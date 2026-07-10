import os
import json
import datetime
import threading
import hashlib
import requests
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from flask import request, jsonify
from database.dbConnection import get_mysql_connection, get_arango_db, get_chroma_collection
from utils.logger import sys_logger
from services.scraper import fetch_rss_feed, scrape_article_content

# ==========================================
# 1. API Endpoint Handlers
# ==========================================

def handle_get_ingestion_logs():
    conn = get_mysql_connection()
    if not conn:
        return jsonify([])
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT run_at, status, articles_processed, nodes_added, nodes_updated, edges_added, errors, created_at
            FROM scheduler_logs
            ORDER BY id DESC
            LIMIT 20
        """)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        
        logs = []
        for row in rows:
            err_list = [e.strip() for e in row['errors'].split(';') if e.strip()] if row['errors'] else []
            logs.append({
                "timestamp": row['run_at'].isoformat() if row['run_at'] else row['created_at'].isoformat(),
                "status": row['status'],
                "articles_processed": [None] * (row['articles_processed'] or 0),
                "nodes_added": row['nodes_added'],
                "nodes_updated": row['nodes_updated'],
                "edges_added": row['edges_added'],
                "errors": err_list
            })
        return jsonify({
    "status": "success", 
    "message": "Ingestion logs fetched successfully", 
    "status_code": 200, 
    "data": logs
})

    except Exception as e:
        sys_logger.log(f"Failed to fetch ingestion logs from DB: {e}", level="ERROR")
        return jsonify({"error": str(e)}), 500

def handle_trigger_scrape():
    from scheduler.scheduler import daily_scraping_task
    # Run the scraping task in a separate background thread to keep the endpoint non-blocking
    threading.Thread(target=lambda: daily_scraping_task(triggered_by="manual")).start()
    return jsonify({"status": "success", "message": "Scraping task triggered in the background."})

def handle_scheduler_status(scheduler=None):
    jobs = []
    next_run_time = None
    last_run = None
    
    conn = get_mysql_connection()
    if conn:
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT run_at, next_run_at, interval_hours, status, articles_processed, nodes_added, nodes_updated, edges_added, errors
                FROM scheduler_logs
                ORDER BY id DESC
                LIMIT 1
            """)
            row = cursor.fetchone()
            if row:
                if row.get('next_run_at'):
                    next_run_time = row['next_run_at'].isoformat()
                
                err_list = [e.strip() for e in row['errors'].split(';') if e.strip()] if row['errors'] else []
                last_run = {
                    "timestamp": row['run_at'].isoformat() if row['run_at'] else None,
                    "status": row['status'],
                    "articles_processed": [None] * (row['articles_processed'] or 0),
                    "nodes_added": row['nodes_added'],
                    "nodes_updated": row['nodes_updated'],
                    "edges_added": row['edges_added'],
                    "errors": err_list
                }
            cursor.close()
            conn.close()
        except Exception as e:
            sys_logger.log(f"Failed to fetch scheduler details from DB: {e}", level="ERROR")
            
    if not last_run:
        api_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        audit_file = os.path.join(api_dir, "storage", "audit_logs.jsonl")
        if os.path.exists(audit_file):
            try:
                with open(audit_file, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    if lines:
                        last_run = json.loads(lines[-1].strip())
            except Exception:
                pass
                
    if scheduler:
        for job in scheduler.get_jobs():
            nrt = job.next_run_time.isoformat() if job.next_run_time else None
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run_time": nrt
            })
            if job.id == "scraping_job" and not next_run_time and nrt:
                next_run_time = nrt

    active_interval = int(os.getenv("SCHEDULER_INTERVAL_HOURS", "6"))
    
    if last_run and last_run.get("timestamp"):
        try:
            last_dt = datetime.datetime.fromisoformat(last_run["timestamp"])
            next_dt = last_dt + datetime.timedelta(hours=active_interval)
            next_run_time = next_dt.isoformat()
        except Exception:
            pass

    return jsonify({
        "scheduler_running": scheduler.running if scheduler else False,
        "jobs": jobs,
        "last_run": last_run,
        "next_run_time": next_run_time,
        "interval_hours": active_interval
    })

def handle_get_scheduler_logs():
    limit = request.args.get('limit', 50, type=int)
    conn = get_mysql_connection()
    if not conn:
        return jsonify([])
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT id, run_at, next_run_at, interval_hours, status,
                   articles_processed, nodes_added, nodes_updated, edges_added,
                   errors, triggered_by, created_at
            FROM scheduler_logs
            ORDER BY id DESC
            LIMIT %s
        """, (limit,))
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        result = []
        for row in rows:
            r = dict(row)
            for key in ['run_at', 'next_run_at', 'created_at']:
                if r.get(key) and hasattr(r[key], 'isoformat'):
                    r[key] = r[key].isoformat()
                elif r.get(key) is None:
                    r[key] = None
            result.append(r)
        return jsonify({
    "status": "success", 
    "message": "Scheduler logs fetched successfully", 
    "status_code": 200, 
    "data": result
})

    except Exception as e:
        sys_logger.log(f"Failed to fetch scheduler logs from DB: {e}", level="ERROR")
        return jsonify({
    "status": "error", 
    "message": str(e), 
    "status_code": 500, 
    "data": []
})


# ==========================================
# 2. Scraping Pipeline Helpers & Sub-routines
# ==========================================

def get_scheduler_next_run():
    # Import locally from scheduler.scheduler to avoid circular dependency
    try:
        from scheduler.scheduler import get_scheduler_next_run
        return get_scheduler_next_run()
    except Exception:
        return None

def extract_proper_nouns(text):
    from prompts import get_extraction_prompt
    from services.llm_processor import call_llm_generate
    prompt = get_extraction_prompt(text)
    raw_output = call_llm_generate(prompt, format_json=True)
    try:
        return json.loads(raw_output)
    except Exception:
        return {"proper_nouns": []}

def extract_entities_and_relationships(text):
    from prompts import get_graph_extraction_prompt
    from services.llm_processor import call_llm_generate
    prompt = get_graph_extraction_prompt(text)
    raw_output = call_llm_generate(prompt, format_json=True)
    try:
        parsed_json = json.loads(raw_output)
        if "entities" not in parsed_json:
            parsed_json["entities"] = []
        if "relationships" not in parsed_json:
            parsed_json["relationships"] = []
        return parsed_json
    except Exception:
        return {"entities": [], "relationships": []}

def gather_knowledge_for_entity(name, category, wiki_summary):
    from prompts import get_knowledge_gathering_prompt
    from services.llm_processor import call_llm_generate
    prompt = get_knowledge_gathering_prompt(name, category, wiki_summary)
    response = call_llm_generate(prompt)
    return response if response else (wiki_summary or f"Entity {name} of category {category}.")

def fetch_wikipedia_summary(proper_noun):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    event_terms = ["world cup", "football", "fifa", "tournament", "olympics", "cricket", "championship", "match"]
    is_major_event = any(term in proper_noun.lower() for term in event_terms)
    search_limit = 3 if is_major_event else 1
    
    try:
        encoded_noun = urllib.parse.quote(proper_noun)
        if not is_major_event:
            wiki_url = f"https://en.wikipedia.org/w/api.php?action=query&format=json&titles={encoded_noun}&prop=extracts&explaintext=true&redirects=1"
            res = requests.get(wiki_url, headers=headers, timeout=8)
            if res.status_code == 200:
                data = res.json()
                pages = data.get("query", {}).get("pages", {})
                for page_id, page_data in pages.items():
                    if page_id != "-1" and "extract" in page_data:
                        return page_data["extract"]
                    
        search_url = f"https://en.wikipedia.org/w/api.php?action=query&format=json&list=search&srsearch={encoded_noun}&srlimit={search_limit}"
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

def fetch_online_knowledge(proper_noun):
    wiki_summary = fetch_wikipedia_summary(proper_noun)
    ddg_summary = ""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        encoded_noun = urllib.parse.quote(proper_noun)
        url = f"https://api.duckduckgo.com/?q={encoded_noun}&format=json&no_html=1"
        res = requests.get(url, headers=headers, timeout=8)
        if res.status_code == 200:
            data = res.json()
            abstract = data.get("AbstractText", "")
            if abstract:
                ddg_summary = abstract
            else:
                related = data.get("RelatedTopics", [])
                related_texts = [r["Text"] for r in related[:3] if isinstance(r, dict) and "Text" in r]
                if related_texts:
                    ddg_summary = "\n".join(related_texts)
    except Exception:
        pass

    combined = []
    if wiki_summary:
        combined.append(f"Wikipedia Context:\n{wiki_summary}")
    if ddg_summary:
        combined.append(f"Online Search Engine / Web Context:\n{ddg_summary}")
        
    if combined:
        return "\n\n---\n\n".join(combined)
    return wiki_summary or ""

def generate_graph_html(title, nodes_list, edges_list):
    category_config = {
        "Person": "#38bdf8",
        "Location": "#4ade80",
        "Organization": "#f472b6",
        "Event": "#fb923c",
        "Product & Tech": "#a78bfa",
        "Other": "#94a3b8"
    }
    
    def normalize_category(raw_cat):
        if not raw_cat:
            return "Other"
        raw_cat_lower = raw_cat.lower()
        if any(word in raw_cat_lower for word in ["person", "man", "woman", "player", "coach", "manager", "ceo", "striker", "midfielder", "member"]):
            return "Person"
        if any(word in raw_cat_lower for word in ["location", "place", "country", "city", "state", "town", "island", "airport"]):
            return "Location"
        if any(word in raw_cat_lower for word in ["organization", "company", "group", "firm", "association", "team", "club"]):
            return "Organization"
        if any(word in raw_cat_lower for word in ["event", "celebration", "war", "match", "cup", "game", "championship"]):
            return "Event"
        if any(word in raw_cat_lower for word in ["product", "technology", "tech", "aircraft", "device", "album", "song"]):
            return "Product & Tech"
        return "Other"
        
    vis_nodes = []
    vis_edges = []
    
    article_key = "article_" + "".join(c for c in title if c.isalnum())[:20]
    vis_nodes.append({
        "id": article_key,
        "label": title,
        "color": {
            "background": "#1e293b",
            "border": "#fb923c",
            "highlight": {"background": "#0f172a", "border": "#fb923c"}
        },
        "font": {"color": "#fb923c", "size": 14, "bold": True},
        "shape": "square",
        "size": 22,
        "borderWidth": 2
    })
    
    seen_node_keys = set([article_key])
    for e in nodes_list:
        name = e.get("name")
        if not name:
            continue
        key = "".join(c for c in name if c.isalnum())
        if key not in seen_node_keys:
            seen_node_keys.add(key)
            cat = e.get("category", "Other")
            norm_cat = normalize_category(cat)
            color = category_config.get(norm_cat, "#94a3b8")
            vis_nodes.append({
                "id": key,
                "label": name,
                "color": {
                    "background": color,
                    "border": "#0f172a"
                },
                "font": {"color": "#e2e8f0", "size": 12},
                "shape": "dot",
                "size": 15
            })
            
            vis_edges.append({
                "from": article_key,
                "to": key,
                "label": "mentions",
                "arrows": "to"
            })
            
    for r in edges_list:
        src = r.get("source")
        tgt = r.get("target")
        rel = r.get("relation", "")
        
        if src and tgt:
            src_key = "".join(c for c in src if c.isalnum())
            tgt_key = "".join(c for c in tgt if c.isalnum())
            
            if src_key in seen_node_keys and tgt_key in seen_node_keys:
                vis_edges.append({
                    "from": src_key,
                    "to": tgt_key,
                    "label": rel,
                    "arrows": "to"
                })
                
    nodes_json = json.dumps(vis_nodes, indent=4)
    edges_json = json.dumps(vis_edges, indent=4)
    
    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>Knowledge Graph - {title}</title>
    <script type="text/javascript" src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
    <style type="text/css">
        body {{
            background-color: #0f172a;
            color: #f8fafc;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 0;
            overflow: hidden;
        }}
        #header {{
            padding: 15px;
            background-color: #1e293b;
            border-bottom: 2px solid #334155;
            text-align: center;
        }}
        #mynetwork {{
            width: 100vw;
            height: calc(100vh - 80px);
            background-color: #0f172a;
        }}
    </style>
</head>
<body>
    <div id="header">
        <h1 style="margin:0;font-size:22px;color:#38bdf8;">Knowledge Graph: {title}</h1>
        <p style="margin:5px 0 0 0;font-size:13px;color:#94a3b8;">Interactive local view. Drag nodes, zoom in/out.</p>
    </div>
    <div id="mynetwork"></div>

    <script type="text/javascript">
        var nodesData = {nodes_json};
        var edgesData = {edges_json};

        var nodes = new vis.DataSet(nodesData);
        var edges = new vis.DataSet(edgesData);

        var container = document.getElementById('mynetwork');
        var graphData = {{
            nodes: nodes,
            edges: edges
        }};
        var options = {{
            nodes: {{
                shape: 'dot',
                size: 16,
                font: {{
                    size: 14,
                    color: '#ffffff'
                }},
                borderWidth: 2
            }},
            edges: {{
                color: {{
                    color: '#475569',
                    highlight: '#fb923c'
                }},
                width: 1.5,
                font: {{
                    align: 'middle',
                    color: '#94a3b8',
                    size: 10,
                    background: '#0f172a',
                    strokeWidth: 0
                }},
                arrows: {{
                    to: {{
                        enabled: true,
                        scaleFactor: 0.8
                    }}
                }},
                smooth: {{
                    type: 'continuous'
                }}
            }},
            physics: {{
                barnesHut: {{
                    gravitationalConstant: -4000,
                    centralGravity: 0.05,
                    springLength: 200,
                    springConstant: 0.04,
                    damping: 0.09
                }},
                stabilization: {{
                    iterations: 100
                }}
            }}
        }};
        var network = new vis.Network(container, graphData, options);
    </script>
</body>
</html>"""
    return html_content

def save_graph_to_file(title, url, published, entities, relationships):
    try:
        import dateutil.parser
        try:
            if published:
                dt = dateutil.parser.parse(published)
                date_str = dt.strftime("%Y-%m-%d")
            else:
                date_str = datetime.datetime.now().strftime("%Y-%m-%d")
        except Exception:
            date_str = datetime.datetime.now().strftime("%Y-%m-%d")
            
        api_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        target_dir = os.path.join(api_dir, "graph", date_str)
        os.makedirs(target_dir, exist_ok=True)
        
        sanitized_title = "".join(c for c in title if c.isalnum() or c in (" ", "_", "-")).strip().replace(" ", "_")
        if not sanitized_title:
            sanitized_title = hashlib.md5(url.encode()).hexdigest()
            
        file_path = os.path.join(target_dir, f"{sanitized_title}.json")
        
        unique_entities = []
        seen_entities = set()
        for e in entities:
            name = e.get("name")
            if name:
                key = name.lower().strip()
                if key not in seen_entities:
                    seen_entities.add(key)
                    unique_entities.append(e)
                    
        unique_relationships = []
        seen_rels = set()
        for r in relationships:
            src = r.get("source")
            tgt = r.get("target")
            rel = r.get("relation")
            if src and tgt:
                key = (src.lower().strip(), tgt.lower().strip(), (rel or "").lower().strip())
                if key not in seen_rels:
                    seen_rels.add(key)
                    unique_relationships.append(r)
                    
        output_data = {
            "article_title": title,
            "article_url": url,
            "publish_date": published,
            "entities": unique_entities,
            "relationships": unique_relationships
        }
        
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2)
            
        html_file_path = os.path.join(target_dir, f"{sanitized_title}.html")
        html_content = generate_graph_html(title, unique_entities, unique_relationships)
        with open(html_file_path, "w", encoding="utf-8") as f:
            f.write(html_content)
            
        sys_logger.log(f"Saved generated knowledge graph JSON & HTML to: {target_dir}", level="INFO")
    except Exception as e:
        sys_logger.log(f"Failed to save knowledge graph file: {e}", level="ERROR")

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
    if any(w in raw_type_lower for w in ["product", "technology", "tech", "aircraft", "device", "album", "song"]):
        return "Product & Tech"
    return "Other"

def is_valid_proper_noun(name, context):
    if not name or len(name.strip()) < 2:
        return False
    name_clean = name.strip().lower()
    stopwords = {"the", "a", "an", "this", "that", "it", "he", "she", "they", "we", "i", "you", "officer", "officers", "police", "news", "website"}
    if name_clean in stopwords:
        return False
    if not any(char.isalnum() for char in name):
        return False
    return True

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

def update_knowledge_graph_for_harvested_knowledge(db, url, title, article_id, c_name, category, gathered_knowledge, graph_data, published=None):
    entities = graph_data.get("entities", [])
    relationships = graph_data.get("relationships", [])
    
    collection_name = "ai_hub_entities"
    edge_collection_name = "ai_hub_relations"
    
    entities_coll = db.collection(collection_name)
    relations_coll = db.collection(edge_collection_name)
    
    timestamp = datetime.datetime.now().isoformat()
    
    nodes_added = 0
    nodes_updated = 0
    edges_added = 0
    
    main_hash = hashlib.md5(c_name.lower().encode()).hexdigest()
    main_key = f"ent_{main_hash}"
    main_category = normalize_node_type(category)
    
    main_claim = {
        "category": main_category,
        "confidence": 1.0,
        "source_url": url,
        "timestamp": timestamp
    }
    
    if entities_coll.has(main_key):
        existing = entities_coll.get(main_key)
        claims = existing.get("claims", [])
        if not any(c.get("source_url") == url and c.get("category") == main_category for c in claims):
            claims.append(main_claim)
        existing["claims"] = claims
        existing["timestamp"] = timestamp
        existing["description"] = gathered_knowledge
        
        urls = existing.get("source_urls", [])
        if url not in urls:
            urls.append(url)
        existing["source_urls"] = urls
        
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
            "_key": main_key,
            "name": c_name,
            "category": main_category,
            "confidence": 1.0,
            "source_urls": [url],
            "article_ids": [str(article_id) if article_id else ""],
            "timestamp": timestamp,
            "description": gathered_knowledge,
            "claims": [main_claim]
        }
        entities_coll.insert(new_entity)
        nodes_added += 1

    art_key = ensure_article_node_in_arango(db, url, title, article_id, published)
    
    edge_hash = hashlib.md5(f"{art_key}_{main_key}_mentions".encode()).hexdigest()
    edge_key = f"edge_{edge_hash}"
    edge_doc = {
        "_key": edge_key,
        "_from": f"{collection_name}/{art_key}",
        "_to": f"{collection_name}/{main_key}",
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
    if not relations_coll.has(edge_key):
        relations_coll.insert(edge_doc)
        edges_added += 1

    entity_keys_map = {c_name.lower(): main_key}
    
    for ent in entities:
        ent_name = ent.get("name")
        if not ent_name or len(ent_name.strip()) < 2:
            continue
            
        e_name = clean_name(ent_name)
        ent_category = normalize_node_type(ent.get("type", "Other"))
        confidence = float(ent.get("confidence", 1.0))
        
        ent_hash = hashlib.md5(e_name.lower().encode()).hexdigest()
        ent_key = f"ent_{ent_hash}"
        entity_keys_map[e_name.lower()] = ent_key
        
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
            
            urls = existing.get("source_urls", [])
            if url not in urls:
                urls.append(url)
            existing["source_urls"] = urls
            
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
                "name": e_name,
                "category": ent_category,
                "confidence": confidence,
                "source_urls": [url],
                "article_ids": [str(article_id) if article_id else ""],
                "timestamp": timestamp,
                "claims": [claim]
            }
            entities_coll.insert(new_entity)
            nodes_added += 1

        sub_edge_hash = hashlib.md5(f"{art_key}_{ent_key}_mentions".encode()).hexdigest()
        sub_edge_key = f"edge_{sub_edge_hash}"
        sub_edge_doc = {
            "_key": sub_edge_key,
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
        if not relations_coll.has(sub_edge_key):
            relations_coll.insert(sub_edge_doc)
            edges_added += 1

    for rel in relationships:
        src = rel.get("source")
        tgt = rel.get("target")
        label = rel.get("type", "related_to")
        confidence = float(rel.get("confidence", 1.0))
        
        if not src or not tgt:
            continue
            
        src_clean = clean_name(src).lower()
        tgt_clean = clean_name(tgt).lower()
        
        src_key = entity_keys_map.get(src_clean)
        tgt_key = entity_keys_map.get(tgt_clean)
        
        if not src_key:
            src_hash = hashlib.md5(src_clean.encode()).hexdigest()
            src_key = f"ent_{src_hash}"
        if not tgt_key:
            tgt_hash = hashlib.md5(tgt_clean.encode()).hexdigest()
            tgt_key = f"ent_{tgt_hash}"
            
        edge_hash = hashlib.md5(f"{src_key}_{tgt_key}_{label.lower()}".encode()).hexdigest()
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
    ensure_article_node_in_arango(db, url, title, article_id, published)
    
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
            
            urls = existing.get("source_urls", [])
            if url not in urls:
                urls.append(url)
            existing["source_urls"] = urls
            
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
        if not relations_coll.has(edge_key):
            relations_coll.insert(edge_doc)
            edges_added += 1

    for rel in relationships:
        src = rel.get("source")
        tgt = rel.get("target")
        label = rel.get("type", "related_to")
        confidence = float(rel.get("confidence", 1.0))
        
        if not src or not tgt:
            continue
            
        src_clean = clean_name(src).lower()
        tgt_clean = clean_name(tgt).lower()
        
        src_key = entity_keys_map.get(src_clean)
        tgt_key = entity_keys_map.get(tgt_clean)
        
        if not src_key:
            src_hash = hashlib.md5(src_clean.encode()).hexdigest()
            src_key = f"ent_{src_hash}"
        if not tgt_key:
            tgt_hash = hashlib.md5(tgt_clean.encode()).hexdigest()
            tgt_key = f"ent_{tgt_hash}"
            
        edge_hash = hashlib.md5(f"{src_key}_{tgt_key}_{label.lower()}".encode()).hexdigest()
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

def write_scheduler_log_to_mysql(run_at, next_run_at, interval_hours, status, articles_processed,
                                  nodes_added, nodes_updated, edges_added, errors, triggered_by="scheduler"):
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

def run_scraping_pipeline(triggered_by="scheduler"):
    nodes_added_count = 0
    nodes_updated_count = 0
    edges_added_count = 0
    processed_urls = []
    task_errors = []
    
    
    api_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    storage_dir = os.path.join(api_dir, "storage")
    os.makedirs(storage_dir, exist_ok=True)
    
    retry_file = os.path.join(storage_dir, "retry_scraping.json")
    audit_file = os.path.join(storage_dir, "audit_logs.jsonl")
    
    failed_items = []
    if os.path.exists(retry_file):
        try:
            with open(retry_file, "r", encoding="utf-8") as f:
                failed_items = json.load(f)
        except Exception as e:
            sys_logger.log(f"Error reading retry file: {e}", level="WARNING")

    connectors = []
    mysql_conn = get_mysql_connection()
    if mysql_conn:
        try:
            cursor = mysql_conn.cursor(dictionary=True)
            cursor.execute("SELECT url, type FROM connectors WHERE is_active = 1")
            connectors = cursor.fetchall()
            cursor.close()
            mysql_conn.close()
        except Exception as e:
            sys_logger.log(f"MySQL Error fetching active connectors: {e}", level="ERROR")
            task_errors.append(f"Connectors error: {str(e)}")
    
    if not connectors:
        sys_logger.log("No active connectors found in the database. Scraping pipeline skipped.", level="ERROR")
        task_errors.append("No active connectors registered.")
        
    rss_articles = []
    for conn in connectors:
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
                    rss_articles.extend(entries)
                else:
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
                
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                }
                
                response = None
                try:
                    import cloudscraper
                    scraper = cloudscraper.create_scraper()
                    response = scraper.get(url, headers=headers, timeout=10)
                except Exception:
                    try:
                        response = requests.get(url, headers=headers, timeout=10)
                    except Exception:
                        pass
                
                if response and response.status_code == 200:
                    from bs4 import BeautifulSoup
                    from urllib.parse import urljoin
                    soup = BeautifulSoup(response.content, 'html.parser')
                    
                    links_found = []
                    for a in soup.find_all('a', href=True):
                        href = a['href'].strip()
                        full_url = urljoin(url, href)
                        parsed_full = urlparse(full_url)
                        
                        if parsed_full.netloc == domain:
                            path_lower = parsed_full.path.lower()
                            if path_lower in ["", "/", "/index.html", "/index.php"]:
                                continue
                            if any(ext in path_lower for ext in [".png", ".jpg", ".jpeg", ".gif", ".pdf", ".css", ".js", ".zip"]):
                                continue
                            if any(nav in path_lower for nav in ["/login", "/register", "/signup", "/contact", "/about", "/privacy", "/terms", "/help", "/category", "/tags", "/search"]):
                                continue
                            
                            text = a.get_text().strip()
                            if len(path_lower.split('/')) > 2 or any(keyword in path_lower for keyword in ["/article", "/story", "/wiki/", "/p/", "/news/"]):
                                if full_url not in [l['link'] for l in links_found] and full_url.lower() != url.lower():
                                    title_text = text if len(text) > 10 else f"Sub-article from {domain}"
                                    links_found.append({
                                        "title": title_text,
                                        "link": full_url,
                                        "published": now_str,
                                        "summary": ""
                                    })
                                    
                    if len(links_found) > 0:
                        sys_logger.log(f"Extracted {len(links_found)} sub-article links from portal {url}. Adding top 5 to scraping queue.", level="INFO")
                        rss_articles.extend(links_found[:5])
                    else:
                        rss_articles.append({
                            "title": f"{label} from {domain}" if domain else f"{label} Scraping",
                            "link": url,
                            "published": now_str,
                            "summary": ""
                        })
                else:
                    rss_articles.append({
                        "title": f"{label} from {domain}" if domain else f"{label} Scraping",
                        "link": url,
                        "published": now_str,
                        "summary": ""
                    })
            except Exception as ex:
                sys_logger.log(f"Error handling webpage URL {url}: {ex}", level="ERROR")
                task_errors.append(f"Scraping error: {str(ex)}")

    stats_lock = threading.Lock()
    processed_count = 0

    def process_single_article_thread(entry):
        nonlocal processed_count, nodes_added_count, nodes_updated_count, edges_added_count
        _stats = [0, 0, 0]
        article_graph = {"entities": [], "relationships": []}
        graph_lock = threading.Lock()
        
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
            if thread_mysql_cursor:
                thread_mysql_cursor.execute("SELECT id FROM articles_meta WHERE source_url = %s", (url,))
                if thread_mysql_cursor.fetchone():
                    sys_logger.log(f"Article already processed (idempotency skip): {title}", level="INFO")
                    return
            else:
                return

            content = scrape_article_content(url)
            if not content and summary:
                content = summary
            if not content:
                sys_logger.log(f"Skipping article with no readable text: {title}", level="WARN")
                return

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

            if thread_arango_db:
                try:
                    ensure_article_node_in_arango(thread_arango_db, url, title, article_id, published)
                except Exception as e:
                    sys_logger.log(f"Failed to ensure Article Node in ArangoDB: {e}", level="ERROR")
                    has_failures = True
                    with stats_lock:
                        task_errors.append(f"ArangoDB article node creation error: {str(e)}")

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

            if proper_nouns_list:
                def process_single_keyword(pn_item):
                    nonlocal has_failures
                    c_name, category = pn_item
                    
                    sys_logger.log(f"Fetching online & Wikipedia summaries for proper noun '{c_name}'...", level="INFO")
                    online_knowledge = fetch_online_knowledge(c_name)
                    
                    sys_logger.log(f"Gathering/synthesizing knowledge for '{c_name}' using local LLM...", level="INFO")
                    gathered_knowledge = gather_knowledge_for_entity(c_name, category, online_knowledge)
                    if not gathered_knowledge:
                        gathered_knowledge = online_knowledge or f"Entity {c_name} of category {category}."
                    
                    extracted_graph_data = {"entities": [], "relationships": []}
                    sub_arango_db = get_arango_db()
                    if sub_arango_db:
                        try:
                            sys_logger.log(f"Extracting entities & relations from gathered knowledge of '{c_name}'...", level="INFO")
                            extracted_graph_data = extract_entities_and_relationships(gathered_knowledge[:2000])
                            with graph_lock:
                                article_graph["entities"].extend(extracted_graph_data.get("entities", []))
                                article_graph["relationships"].extend(extracted_graph_data.get("relationships", []))
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

                nodes_added_count += _stats[0]
                nodes_updated_count += _stats[1]
                edges_added_count += _stats[2]
            else:
                if thread_arango_db:
                    try:
                        sys_logger.log(f"No proper nouns extracted. Generating knowledge graph directly from article content...", level="INFO")
                        extracted_graph_data = extract_entities_and_relationships(content[:2000])
                        with graph_lock:
                            article_graph["entities"].extend(extracted_graph_data.get("entities", []))
                            article_graph["relationships"].extend(extracted_graph_data.get("relationships", []))
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
            if has_failures and article_id:
                sys_logger.log(f"Article '{title}' had processing warnings/failures but is preserved in MySQL metadata.", level="INFO")
            
            if article_graph["entities"] or article_graph["relationships"]:
                save_graph_to_file(title, url, published, article_graph["entities"], article_graph["relationships"])

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

    if rss_articles:
        with ThreadPoolExecutor(max_workers=3) as executor:
            executor.map(process_single_article_thread, rss_articles)

    # 4. Retry failed updates
    still_failed = []
    retry_arango_db = get_arango_db()
    if failed_items and retry_arango_db:
        sys_logger.log(f"Retrying {len(failed_items)} failed graph updates...", level="INFO")
        for item in failed_items:
            try:
                retry_graph = {"entities": [], "relationships": []}
                extracted_pns_data = extract_proper_nouns(item["content"][:2000])
                extracted_pns = extracted_pns_data.get("proper_nouns", [])
                for pn in extracted_pns:
                    raw_name = pn.get("name")
                    category = pn.get("category", "Other")
                    if is_valid_proper_noun(raw_name, item["content"]):
                        c_name = clean_name(raw_name)
                        online_knowledge = fetch_online_knowledge(c_name)
                        gathered_knowledge = gather_knowledge_for_entity(c_name, category, online_knowledge)
                        if not gathered_knowledge:
                            gathered_knowledge = online_knowledge or f"Entity {c_name} of category {category}."
                        extracted_graph_data = extract_entities_and_relationships(gathered_knowledge[:2000])
                        retry_graph["entities"].extend(extracted_graph_data.get("entities", []))
                        retry_graph["relationships"].extend(extracted_graph_data.get("relationships", []))
                        n_added, n_updated, e_added = update_knowledge_graph_for_harvested_knowledge(
                            retry_arango_db, item["url"], item["title"], item.get("article_id"), c_name, category, gathered_knowledge, extracted_graph_data, item.get("published", "")
                        )
                        nodes_added_count += n_added
                        nodes_updated_count += n_updated
                        edges_added_count += e_added
                if retry_graph["entities"] or retry_graph["relationships"]:
                    save_graph_to_file(item["title"], item["url"], item.get("published", ""), retry_graph["entities"], retry_graph["relationships"])
                sys_logger.log(f"Successfully retried graph update for {item['title']}", level="SUCCESS")
            except Exception as e:
                sys_logger.log(f"Retry failed for {item['title']}: {e}", level="ERROR")
                still_failed.append(item)
    else:
        still_failed = failed_items

    try:
        with open(retry_file, "w", encoding="utf-8") as f:
            json.dump(still_failed, f, indent=2)
    except Exception as e:
        sys_logger.log(f"Error saving retry file: {e}", level="ERROR")

    # Audit Logs
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

    next_run_iso = get_scheduler_next_run()
    interval_h = int(os.getenv("SCHEDULER_INTERVAL_HOURS", "6"))
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
        triggered_by=triggered_by
    )
