from apscheduler.schedulers.background import BackgroundScheduler
import datetime
import os
import sys
import hashlib
import json
import requests
import urllib.parse
import threading

_scraping_lock = threading.Lock()

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.scraper import fetch_rss_feed, scrape_article_content
from database.dbConnection import get_mysql_connection, get_arango_db
from database.chromaConnection import get_chroma_collection
from utils.logger import sys_logger
from services.llm_processor import extract_entities_and_relationships, extract_proper_nouns, gather_knowledge_for_entity
from utils.settings_manager import load_settings

_scheduler = None
_scheduler_next_run = None  # cached next run time for external read


def get_scheduler_next_run():
    """Returns the next scheduled run time as an ISO string, or None."""
    global _scheduler, _scheduler_next_run
    if _scheduler:
        try:
            job = _scheduler.get_job("scraping_job")
            if job and job.next_run_time:
                _scheduler_next_run = job.next_run_time.isoformat()
                return _scheduler_next_run
        except Exception:
            pass
    return _scheduler_next_run


def write_scheduler_log_to_mysql(run_at, next_run_at, interval_hours, status, articles_processed,
                                  nodes_added, nodes_updated, edges_added, errors, triggered_by="scheduler"):
    """Persist a scheduler run record to the MySQL scheduler_logs table."""
    try:
        conn = get_mysql_connection()
        if not conn:
            return
        cursor = conn.cursor()
        errors_str = "; ".join(errors) if errors else ""
        next_run_val = None
        if next_run_at:
            try:
                if isinstance(next_run_at, str):
                    # strip timezone if present so MySQL can accept it
                    next_run_val = next_run_at.split("+")[0].replace("T", " ")[:19]
                else:
                    next_run_val = next_run_at.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                next_run_val = None
        run_at_str = run_at if isinstance(run_at, str) else run_at.strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            INSERT INTO scheduler_logs
                (run_at, next_run_at, interval_hours, status, articles_processed,
                 nodes_added, nodes_updated, edges_added, errors, triggered_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            run_at_str,
            next_run_val,
            interval_hours,
            status,
            articles_processed,
            nodes_added,
            nodes_updated,
            edges_added,
            errors_str,
            triggered_by
        ))
        conn.commit()
        cursor.close()
        conn.close()
        sys_logger.log(f"Scheduler log written to MySQL (status={status}, articles={articles_processed})", level="INFO")
    except Exception as e:
        sys_logger.log(f"Failed to write scheduler log to MySQL: {e}", level="ERROR")

def get_next_run_time(interval_hours):
    """Calculates the next run time relative to the last successful scrape execution recorded in database/audit logs."""
    last_run_time = None
    
    # Try database first
    try:
        conn = get_mysql_connection()
        if conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT run_at FROM scheduler_logs 
                WHERE status = 'SUCCESS' OR status = 'PARTIAL_FAILURE'
                ORDER BY id DESC LIMIT 1
            """)
            row = cursor.fetchone()
            if row and row[0]:
                last_run_time = row[0]
            cursor.close()
            conn.close()
    except Exception as e:
        sys_logger.log(f"Failed to fetch last run time from MySQL for next run calculation: {e}", level="WARNING")

    # Fallback to audit_logs.jsonl
    if not last_run_time:
        storage_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "storage")
        audit_file = os.path.join(storage_dir, "audit_logs.jsonl")
        if os.path.exists(audit_file):
            try:
                with open(audit_file, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    if lines:
                        import json
                        last_entry = json.loads(lines[-1].strip())
                        last_run_time_str = last_entry.get("timestamp")
                        if last_run_time_str:
                            # Split on dot to ignore microseconds for robust parsing
                            last_run_time = datetime.datetime.fromisoformat(last_run_time_str.split(".")[0])
            except Exception:
                pass
                
    now = datetime.datetime.now()
    if last_run_time:
        next_run = last_run_time + datetime.timedelta(hours=interval_hours)
        if next_run < now:
            return now + datetime.timedelta(seconds=5)
        return next_run
    return now + datetime.timedelta(hours=interval_hours)


def fetch_wikipedia_summary(proper_noun):
    """
    Collects full text info on a proper noun by querying the Wikipedia Action API with a search query fallback.
    Enhances breadth of data retrieval for major events like World Cup/Football by fetching multiple related pages.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    # Check if keyword is related to major sports/events
    event_terms = ["world cup", "football", "fifa", "tournament", "olympics", "cricket", "championship", "match"]
    is_major_event = any(term in proper_noun.lower() for term in event_terms)
    search_limit = 3 if is_major_event else 1
    
    try:
        encoded_noun = urllib.parse.quote(proper_noun)
        # 1. Try direct lookup first (only if not forcing breadth search for sports events)
        if not is_major_event:
            wiki_url = f"https://en.wikipedia.org/w/api.php?action=query&format=json&titles={encoded_noun}&prop=extracts&explaintext=true&redirects=1"
            print(f"Visiting URL: {wiki_url}", flush=True)
            res = requests.get(wiki_url, headers=headers, timeout=8)
            if res.status_code == 200:
                data = res.json()
                pages = data.get("query", {}).get("pages", {})
                for page_id, page_data in pages.items():
                    if page_id != "-1" and "extract" in page_data:
                        return page_data["extract"]
                    
        # 2. Search fallback
        search_url = f"https://en.wikipedia.org/w/api.php?action=query&format=json&list=search&srsearch={encoded_noun}&srlimit={search_limit}"
        print(f"Visiting URL: {search_url}", flush=True)
        res = requests.get(search_url, headers=headers, timeout=8)
        if res.status_code == 200:
            data = res.json()
            search_results = data.get("query", {}).get("search", [])
            if search_results:
                combined_extracts = []
                for result in search_results:
                    best_title = result["title"]
                    encoded_best = urllib.parse.quote(best_title)
                    wiki_url = f"https://en.wikipedia.org/w/api.php?action=query&format=json&titles={encoded_best}&prop=extracts&explaintext=true&redirects=1"
                    print(f"Visiting URL: {wiki_url}", flush=True)
                    res2 = requests.get(wiki_url, headers=headers, timeout=8)
                    if res2.status_code == 200:
                        data2 = res2.json()
                        pages2 = data2.get("query", {}).get("pages", {})
                        for page_id, page_data in pages2.items():
                            if page_id != "-1" and "extract" in page_data:
                                combined_extracts.append(page_data["extract"])
                if combined_extracts:
                    return "\n\n---\n\n".join(combined_extracts)
    except Exception:
        pass
    return ""

def clean_name(n):
    if not n:
        return ""
    return " ".join(n.split())

def normalize_node_type(raw_type):
    if not raw_type:
        return "Other"
    raw_type_lower = raw_type.lower()
    if any(w in raw_type_lower for w in ["person", "man", "woman", "player", "coach", "manager", "ceo"]):
        return "Person"
    if any(w in raw_type_lower for w in ["organization", "company", "group", "firm", "association", "band", "club", "team"]):
        return "Organization"
    if any(w in raw_type_lower for w in ["location", "place", "country", "city", "state", "town"]):
        return "Location"
    if any(w in raw_type_lower for w in ["event", "celebration", "war", "match", "game", "conference"]):
        return "Event"
    if any(w in raw_type_lower for w in ["product", "device", "album", "single", "song"]):
        return "Product"
    if any(w in raw_type_lower for w in ["technology", "tech", "software", "hardware"]):
        return "Technology"
    if any(w in raw_type_lower for w in ["topic", "subject"]):
        return "Topic"
    if any(w in raw_type_lower for w in ["category"]):
        return "Category"
    return "Other"

def normalize_edge_type(raw_label):
    if not raw_label:
        return "related_to"
    # Clean whitespace and return direct dynamic semantic label
    return " ".join(raw_label.split())

def is_valid_proper_noun(name, content):
    """
    Validates if a name is a proper noun:
    - Must be at least 2 characters.
    - Must have at least one significant word present in the source content.
    - Must start with an uppercase letter (except for exceptions like iPhone).
    - Must not be in a blacklist of common generic terms.
    """
    if not name:
        return False
    c_name = " ".join(name.split())
    if len(c_name) < 2:
        return False

    # Check if ANY significant word (3+ chars) from the name appears in content
    # This is more lenient than exact match — handles LLM paraphrasing
    content_lower = content.lower()
    words = [w for w in c_name.split() if len(w) >= 3]
    if words:
        if not any(w.lower() in content_lower for w in words):
            return False
    else:
        # Very short name — fall back to exact check
        if c_name.lower() not in content_lower:
            return False

    # Check if it starts with an uppercase letter
    if not c_name[0].isupper() and not (c_name.startswith("iP") or c_name.startswith("eB")):
        return False

    # Blacklist of common generic words
    blacklist = {
        "regulator", "regulators", "customer", "customers", "officer", "officers",
        "suspect", "suspects", "people", "company", "companies", "government",
        "governments", "country", "countries", "phone call", "phone calls", "user", "users",
        "witness", "witnesses", "victim", "victims", "police", "police officer", "police officers"
    }
    if c_name.lower() in blacklist:
        return False

    return True

def update_knowledge_graph_for_harvested_knowledge(db, url, title, article_id, proper_noun, category, gathered_knowledge, extracted_data, published):
    """
    Validates, extracts and builds the ArangoDB Knowledge Graph from harvested knowledge of a proper noun.
    """
    entities = extracted_data.get("entities", [])
    relationships = extracted_data.get("relationships", [])
    
    collection_name = "ai_hub_entities"
    edge_collection_name = "ai_hub_relations"
    graph_name = "AIHubKnowledgeGraph"
    
    if not db.has_collection(collection_name):
        db.create_collection(collection_name)
    entities_coll = db.collection(collection_name)
    
    if not db.has_collection(edge_collection_name):
        db.create_collection(edge_collection_name, edge=True)
    relations_coll = db.collection(edge_collection_name)
    
    if not db.has_graph(graph_name):
        db.create_graph(
            graph_name,
            edge_definitions=[
                {
                    "edge_collection": edge_collection_name,
                    "from_vertex_collections": [collection_name],
                    "to_vertex_collections": [collection_name]
                }
            ]
        )
        
    timestamp = datetime.datetime.now().isoformat()
    art_key = f"art_{hashlib.md5(url.encode()).hexdigest()}"
    
    # 1. Ensure parent Article Node exists
    article_doc = {
        "_key": art_key,
        "name": title,
        "category": "Article",
        "source_url": url,
        "article_id": str(article_id) if article_id else "",
        "timestamp": timestamp,
        "confidence": 1.0,
        "claims": [{
            "category": "Article",
            "confidence": 1.0,
            "source_url": url,
            "timestamp": timestamp
        }]
    }
    if not entities_coll.has(art_key):
        entities_coll.insert(article_doc)

    nodes_added = 0
    nodes_updated = 0
    edges_added = 0

    # 2. Ensure Proper Noun Node itself exists
    pn_clean = clean_name(proper_noun)
    pn_hash = hashlib.md5(pn_clean.lower().encode()).hexdigest()
    pn_key = f"ent_{pn_hash}"
    
    pn_claim = {
        "category": category,
        "confidence": 1.0,
        "source_url": url,
        "timestamp": timestamp
    }
    
    if entities_coll.has(pn_key):
        existing_pn = entities_coll.get(pn_key)
        claims = existing_pn.get("claims", [])
        if not any(c.get("source_url") == url and c.get("category") == category for c in claims):
            claims.append(pn_claim)
        existing_pn["claims"] = claims
        existing_pn["timestamp"] = timestamp
        
        # Merge article reference URL
        urls = existing_pn.get("source_urls", [])
        if url not in urls:
            urls.append(url)
        existing_pn["source_urls"] = urls
        
        # Merge article reference ID
        art_ids = existing_pn.get("article_ids", [])
        s_art_id = str(article_id) if article_id else ""
        if s_art_id and s_art_id not in art_ids:
            art_ids.append(s_art_id)
        existing_pn["article_ids"] = art_ids
        
        entities_coll.update(existing_pn)
        nodes_updated += 1
    else:
        new_pn = {
            "_key": pn_key,
            "name": pn_clean,
            "category": category,
            "confidence": 1.0,
            "source_urls": [url],
            "article_ids": [str(article_id) if article_id else ""],
            "timestamp": timestamp,
            "claims": [pn_claim]
        }
        entities_coll.insert(new_pn)
        nodes_added += 1

    # 3. Create "mentions" relationship from Article to Proper Noun Node
    edge_hash = hashlib.md5(f"{art_key}_{pn_key}_mentions".encode()).hexdigest()
    edge_key = f"edge_{edge_hash}"
    edge_doc = {
        "_key": edge_key,
        "_from": f"{collection_name}/{art_key}",
        "_to": f"{collection_name}/{pn_key}",
        "label": "mentions",
        "confidence": 1.0,
        "source_url": url,
        "article_id": str(article_id) if article_id else "",
        "timestamp": timestamp,
        "claims": [{
            "label": "mentions",
            "confidence": 1.0,
            "source_url": url,
            "timestamp": timestamp
        }]
    }
    if relations_coll.has(edge_key):
        existing_edge = relations_coll.get(edge_key)
        claims = existing_edge.get("claims", [])
        if not any(c.get("source_url") == url for c in claims):
            claims.append(edge_doc["claims"][0])
        existing_edge["claims"] = claims
        existing_edge["timestamp"] = timestamp
        relations_coll.update(existing_edge)
    else:
        relations_coll.insert(edge_doc)
        edges_added += 1

    # 4. Map for resolved sub-entity keys
    entity_keys_map = {pn_clean.lower(): pn_key}

    # 5. Insert/Update Sub-Entity Nodes from Harvested Knowledge Graph
    # NOTE: We register ALL LLM-extracted entity names in entity_keys_map (even those
    # that don't appear verbatim in gathered_knowledge) so that relationship lookups work.
    # is_valid_proper_noun is used only to decide whether to SKIP inserting a node, but
    # the key mapping is added regardless so relationships are never silently dropped.
    for ent in entities:
        raw_name = ent.get("name")
        if not raw_name:
            continue
            
        c_name = clean_name(raw_name)
        if len(c_name) < 2:
            continue

        ent_category = normalize_node_type(ent.get("type", "Other"))
        confidence = float(ent.get("confidence", 1.0))
        
        ent_hash = hashlib.md5(c_name.lower().encode()).hexdigest()
        ent_key = f"ent_{ent_hash}"
        # Always register in map so relationship source/target lookup works
        entity_keys_map[c_name.lower()] = ent_key
        
        # Only persist to ArangoDB if entity passes validation
        if not is_valid_proper_noun(raw_name, gathered_knowledge):
            # Still add to map but don't insert/update in DB as a standalone node
            continue
        
        claim = {
            "category": ent_category,
            "confidence": confidence,
            "source_url": url,
            "timestamp": timestamp
        }
        
        if entities_coll.has(ent_key):
            existing = entities_coll.get(ent_key)
            claims = existing.get("claims", [])
            if not any(c.get("source_url") == url and c.get("category") == ent_category for c in claims):
                claims.append(claim)
            existing["claims"] = claims
            existing["timestamp"] = timestamp
            
            # Merge article reference URL
            urls = existing.get("source_urls", [])
            if url not in urls:
                urls.append(url)
            existing["source_urls"] = urls
            
            # Merge article reference ID
            art_ids = existing.get("article_ids", [])
            s_art_id = str(article_id) if article_id else ""
            if s_art_id and s_art_id not in art_ids:
                art_ids.append(s_art_id)
            existing["article_ids"] = art_ids
            
            best_claim = max(claims, key=lambda c: c.get("confidence", 0.0))
            existing["category"] = best_claim["category"]
            existing["confidence"] = best_claim["confidence"]
            
            entities_coll.update(existing)
            nodes_updated += 1
        else:
            new_entity = {
                "_key": ent_key,
                "name": c_name,
                "category": ent_category,
                "confidence": confidence,
                "source_urls": [url],
                "article_ids": [str(article_id) if article_id else ""],
                "timestamp": timestamp,
                "claims": [claim]
            }
            entities_coll.insert(new_entity)
            nodes_added += 1


    # 6. Create relationship from Proper Noun to each sub-entity
    #    Only insert edge if BOTH nodes actually exist in ArangoDB.
    for sub_name, sub_key in entity_keys_map.items():
        if sub_key == pn_key:
            continue
        # Guard: skip if the sub-entity node was never persisted (failed validation)
        if not entities_coll.has(sub_key):
            continue
        # Guard: skip if proper noun node itself is missing (shouldn't happen, but be safe)
        if not entities_coll.has(pn_key):
            continue
        sub_edge_hash = hashlib.md5(f"{pn_key}_{sub_key}_related_to".encode()).hexdigest()
        sub_edge_key = f"edge_{sub_edge_hash}"
        sub_edge_doc = {
            "_key": sub_edge_key,
            "_from": f"{collection_name}/{pn_key}",
            "_to": f"{collection_name}/{sub_key}",
            "label": "related_to",
            "confidence": 1.0,
            "source_url": url,
            "article_id": str(article_id) if article_id else "",
            "timestamp": timestamp,
            "claims": [{
                "label": "related_to",
                "confidence": 1.0,
                "source_url": url,
                "timestamp": timestamp
            }]
        }
        if relations_coll.has(sub_edge_key):
            existing_sub_edge = relations_coll.get(sub_edge_key)
            claims = existing_sub_edge.get("claims", [])
            if not any(c.get("source_url") == url for c in claims):
                claims.append(sub_edge_doc["claims"][0])
            existing_sub_edge["claims"] = claims
            existing_sub_edge["timestamp"] = timestamp
            relations_coll.update(existing_sub_edge)
        else:
            relations_coll.insert(sub_edge_doc)
            edges_added += 1


    # 7. Create semantic relationships between sub-entities
    for rel in relationships:
        source_name = rel.get("source")
        target_name = rel.get("target")
        raw_label = rel.get("type")
        confidence = float(rel.get("confidence", 1.0))
        
        if not source_name or not target_name or not raw_label:
            continue
            
        c_src = clean_name(source_name)
        c_tgt = clean_name(target_name)
        
        # Primary lookup in entity_keys_map
        src_key = entity_keys_map.get(c_src.lower())
        tgt_key = entity_keys_map.get(c_tgt.lower())
        
        # Fallback: derive key by hash so we can still create the edge even if
        # the entity was not previously seen in gathered_knowledge verbatim.
        # This ensures relationships LLM returns are never silently dropped.
        if not src_key and c_src and len(c_src) >= 2:
            src_hash = hashlib.md5(c_src.lower().encode()).hexdigest()
            candidate_key = f"ent_{src_hash}"
            if entities_coll.has(candidate_key):
                src_key = candidate_key
        if not tgt_key and c_tgt and len(c_tgt) >= 2:
            tgt_hash = hashlib.md5(c_tgt.lower().encode()).hexdigest()
            candidate_key = f"ent_{tgt_hash}"
            if entities_coll.has(candidate_key):
                tgt_key = candidate_key
        
        if not src_key or not tgt_key:
            continue
            
        label = normalize_edge_type(raw_label)
        
        edge_hash = hashlib.md5(f"{src_key}_{tgt_key}_{label}".encode()).hexdigest()
        edge_key = f"edge_{edge_hash}"
        
        claim = {
            "label": label,
            "confidence": confidence,
            "source_url": url,
            "timestamp": timestamp
        }
        
        edge_doc = {
            "_key": edge_key,
            "_from": f"{collection_name}/{src_key}",
            "_to": f"{collection_name}/{tgt_key}",
            "label": label,
            "confidence": confidence,
            "source_url": url,
            "article_id": str(article_id) if article_id else "",
            "timestamp": timestamp,
            "claims": [claim]
        }
        
        if relations_coll.has(edge_key):
            existing = relations_coll.get(edge_key)
            claims = existing.get("claims", [])
            if not any(c.get("source_url") == url and c.get("label") == label for c in claims):
                claims.append(claim)
            existing["claims"] = claims
            existing["timestamp"] = timestamp
            
            best_claim = max(claims, key=lambda c: c.get("confidence", 0.0))
            existing["label"] = best_claim["label"]
            existing["confidence"] = best_claim["confidence"]
            
            relations_coll.update(existing)
        else:
            relations_coll.insert(edge_doc)
            edges_added += 1

    return nodes_added, nodes_updated, edges_added

def ensure_article_node_in_arango(db, url, title, article_id, published=None):
    collection_name = "ai_hub_entities"
    edge_collection_name = "ai_hub_relations"
    graph_name = "AIHubKnowledgeGraph"
    
    if not db.has_collection(collection_name):
        db.create_collection(collection_name)
    entities_coll = db.collection(collection_name)
    
    if not db.has_collection(edge_collection_name):
        db.create_collection(edge_collection_name, edge=True)
    relations_coll = db.collection(edge_collection_name)
    
    if not db.has_graph(graph_name):
        db.create_graph(
            graph_name,
            edge_definitions=[
                {
                    "edge_collection": edge_collection_name,
                    "from_vertex_collections": [collection_name],
                    "to_vertex_collections": [collection_name]
                }
            ]
        )
        
    timestamp = datetime.datetime.now().isoformat()
    art_key = f"art_{hashlib.md5(url.encode()).hexdigest()}"
    
    article_doc = {
        "_key": art_key,
        "name": title,
        "category": "Article",
        "source_url": url,
        "article_id": str(article_id) if article_id else "",
        "timestamp": timestamp,
        "confidence": 1.0,
        "claims": [{
            "category": "Article",
            "confidence": 1.0,
            "source_url": url,
            "timestamp": timestamp
        }]
    }
    if not entities_coll.has(art_key):
        entities_coll.insert(article_doc)
    return art_key

def update_knowledge_graph_directly_from_article(db, url, title, article_id, content, extracted_data, published):
    entities = extracted_data.get("entities", [])
    relationships = extracted_data.get("relationships", [])
    
    collection_name = "ai_hub_entities"
    edge_collection_name = "ai_hub_relations"
    
    entities_coll = db.collection(collection_name)
    relations_coll = db.collection(edge_collection_name)
    
    timestamp = datetime.datetime.now().isoformat()
    art_key = f"art_{hashlib.md5(url.encode()).hexdigest()}"
    
    nodes_added = 0
    nodes_updated = 0
    edges_added = 0
    
    entity_keys_map = {}
    
    # Ensure Article Node itself exists
    ensure_article_node_in_arango(db, url, title, article_id, published)
    
    # 1. Insert/Update Sub-Entity Nodes from Extracted Graph Data
    for ent in entities:
        raw_name = ent.get("name")
        if not raw_name or len(raw_name.strip()) < 2:
            continue
            
        c_name = clean_name(raw_name)
        ent_category = normalize_node_type(ent.get("type", "Other"))
        confidence = float(ent.get("confidence", 1.0))
        
        ent_hash = hashlib.md5(c_name.lower().encode()).hexdigest()
        ent_key = f"ent_{ent_hash}"
        entity_keys_map[c_name.lower()] = ent_key
        
        claim = {
            "category": ent_category,
            "confidence": confidence,
            "source_url": url,
            "timestamp": timestamp
        }
        
        if entities_coll.has(ent_key):
            existing = entities_coll.get(ent_key)
            claims = existing.get("claims", [])
            if not any(c.get("source_url") == url and c.get("category") == ent_category for c in claims):
                claims.append(claim)
            existing["claims"] = claims
            existing["timestamp"] = timestamp
            
            # Merge article reference URL
            urls = existing.get("source_urls", [])
            if url not in urls:
                urls.append(url)
            existing["source_urls"] = urls
            
            # Merge article reference ID
            art_ids = existing.get("article_ids", [])
            s_art_id = str(article_id) if article_id else ""
            if s_art_id and s_art_id not in art_ids:
                art_ids.append(s_art_id)
            existing["article_ids"] = art_ids
            
            best_claim = max(claims, key=lambda c: c.get("confidence", 0.0))
            existing["category"] = best_claim["category"]
            existing["confidence"] = best_claim["confidence"]
            
            entities_coll.update(existing)
            nodes_updated += 1
        else:
            new_entity = {
                "_key": ent_key,
                "name": c_name,
                "category": ent_category,
                "confidence": confidence,
                "source_urls": [url],
                "article_ids": [str(article_id) if article_id else ""],
                "timestamp": timestamp,
                "claims": [claim]
            }
            entities_coll.insert(new_entity)
            nodes_added += 1

        # Create "mentions" / connection from Article to this Entity Node
        edge_hash = hashlib.md5(f"{art_key}_{ent_key}_mentions".encode()).hexdigest()
        edge_key = f"edge_{edge_hash}"
        edge_doc = {
            "_key": edge_key,
            "_from": f"{collection_name}/{art_key}",
            "_to": f"{collection_name}/{ent_key}",
            "label": "mentions",
            "confidence": 1.0,
            "source_url": url,
            "article_id": str(article_id) if article_id else "",
            "timestamp": timestamp,
            "claims": [{
                "label": "mentions",
                "confidence": 1.0,
                "source_url": url,
                "timestamp": timestamp
            }]
        }
        if relations_coll.has(edge_key):
            existing_edge = relations_coll.get(edge_key)
            claims = existing_edge.get("claims", [])
            if not any(c.get("source_url") == url for c in claims):
                claims.append(edge_doc["claims"][0])
            existing_edge["claims"] = claims
            existing_edge["timestamp"] = timestamp
            relations_coll.update(existing_edge)
        else:
            relations_coll.insert(edge_doc)
            edges_added += 1

    # 2. Create semantic relationships between sub-entities
    for rel in relationships:
        source_name = rel.get("source")
        target_name = rel.get("target")
        raw_label = rel.get("type")
        confidence = float(rel.get("confidence", 1.0))
        
        if not source_name or not target_name or not raw_label:
            continue
            
        c_src = clean_name(source_name)
        c_tgt = clean_name(target_name)
        
        src_key = entity_keys_map.get(c_src.lower())
        tgt_key = entity_keys_map.get(c_tgt.lower())
        
        if not src_key or not tgt_key:
            continue
            
        label = normalize_edge_type(raw_label)
        edge_hash = hashlib.md5(f"{src_key}_{tgt_key}_{label}".encode()).hexdigest()
        edge_key = f"edge_{edge_hash}"
        
        claim = {
            "label": label,
            "confidence": confidence,
            "source_url": url,
            "timestamp": timestamp
        }
        
        edge_doc = {
            "_key": edge_key,
            "_from": f"{collection_name}/{src_key}",
            "_to": f"{collection_name}/{tgt_key}",
            "label": label,
            "confidence": confidence,
            "source_url": url,
            "article_id": str(article_id) if article_id else "",
            "timestamp": timestamp,
            "claims": [claim]
        }
        
        if relations_coll.has(edge_key):
            existing = relations_coll.get(edge_key)
            claims = existing.get("claims", [])
            if not any(c.get("source_url") == url and c.get("label") == label for c in claims):
                claims.append(claim)
            existing["claims"] = claims
            existing["timestamp"] = timestamp
            
            best_claim = max(claims, key=lambda c: c.get("confidence", 0.0))
            existing["label"] = best_claim["label"]
            existing["confidence"] = best_claim["confidence"]
            
            relations_coll.update(existing)
        else:
            relations_coll.insert(edge_doc)
            edges_added += 1

    return nodes_added, nodes_updated, edges_added

def _run_daily_scraping_task():
    sys_logger.log("Starting scheduled scraping task...", level="SYSTEM")
    
    settings = load_settings()
    max_articles = settings.get("max_articles_per_source", 3)
    
    # 1. Establish Connections
    mysql_conn = get_mysql_connection()
    mysql_cursor = mysql_conn.cursor() if mysql_conn else None
            
    chroma_collection = get_chroma_collection()
    arango_db = get_arango_db()
    
    storage_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "storage")
    os.makedirs(storage_dir, exist_ok=True)
    audit_file = os.path.join(storage_dir, "audit_logs.jsonl")
    retry_file = os.path.join(storage_dir, "failed_graph_updates.json")

    # Load previously failed updates
    failed_items = []
    if os.path.exists(retry_file):
        try:
            with open(retry_file, "r", encoding="utf-8") as f:
                failed_items = json.load(f)
        except Exception:
            failed_items = []

    processed_urls = []
    nodes_added_count = 0
    nodes_updated_count = 0
    edges_added_count = 0
    task_errors = []

    # Build unified list of active connectors from MySQL and standard RSS URLs from settings
    connectors = []
    if mysql_cursor:
        try:
            mysql_cursor.execute("SELECT url, type FROM connectors")
            rows = mysql_cursor.fetchall()
            for row in rows:
                connectors.append({
                    "url": row[0],
                    "type": row[1]
                })
        except Exception as e:
            sys_logger.log(f"Failed to fetch active connectors from MySQL: {e}", level="ERROR")
            task_errors.append(f"DB Error: {str(e)}")
        finally:
            try:
                mysql_cursor.close()
            except Exception:
                pass
            try:
                mysql_conn.close()
            except Exception:
                pass
            mysql_cursor = None
            mysql_conn = None

    rss_urls = settings.get("rss_urls", ["http://feeds.bbci.co.uk/news/rss.xml"])
    
    unified_connectors = []
    # Add custom connectors
    for conn in connectors:
        if conn.get("url"):
            unified_connectors.append({
                "url": conn.get("url"),
                "type": conn.get("type", "rss")
            })
            
    # Add default RSS URLs to crawl, avoiding duplicates
    existing_urls = {c["url"].lower() for c in unified_connectors}
    for url in rss_urls:
        if url.lower() not in existing_urls:
            unified_connectors.append({
                "url": url,
                "type": "rss"
            })

    # Fetch new articles from RSS sources or direct URLs
    rss_articles = []
    for conn in unified_connectors:
        url = conn.get("url")
        c_type = conn.get("type", "rss")
        
        if not url:
            continue
            
        if c_type == "rss":
            sys_logger.log(f"Fetching RSS feed: {url}", level="INFO")
            try:
                entries = fetch_rss_feed(url)
                if entries:
                    sys_logger.log(f"Fetching all {len(entries)} articles from RSS feed: {url}", level="INFO")
                    rss_articles.extend(entries)  # process all articles
                else:
                    # Fallback to direct URL if no RSS entries found
                    now_str = datetime.datetime.now().strftime("%a, %d %b %Y %H:%M:%S GMT")
                    from urllib.parse import urlparse
                    parsed_url = urlparse(url)
                    domain = parsed_url.netloc
                    rss_articles.append({
                        "title": f"Article from {domain}" if domain else "Direct URL Scraping",
                        "link": url,
                        "published": now_str,
                        "summary": ""
                    })
            except Exception as e:
                sys_logger.log(f"Failed parsing RSS, attempting direct scraping for {url}: {e}", level="INFO")
                try:
                    now_str = datetime.datetime.now().strftime("%a, %d %b %Y %H:%M:%S GMT")
                    from urllib.parse import urlparse
                    parsed_url = urlparse(url)
                    domain = parsed_url.netloc
                    rss_articles.append({
                        "title": f"Article from {domain}" if domain else "Direct URL Scraping",
                        "link": url,
                        "published": now_str,
                        "summary": ""
                    })
                except Exception as ex:
                    sys_logger.log(f"Error handling URL {url}: {ex}", level="ERROR")
                    task_errors.append(f"Scraping error: {str(ex)}")
        else:
            # Direct Webpage type (webpage, news, wiki, research)
            sys_logger.log(f"Adding direct webpage for scraping: {url} (Type: {c_type})", level="INFO")
            try:
                now_str = datetime.datetime.now().strftime("%a, %d %b %Y %H:%M:%S GMT")
                from urllib.parse import urlparse
                parsed_url = urlparse(url)
                domain = parsed_url.netloc
                
                type_labels = {
                    "news": "Online Newspaper",
                    "wiki": "Wikipedia Page",
                    "research": "Research Portal"
                }
                label = type_labels.get(c_type, "Webpage")
                
                # Fetch page to check for sub-links (articles)
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                }
                
                page_fetched = False
                response = None
                try:
                    import cloudscraper
                    scraper = cloudscraper.create_scraper()
                    response = scraper.get(url, headers=headers, timeout=10)
                except Exception:
                    try:
                        import requests
                        response = requests.get(url, headers=headers, timeout=10)
                    except Exception:
                        pass
                
                if response and response.status_code == 200:
                    from bs4 import BeautifulSoup
                    from urllib.parse import urljoin
                    soup = BeautifulSoup(response.content, 'html.parser')
                    
                    # Look for links
                    links_found = []
                    for a in soup.find_all('a', href=True):
                        href = a['href'].strip()
                        full_url = urljoin(url, href)
                        parsed_full = urlparse(full_url)
                        
                        # Heuristics:
                        # 1. Same domain
                        # 2. Path has substantial length (likely an article, not home or category list)
                        # 3. Not a file extension (e.g. .pdf, .jpg, .zip)
                        # 4. Doesn't contain common nav/system pages
                        if parsed_full.netloc == domain:
                            path_lower = parsed_full.path.lower()
                            # Avoid home page itself
                            if path_lower in ["", "/", "/index.html", "/index.php"]:
                                continue
                            # Exclude assets & nav
                            if any(ext in path_lower for ext in [".png", ".jpg", ".jpeg", ".gif", ".pdf", ".css", ".js", ".zip"]):
                                                    continue
                            if any(nav in path_lower for nav in ["/login", "/register", "/signup", "/contact", "/about", "/privacy", "/terms", "/help", "/category", "/tags", "/search"]):
                                                    continue
                            
                            # Clean anchor text
                            text = a.get_text().strip()
                            # Often article links have a long path (e.g., /news/2026/07/event-title)
                            if len(path_lower.split('/')) > 2 or any(keyword in path_lower for keyword in ["/article", "/story", "/wiki/", "/p/", "/news/"]):
                                if full_url not in [l['link'] for l in links_found] and full_url.lower() != url.lower():
                                    title_text = text if len(text) > 10 else f"Sub-article from {domain}"
                                    links_found.append({
                                        "title": title_text,
                                        "link": full_url,
                                        "published": now_str,
                                        "summary": ""
                                    })
                                    
                    # If we found valid sub-article links, add them (up to 5 to avoid overloading)
                    if len(links_found) > 0:
                        sys_logger.log(f"Extracted {len(links_found)} sub-article links from portal {url}. Adding top 5 to scraping queue.", level="INFO")
                        rss_articles.extend(links_found[:5])
                    else:
                        # Fallback to scraping the URL itself as a single page
                        rss_articles.append({
                            "title": f"{label} from {domain}" if domain else f"{label} Scraping",
                            "link": url,
                            "published": now_str,
                            "summary": ""
                        })
                else:
                    # Fallback to URL itself
                    rss_articles.append({
                        "title": f"{label} from {domain}" if domain else f"{label} Scraping",
                        "link": url,
                        "published": now_str,
                        "summary": ""
                    })
            except Exception as ex:
                sys_logger.log(f"Error handling webpage URL {url}: {ex}", level="ERROR")
                task_errors.append(f"Scraping error: {str(ex)}")

    # Concurrent article processing logic
    from concurrent.futures import ThreadPoolExecutor
    stats_lock = threading.Lock()
    processed_count = 0

    def process_single_article_thread(entry):
        nonlocal processed_count, nodes_added_count, nodes_updated_count, edges_added_count
        # Mutable container so doubly-nested process_single_keyword can update counters
        _stats = [0, 0, 0]  # [nodes_added, nodes_updated, edges_added]
        
        thread_mysql_conn = get_mysql_connection()
        thread_mysql_cursor = thread_mysql_conn.cursor() if thread_mysql_conn else None
        thread_chroma_collection = get_chroma_collection()
        thread_arango_db = get_arango_db()
        
        url = entry["link"]
        title = entry["title"]
        published = entry.get("published", "")
        summary = entry.get("summary", "")
        article_id = None
        has_failures = False
        
        try:
            # Idempotency Check: Skip processing if article exists in MySQL
            if thread_mysql_cursor:
                thread_mysql_cursor.execute("SELECT id FROM articles_meta WHERE source_url = %s", (url,))
                if thread_mysql_cursor.fetchone():
                    sys_logger.log(f"Article already processed (idempotency skip): {title}", level="INFO")
                    return
            else:
                return

            # Scrape and clean article text
            content = scrape_article_content(url)
            if not content and summary:
                content = summary
            if not content:
                sys_logger.log(f"Skipping article with no readable text: {title}", level="WARN")
                return

            # Save structured article to MySQL
            if thread_mysql_conn and thread_mysql_cursor:
                try:
                    thread_mysql_cursor.execute("INSERT IGNORE INTO articles_meta (title, source_url) VALUES (%s, %s)", (title, url))
                    thread_mysql_conn.commit()
                    thread_mysql_cursor.execute("SELECT id FROM articles_meta WHERE source_url = %s", (url,))
                    row = thread_mysql_cursor.fetchone()
                    if row:
                        article_id = row[0]
                except Exception as e:
                    sys_logger.log(f"MySQL Insert Error for {title}: {e}", level="ERROR")
                    has_failures = True
                    with stats_lock:
                        task_errors.append(f"MySQL error: {str(e)}")

            # Save document embedding to ChromaDB
            if thread_chroma_collection:
                try:
                    thread_chroma_collection.delete(where={"source_url": url})
                    chunks = [content[i:i+1000] for i in range(0, len(content), 1000)]
                    for i, chunk in enumerate(chunks):
                        doc_id = hashlib.md5(f"{url}_{i}".encode()).hexdigest()
                        chunk_text = f"Document Title: {title}\nPublished Date: {published}\nSource URL: {url}\n\nContent:\n# {title}\n\n{chunk}"
                        thread_chroma_collection.upsert(
                            documents=[chunk_text],
                            metadatas=[{"source_url": url, "title": title, "published": published, "type": "article"}],
                            ids=[doc_id]
                        )
                except Exception as e:
                    sys_logger.log(f"ChromaDB Insert Error for {title}: {e}", level="ERROR")
                    has_failures = True
                    with stats_lock:
                        task_errors.append(f"ChromaDB error: {str(e)}")

            with stats_lock:
                processed_urls.append(url)

            # Always ensure Article Node exists in ArangoDB
            if thread_arango_db:
                try:
                    ensure_article_node_in_arango(thread_arango_db, url, title, article_id, published)
                except Exception as e:
                    sys_logger.log(f"Failed to ensure Article Node in ArangoDB: {e}", level="ERROR")
                    has_failures = True
                    with stats_lock:
                        task_errors.append(f"ArangoDB article node creation error: {str(e)}")

            # Extract proper nouns using local LLM
            short_content = content[:2000]
            proper_nouns_list = []
            try:
                sys_logger.log(f"Extracting proper nouns from content using local LLM...", level="INFO")
                extracted_pns_data = extract_proper_nouns(short_content)
                extracted_pns = extracted_pns_data.get("proper_nouns", [])
                for pn in extracted_pns:
                    raw_name = pn.get("name")
                    category = pn.get("category", "Other")
                    if is_valid_proper_noun(raw_name, content):
                        c_name = clean_name(raw_name)
                        proper_nouns_list.append((c_name, category))
                sys_logger.log(f"Filtered proper nouns: {[n[0] for n in proper_nouns_list]}", level="SUCCESS")
            except Exception as e:
                sys_logger.log(f"Proper noun extraction failed: {e}", level="ERROR")
                has_failures = True
                with stats_lock:
                    task_errors.append(f"Proper noun extraction error: {str(e)}")

            # Fetch search content (Wikipedia) and store mappings (Concurrently)
            if proper_nouns_list:
                def process_single_keyword(pn_item):
                    nonlocal has_failures
                    c_name, category = pn_item
                    
                    sys_logger.log(f"Fetching Wikipedia summary for proper noun '{c_name}'...", level="INFO")
                    wiki_summary = fetch_wikipedia_summary(c_name)
                    
                    sys_logger.log(f"Gathering/synthesizing knowledge for '{c_name}' using local LLM...", level="INFO")
                    gathered_knowledge = gather_knowledge_for_entity(c_name, category, wiki_summary)
                    if not gathered_knowledge:
                        gathered_knowledge = wiki_summary or f"Entity {c_name} of category {category}."
                    
                    extracted_graph_data = {"entities": [], "relationships": []}
                    sub_arango_db = get_arango_db()
                    if sub_arango_db:
                        try:
                            sys_logger.log(f"Extracting entities & relations from gathered knowledge of '{c_name}'...", level="INFO")
                            extracted_graph_data = extract_entities_and_relationships(gathered_knowledge[:2000])
                        except Exception as e:
                            sys_logger.log(f"Graph extraction failed for '{c_name}': {e}", level="ERROR")
                            has_failures = True
                    
                    sub_mysql_conn = get_mysql_connection()
                    sub_mysql_cursor = sub_mysql_conn.cursor() if sub_mysql_conn else None
                    topic_id = None
                    if sub_mysql_conn and sub_mysql_cursor:
                        try:
                            sub_mysql_cursor.execute("SELECT id FROM topics WHERE name = %s", (c_name,))
                            row = sub_mysql_cursor.fetchone()
                            if row:
                                topic_id = row[0]
                                sub_mysql_cursor.execute("UPDATE topics SET description = %s, category = %s WHERE id = %s", (gathered_knowledge, category, topic_id))
                            else:
                                sub_mysql_cursor.execute("INSERT INTO topics (name, category, description) VALUES (%s, %s, %s)", (c_name, category, gathered_knowledge))
                                sub_mysql_conn.commit()
                                sub_mysql_cursor.execute("SELECT LAST_INSERT_ID()")
                                row_id = sub_mysql_cursor.fetchone()
                                if row_id:
                                    topic_id = row_id[0]
                            sub_mysql_conn.commit()
                            
                            if article_id and topic_id:
                                sub_mysql_cursor.execute("INSERT IGNORE INTO article_topics (article_id, topic_id) VALUES (%s, %s)", (article_id, topic_id))
                                sub_mysql_conn.commit()
                        except Exception as e:
                            sys_logger.log(f"MySQL Topic/Mapping Insert Error for {c_name}: {e}", level="ERROR")
                            has_failures = True
                        finally:
                            try:
                                sub_mysql_cursor.close()
                                sub_mysql_conn.close()
                            except Exception:
                                pass
                                
                    sub_chroma_collection = get_chroma_collection()
                    if sub_chroma_collection:
                        node_key = "".join(c for c in c_name if c.isalnum())
                        wiki_doc_id = f"wiki_{node_key}"
                        wiki_url = f"https://en.wikipedia.org/wiki/{node_key}"
                        wiki_text = f"Knowledge Summary for {c_name}:\n{gathered_knowledge}"
                        try:
                            try:
                                sub_chroma_collection.delete(ids=[wiki_doc_id])
                            except Exception:
                                pass
                            sub_chroma_collection.upsert(
                                documents=[wiki_text],
                                metadatas=[{
                                    "source_url": wiki_url, 
                                    "title": f"Knowledge Summary - {c_name}", 
                                    "published": "", 
                                    "type": "proper_noun_search",
                                    "associated_article_url": url,
                                    "proper_noun": c_name
                                }],
                                ids=[wiki_doc_id]
                            )
                        except Exception as e:
                            sys_logger.log(f"ChromaDB Wiki Insert Error for {c_name}: {e}", level="ERROR")
                            has_failures = True
                            
                    if sub_arango_db:
                        try:
                            sys_logger.log(f"Updating ArangoDB Knowledge Graph for '{c_name}'...", level="INFO")
                            n_added, n_updated, e_added = update_knowledge_graph_for_harvested_knowledge(
                                sub_arango_db, url, title, article_id, c_name, category, gathered_knowledge, extracted_graph_data, published
                            )
                            # Use _stats list (mutable) to avoid double-nested nonlocal issue
                            with stats_lock:
                                _stats[0] += n_added
                                _stats[1] += n_updated
                                _stats[2] += e_added
                            sys_logger.log(f"Graph updated for '{c_name}': +{n_added} nodes, ~{n_updated} updated, +{e_added} edges", level="SUCCESS")
                        except Exception as e:
                            sys_logger.log(f"Graph update failed for proper noun '{c_name}': {e}", level="ERROR")
                            has_failures = True
                            with stats_lock:
                                task_errors.append(f"Graph error for {c_name}: {str(e)}")

                for pn_item in proper_nouns_list:
                    process_single_keyword(pn_item)

                # Flush _stats back into the nonlocal counters (safe — single thread per article)
                nodes_added_count += _stats[0]
                nodes_updated_count += _stats[1]
                edges_added_count += _stats[2]
                    
            else:
                if thread_arango_db:
                    try:
                        sys_logger.log(f"No proper nouns extracted. Generating knowledge graph directly from article content...", level="INFO")
                        extracted_graph_data = extract_entities_and_relationships(content[:2000])
                        n_added, n_updated, e_added = update_knowledge_graph_directly_from_article(
                            thread_arango_db, url, title, article_id, content, extracted_graph_data, published
                        )
                        with stats_lock:
                            nodes_added_count += n_added
                            nodes_updated_count += n_updated
                            edges_added_count += e_added
                        sys_logger.log(f"Successfully generated direct knowledge graph for article '{title}'.", level="SUCCESS")
                    except Exception as e:
                        sys_logger.log(f"Failed to generate direct knowledge graph for article '{title}': {e}", level="ERROR")
                        has_failures = True
                        with stats_lock:
                            task_errors.append(f"Direct graph error for {title}: {str(e)}")
        finally:
            # Even if there were processing failures, we preserve all articles in the database as per user request
            if has_failures and article_id:
                sys_logger.log(f"Article '{title}' had processing warnings/failures but is preserved in MySQL metadata.", level="INFO")
            
            if thread_mysql_cursor:
                try:
                    thread_mysql_cursor.close()
                except Exception:
                    pass
            if thread_mysql_conn:
                try:
                    thread_mysql_conn.close()
                except Exception:
                    pass
            
            with stats_lock:
                processed_count += 1
                current_count = processed_count
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            sys_logger.log(f"URL: {url} | Processed: {current_count} articles | Time: {timestamp}", level="INFO")

    # Run the threads concurrently
    if rss_articles:
        with ThreadPoolExecutor(max_workers=3) as executor:
            executor.map(process_single_article_thread, rss_articles)

    # 5. Retry previously failed graph updates
    still_failed = []
    retry_arango_db = get_arango_db()
    if failed_items and retry_arango_db:
        sys_logger.log(f"Retrying {len(failed_items)} failed graph updates...", level="INFO")
        for item in failed_items:
            try:
                extracted_pns_data = extract_proper_nouns(item["content"][:2000])
                extracted_pns = extracted_pns_data.get("proper_nouns", [])
                for pn in extracted_pns:
                    raw_name = pn.get("name")
                    category = pn.get("category", "Other")
                    if is_valid_proper_noun(raw_name, item["content"]):
                        c_name = clean_name(raw_name)
                        wiki_summary = fetch_wikipedia_summary(c_name)
                        gathered_knowledge = gather_knowledge_for_entity(c_name, category, wiki_summary)
                        extracted_graph_data = extract_entities_and_relationships(gathered_knowledge[:2000])
                        n_added, n_updated, e_added = update_knowledge_graph_for_harvested_knowledge(
                            retry_arango_db, item["url"], item["title"], item.get("article_id"), c_name, category, gathered_knowledge, extracted_graph_data, item.get("published", "")
                        )
                        nodes_added_count += n_added
                        nodes_updated_count += n_updated
                        edges_added_count += e_added
                sys_logger.log(f"Successfully retried graph update for {item['title']}", level="SUCCESS")
            except Exception as e:
                sys_logger.log(f"Retry failed for {item['title']}: {e}", level="ERROR")
                still_failed.append(item)
    else:
        still_failed = failed_items

    # Save remaining failures back
    try:
        with open(retry_file, "w", encoding="utf-8") as f:
            json.dump(still_failed, f, indent=2)
    except Exception as e:
        sys_logger.log(f"Error saving retry file: {e}", level="ERROR")

    # Append audit log entry
    status_str = "SUCCESS" if not task_errors else ("PARTIAL_FAILURE" if processed_urls else "FAILURE")
    audit_entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "status": status_str,
        "articles_processed": processed_urls,
        "nodes_added": nodes_added_count,
        "nodes_updated": nodes_updated_count,
        "edges_added": edges_added_count,
        "errors": task_errors
    }
    
    print(f"Successfully processed articles count: {len(processed_urls)}", flush=True)
    sys_logger.log(f"Successfully processed articles count: {len(processed_urls)}", level="INFO")
    
    try:
        with open(audit_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(audit_entry) + "\n")
    except Exception as e:
        sys_logger.log(f"Error writing audit log: {e}", level="ERROR")

    sys_logger.log(f"Daily scraping task completed successfully. Status: {status_str}.", level="SYSTEM")

    # Write run record to MySQL scheduler_logs
    next_run_iso = get_scheduler_next_run()
    settings_for_log = load_settings()
    interval_h = settings_for_log.get("scheduler_interval_hours", 6)
    write_scheduler_log_to_mysql(
        run_at=audit_entry["timestamp"],
        next_run_at=next_run_iso,
        interval_hours=interval_h,
        status=status_str,
        articles_processed=len(processed_urls),
        nodes_added=nodes_added_count,
        nodes_updated=nodes_updated_count,
        edges_added=edges_added_count,
        errors=task_errors,
        triggered_by=_current_triggered_by
    )

# Thread-local flag so manual triggers vs scheduled triggers are differentiated
_current_triggered_by = "scheduler"

def daily_scraping_task(triggered_by="scheduler"):
    global _current_triggered_by
    # Attempt to acquire lock without blocking to prevent concurrent execution
    if not _scraping_lock.acquire(blocking=False):
        sys_logger.log("Scraping task is already running in another thread. Skipping this execution.", level="INFO")
        return
    _current_triggered_by = triggered_by
    try:
        _run_daily_scraping_task()
    finally:
        _scraping_lock.release()

def init_scheduler():
    global _scheduler
    scheduler = BackgroundScheduler()
    settings = load_settings()
    interval = settings.get("scheduler_interval_hours", 6)
    
    # Calculate next run relative to the last actual run recorded in audit logs
    start_time = get_next_run_time(interval)
    
    scheduler.add_job(
        func=daily_scraping_task, 
        trigger="interval", 
        hours=interval,
        start_date=start_time,
        id="scraping_job"
    )
    scheduler.start()
    _scheduler = scheduler
    sys_logger.log(f"Scheduler initialized to run every {interval} hours. Next automated run scheduled for: {start_time.strftime('%Y-%m-%d %H:%M:%S')}.", level="SYSTEM")
    return scheduler
