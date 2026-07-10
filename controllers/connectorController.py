import hashlib
from flask import request, jsonify
from database.dbConnection import get_mysql_connection
from utils.logger import sys_logger

def handle_api_connectors():
    if request.method == 'GET':
        conn = get_mysql_connection()
        if not conn:
            return jsonify({"status": "error", "message": "Database connection error", "status_code": 500, "data": []})
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT id, url, type FROM connectors")
            rows = cursor.fetchall()
            cursor.close()
            conn.close()
            return jsonify({"status": "success", "message": "Connectors fetched successfully", "status_code": 200, "data": rows})
        except Exception as e:
            sys_logger.log(f"Failed to fetch connectors from DB: {e}", level="ERROR")
            return jsonify({"status": "error", "message": str(e), "status_code": 500, "data": []})
    
    connectors = request.json
    if not isinstance(connectors, list):
        return jsonify({"status": "error", "message": "Payload must be a list of connectors", "status_code": 400, "data": []})
        
    conn = get_mysql_connection()
    if not conn:
        return jsonify({"status": "error", "message": "Database connection error", "status_code": 500, "data": []})
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM connectors")
        for conn_data in connectors:
            url = conn_data.get("url", "").strip()
            c_type = conn_data.get("type", "rss").strip()
            # Auto-generate id if missing or empty so connectors always get saved
            c_id = conn_data.get("id", "").strip()
            if not c_id:
                c_id = f"conn_{hashlib.md5(url.encode()).hexdigest()}"
            if url:
                cursor.execute(
                    "INSERT IGNORE INTO connectors (id, url, type) VALUES (%s, %s, %s)",
                    (c_id, url, c_type)
                )
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"status": "success", "message": "Connectors updated successfully.", "status_code": 200})
    except Exception as e:
        sys_logger.log(f"Failed to save connectors to DB: {e}", level="ERROR")
        return jsonify({"status": "error", "message": str(e), "status_code": 500, "data": []})
