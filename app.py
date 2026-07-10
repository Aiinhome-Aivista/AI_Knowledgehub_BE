from flask import Flask, jsonify, send_file, request
from flask_cors import CORS
import os
import sys
from dotenv import load_dotenv

# Ensure correct path resolution
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from scheduler.scheduler import init_scheduler
from controllers.chatController import handle_chat
from controllers.topicsController import handle_topics
from controllers.logController import handle_stream_logs
from controllers.graphController import handle_graph_data
from utils.settings_manager import load_settings, save_settings
from utils.logger import sys_logger

# Load environment variables
load_dotenv()

scheduler = None

app = Flask(__name__)
CORS(app)  # Enable CORS for the UI

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json or {}
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")
    
    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400
        
    from database.dbConnection import get_mysql_connection
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

@app.route('/api/stream-logs')
def stream_logs():
    return handle_stream_logs()

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({"status": "running"})

@app.route('/api/topics', methods=['GET'])
def get_topics():
    return handle_topics()

@app.route('/api/chat', methods=['POST'])
def chat():
    return handle_chat()

@app.route('/api/graph-data', methods=['GET'])
def graph_data():
    return handle_graph_data()

@app.route('/graph', methods=['GET'])
def view_graph():
    return send_file(os.path.join(os.path.dirname(os.path.abspath(__file__)), "graph.html"))

@app.route('/api/settings', methods=['GET', 'POST'])
def handle_api_settings():
    global scheduler
    if request.method == 'GET':
        return jsonify(load_settings())
    
    settings = request.json
    if not settings:
        return jsonify({"error": "Invalid payload"}), 400
        
    if save_settings(settings):
        # Dynamically reschedule APScheduler job if scheduler is running
        if scheduler:
            try:
                job = scheduler.get_job("scraping_job")
                if job:
                    new_interval = settings.get("scheduler_interval_hours", 6)
                    from scheduler.scheduler import get_next_run_time
                    start_time = get_next_run_time(new_interval)
                    job.reschedule(trigger='interval', hours=new_interval, start_date=start_time)
                    sys_logger.log(f"Rescheduled scraping job to run every {new_interval} hours. Next run at: {start_time.strftime('%Y-%m-%d %H:%M:%S')}", level="SYSTEM")
            except Exception as e:
                sys_logger.log(f"Failed to reschedule scraping job: {e}", level="ERROR")
        return jsonify({"status": "success", "message": "Settings updated successfully."})
    return jsonify({"error": "Failed to save settings"}), 500

@app.route('/api/connectors', methods=['GET', 'POST'])
def handle_api_connectors():
    from database.dbConnection import get_mysql_connection
    if request.method == 'GET':
        conn = get_mysql_connection()
        if not conn:
            return jsonify([])
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT id, url, type FROM connectors")
            rows = cursor.fetchall()
            cursor.close()
            conn.close()
            return jsonify(rows)
        except Exception as e:
            sys_logger.log(f"Failed to fetch connectors from DB: {e}", level="ERROR")
            return jsonify({"error": str(e)}), 500
    
    connectors = request.json
    if not isinstance(connectors, list):
        return jsonify({"error": "Payload must be a list of connectors"}), 400
        
    conn = get_mysql_connection()
    if not conn:
        return jsonify({"error": "Database connection error"}), 500
    try:
        import hashlib
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
        return jsonify({"status": "success", "message": "Connectors updated successfully."})
    except Exception as e:
        sys_logger.log(f"Failed to save connectors to DB: {e}", level="ERROR")
        return jsonify({"error": str(e)}), 500

@app.route('/api/test-llm', methods=['POST'])
def test_llm():
    data = request.json or {}
    url = data.get("llm_url")
    model = data.get("llm_model")
    if not url or not model:
        return jsonify({"success": False, "message": "URL and Model are required"}), 400
    
    payload = {
        "model": model,
        "prompt": "Hello",
        "stream": False,
        "keep_alive": 1
    }
    try:
        import requests
        res = requests.post(f"{url}/api/generate", json=payload, timeout=5)
        if res.status_code == 200:
            return jsonify({"success": True, "message": f"Successfully connected to LLM and verified model '{model}'."})
        else:
            return jsonify({"success": False, "message": f"Server returned status code {res.status_code}."})
    except Exception as e:
        return jsonify({"success": False, "message": f"Connection failed: {str(e)}"})

@app.route('/api/articles', methods=['GET'])
def get_articles():
    from database.dbConnection import get_mysql_connection
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

@app.route('/api/ingestion-logs', methods=['GET'])
def get_ingestion_logs():
    from database.dbConnection import get_mysql_connection
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
            # Map database semicolon separated string to array of errors for UI
            err_list = [e.strip() for e in row['errors'].split(';') if e.strip()] if row['errors'] else []
            logs.append({
                "timestamp": row['run_at'].isoformat() if row['run_at'] else row['created_at'].isoformat(),
                "status": row['status'],
                # Convert articles count integer to list of None values so the UI's .length check works perfectly
                "articles_processed": [None] * (row['articles_processed'] or 0),
                "nodes_added": row['nodes_added'],
                "nodes_updated": row['nodes_updated'],
                "edges_added": row['edges_added'],
                "errors": err_list
            })
        return jsonify(logs)
    except Exception as e:
        sys_logger.log(f"Failed to fetch ingestion logs from DB: {e}", level="ERROR")
        return jsonify({"error": str(e)}), 500


@app.route('/api/landing-data', methods=['GET'])
def get_landing_data():
    from database.dbConnection import get_mysql_connection, get_arango_db
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
        except Exception as ex:
            pass
    except Exception as e:
        sys_logger.log(f"Failed to fetch landing page data: {e}", level="ERROR")
        return jsonify({"error": str(e)}), 500
    return jsonify(db_data)

@app.route('/api/trigger-scrape', methods=['POST'])
def trigger_scrape():
    import threading
    from scheduler.scheduler import daily_scraping_task
    # Run the scraping task in a separate background thread to keep the endpoint non-blocking
    threading.Thread(target=lambda: daily_scraping_task(triggered_by="manual")).start()
    return jsonify({"status": "success", "message": "Scraping task triggered in the background."})

@app.route('/api/scheduler-status', methods=['GET'])
def scheduler_status():
    global scheduler
    jobs = []
    
    # 1. Fetch next run time, last execution, and interval dynamically from MySQL scheduler_logs
    next_run_time = None
    last_run = None
    interval_hours = 6
    
    from database.dbConnection import get_mysql_connection
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
                interval_hours = row.get('interval_hours', 6)
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
            
    # Fallback to local file if DB query returned nothing
    if not last_run:
        audit_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "storage", "audit_logs.jsonl")
        if os.path.exists(audit_file):
            try:
                import json
                with open(audit_file, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    if lines:
                        last_run = json.loads(lines[-1].strip())
            except Exception:
                pass
                
    # 2. Get running job details if next_run_time was not resolved from DB
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

    # 3. Dynamically calculate next run time using active interval from settings and last DB run timestamp
    settings = load_settings()
    active_interval = settings.get("scheduler_interval_hours", 6)
    
    if last_run and last_run.get("timestamp"):
        import datetime
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

@app.route('/api/scheduler-logs', methods=['GET'])
def get_scheduler_logs():
    from database.dbConnection import get_mysql_connection
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
        # Convert datetime fields to ISO strings for JSON serialisation
        result = []
        for row in rows:
            r = dict(row)
            for key in ['run_at', 'next_run_at', 'created_at']:
                if r.get(key) and hasattr(r[key], 'isoformat'):
                    r[key] = r[key].isoformat()
                elif r.get(key) is None:
                    r[key] = None
            result.append(r)
        return jsonify(result)
    except Exception as e:
        sys_logger.log(f"Failed to fetch scheduler logs from DB: {e}", level="ERROR")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # Initialize the background scheduler only when run directly
    scheduler = init_scheduler()
    
    # Open default browser on startup
    try:
        import webbrowser
        import threading
        import time
        def open_browser():
            time.sleep(1.5) # Wait for Flask server to boot up
            webbrowser.open("http://localhost:5000/graph")
        threading.Thread(target=open_browser).start()
    except Exception as e:
        print(f"Could not open browser: {e}")
        
    # Use threaded=True to allow the background scheduler to run smoothly
    app.run(host='0.0.0.0', port=5000, threaded=True)
