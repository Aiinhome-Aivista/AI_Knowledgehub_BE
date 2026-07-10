from flask import jsonify
from database.dbConnection import get_arango_db

def handle_graph_data():
    db = get_arango_db()
    if not db:
        return jsonify({"nodes": [], "edges": []})
        
    try:
        collection_name = "ai_hub_entities"
        edge_collection = "ai_hub_relations"
        
        entities = []
        edges = []
        
        # 1. Fetch the latest edges first from ArangoDB (no limits)
        if db.has_collection(edge_collection):
            edge_cursor = db.aql.execute(f"""
                FOR doc IN {edge_collection} 
                SORT doc.timestamp DESC 
                RETURN doc
            """)
            edges = list(edge_cursor)
            
        # 2. Extract all unique keys referenced by the fetched edges
        node_keys = set()
        for edge in edges:
            from_key = edge["_from"].split("/")[-1]
            to_key = edge["_to"].split("/")[-1]
            node_keys.add(from_key)
            node_keys.add(to_key)
            
        # 3. Fetch ONLY the nodes that are connected by these edges
        if db.has_collection(collection_name):
            if node_keys:
                cursor = db.aql.execute(
                    f"FOR doc IN {collection_name} FILTER doc._key IN @keys RETURN doc",
                    bind_vars={"keys": list(node_keys)}
                )
                entities = list(cursor)
            else:
                # Fallback if there are no edges: return all entities to avoid blank screen (no limits)
                cursor = db.aql.execute(f"FOR doc IN {collection_name} RETURN doc")
                entities = list(cursor)
            
        # Color mapping for different category nodes
        category_config = {
            "Person": "#38bdf8",          # Neon Blue
            "Location": "#4ade80",        # Neon Green
            "Organization": "#f472b6",    # Neon Pink
            "Event": "#fb923c",            # Neon Orange
            "Product & Tech": "#a78bfa",   # Neon Purple
            "Other": "#94a3b8"             # Neon Gray
        }
        
        def normalize_category(raw_cat):
            if not raw_cat:
                return "Other"
            raw_cat_lower = raw_cat.lower()
            if any(word in raw_cat_lower for word in ["person", "man", "woman", "midfielder", "striker", "musician", "singer", "member", "people", "age", "player", "manager", "coach", "profession", "hooligan"]):
                return "Person"
            if any(word in raw_cat_lower for word in ["location", "place", "country", "city", "island", "state", "town", "capital", "airport", "sea", "ocean"]):
                return "Location"
            if any(word in raw_cat_lower for word in ["organization", "company", "group", "band", "firm", "association", "depot", "navy", "military", "club", "team", "force"]):
                return "Organization"
            if any(word in raw_cat_lower for word in ["event", "celebration", "war", "match", "cup", "hiatus", "storm", "typhoon", "election", "game"]):
                return "Event"
            if any(word in raw_cat_lower for word in ["product", "technology", "tech", "aircraft", "bomber", "album", "single", "song", "device", "vessel", "ship", "battleship", "concept"]):
                return "Product & Tech"
            return "Other"
            
        def wrap_text(text, width=20):
            if not text:
                return ""
            words = text.split()
            lines = []
            current_line = []
            current_length = 0
            for word in words:
                if current_length + len(word) > width:
                    lines.append(" ".join(current_line))
                    current_line = [word]
                    current_length = len(word)
                else:
                    current_line.append(word)
                    current_length += len(word) + 1
            if current_line:
                lines.append(" ".join(current_line))
            return "\n".join(lines)
            
        nodes_list = []
        edges_list = []
        
        # Populate nodes list
        for doc in entities:
            key = doc["_key"]
            name = doc.get("name", key)
            cat = doc.get("category", "Other")
            
            if cat == "Article":
                # Articles are represented as distinctive orange square nodes
                nodes_list.append({
                    "id": key,
                    "label": wrap_text(name, 22),
                    "color": {
                        "background": "#1e293b",
                        "border": "#fb923c",
                        "highlight": {"background": "#0f172a", "border": "#fb923c"}
                    },
                    "font": {"color": "#fb923c", "size": 13, "bold": True},
                    "shape": "square",
                    "size": 22,
                    "borderWidth": 2
                })
            else:
                # Entities are standard colorful circular nodes
                norm_cat = normalize_category(cat)
                color = category_config.get(norm_cat, "#94a3b8")
                nodes_list.append({
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
                
        # Populate edges list
        for edge in edges:
            from_id = edge["_from"].split("/")[-1]
            to_id = edge["_to"].split("/")[-1]
            label = edge.get("label", "")
            
            edges_list.append({
                "from": from_id,
                "to": to_id,
                "label": label,
                "arrows": "to"
            })
            
        return jsonify({"nodes": nodes_list, "edges": edges_list})
    except Exception as e:
        return jsonify({"error": str(e), "nodes": [], "edges": []})
