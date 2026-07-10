from flask import jsonify
from database.dbConnection import get_mysql_connection

def handle_topics():
    """
    Retrieves distinct topics and categories from MySQL.
    """
    conn = get_mysql_connection()
    if not conn:
        return jsonify({"status": "error", "message": "Database connection failed", "status_code": 500})
        
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT DISTINCT name, category FROM topics ORDER BY name ASC")
        topics = cursor.fetchall()
        cursor.close()
        conn.close()
        return jsonify({"status": "success", "message":"Topics fetched successfully", "status_code":200, "data":topics})
    except Exception as e:
        print(f"Error fetching topics: {e}")
        return jsonify({"status": "error", "message": str(e), "status_code": 500})
