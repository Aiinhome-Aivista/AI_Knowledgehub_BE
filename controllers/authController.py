from flask import request, jsonify
from database.dbConnection import get_mysql_connection

def handle_login():
    data = request.json or {}
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")
    
    if not email or not password:
        return jsonify({"status": "error", "message":"Email and password are required", "status_code":400})
        
    conn = get_mysql_connection()
    if not conn:
        return jsonify({"status": "error", "message":"Database connection error", "status_code":500})
        
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT r.role_name AS role, u.name 
            FROM users u
            JOIN roles r ON u.role_id = r.role_id
            WHERE u.email = %s AND u.password = %s
        """, (email, password))
        user = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if user:
            return jsonify({"status": "success", "message":"Login successfully", "status_code":200, "data":{"role": user["role"], "name": user.get("name", "") or ""}})
        else:
            return jsonify({"status": "error", "message":"Invalid email or password. Access denied.", "status_code":401})
    except Exception as e:
        return jsonify({"status": "error", "message":str(e), "status_code":500})
