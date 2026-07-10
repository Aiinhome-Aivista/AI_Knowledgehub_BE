from flask import request, jsonify
from database.dbConnection import get_mysql_connection

def handle_login():
    data = request.json or {}
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")
    
    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400
        
    conn = get_mysql_connection()
    if not conn:
        return jsonify({"error": "Database connection error"}), 500
        
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
            return jsonify({"status": "success", "role": user["role"], "name": user.get("name", "") or ""})
        else:
            return jsonify({"error": "Invalid email or password. Access denied."}), 401
    except Exception as e:
        return jsonify({"error": str(e)}), 500
