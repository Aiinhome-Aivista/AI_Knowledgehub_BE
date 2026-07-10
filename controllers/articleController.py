from flask import jsonify
from database.dbConnection import get_mysql_connection

def handle_get_articles():
    conn = get_mysql_connection()
    if not conn:
        return jsonify([])
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, title, source_url, created_at FROM articles_meta ORDER BY id DESC")
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        
        formatted_rows = []
        for row in rows:
            r = dict(row)
            if r.get("created_at") and hasattr(r["created_at"], "isoformat"):
                r["created_at"] = r["created_at"].isoformat()
            formatted_rows.append(r)
            
        return jsonify(formatted_rows)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
