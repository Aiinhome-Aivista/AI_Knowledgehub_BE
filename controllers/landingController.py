from flask import jsonify
from database.dbConnection import get_mysql_connection, get_arango_db
from utils.logger import sys_logger

def handle_get_landing_data():
    conn = get_mysql_connection()
    db_data = {
        "top_keywords": [],
        "most_searched": [],
        "most_written": [],
        "data_coverage": {
            "total_articles": 0,
            "total_connectors": 0,
            "total_topics": 0,
            "arango_nodes": 0,
            "arango_edges": 0
        }
    }
    if not conn:
        return jsonify(db_data)
    try:
        cursor = conn.cursor(dictionary=True)
        # 1. Top Keywords Found — top 30, frontend paginates 10 per page
        cursor.execute("SELECT id, name, category, created_at FROM topics ORDER BY id DESC LIMIT 30")
        db_data["top_keywords"] = cursor.fetchall()
        
        # 2. Most Searched Items
        cursor.execute("SELECT query, count FROM search_logs ORDER BY count DESC LIMIT 10")
        db_data["most_searched"] = cursor.fetchall()
        
        # 3. Most Written About
        cursor.execute("""
            SELECT t.name, COUNT(at.article_id) as count 
            FROM topics t 
            JOIN article_topics at ON t.id = at.topic_id 
            GROUP BY t.id, t.name 
            ORDER BY count DESC 
            LIMIT 10
        """)
        db_data["most_written"] = cursor.fetchall()
        
        # 4. Data Coverage stats
        cursor.execute("SELECT COUNT(*) as count FROM articles_meta")
        db_data["data_coverage"]["total_articles"] = cursor.fetchone()["count"]
        
        cursor.execute("SELECT COUNT(*) as count FROM connectors")
        db_data["data_coverage"]["total_connectors"] = cursor.fetchone()["count"]
        
        cursor.execute("SELECT COUNT(*) as count FROM topics")
        db_data["data_coverage"]["total_topics"] = cursor.fetchone()["count"]
        
        cursor.close()
        conn.close()
        
        try:
            arango_db = get_arango_db()
            if arango_db:
                if arango_db.has_collection("ai_hub_entities"):
                    db_data["data_coverage"]["arango_nodes"] = arango_db.collection("ai_hub_entities").count()
                if arango_db.has_collection("ai_hub_relations"):
                    db_data["data_coverage"]["arango_edges"] = arango_db.collection("ai_hub_relations").count()
        except Exception:
            pass
    except Exception as e:
        sys_logger.log(f"Failed to fetch landing page data: {e}", level="ERROR")
        return jsonify({
    "status": "error", 
    "message": str(e), 
    "status_code": 500, 
    "data": db_data
})

    return jsonify(db_data)
