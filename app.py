from flask import Flask, jsonify, request
from flask_cors import CORS
import os
import sys
from dotenv import load_dotenv
from scheduler.scheduler import get_next_run_time, daily_scraping_task
import scheduler.scheduler as scheduler_module

# Ensure correct path resolution
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from controllers.chatController import handle_chat
from controllers.topicsController import handle_topics
from controllers.logController import handle_stream_logs
from controllers.graphController import handle_graph_data, handle_view_graph
from controllers.authController import handle_login
from controllers.connectorController import handle_api_connectors
from controllers.articleController import handle_get_articles
from controllers.schedulerController import (
    handle_get_ingestion_logs, 
    handle_trigger_scrape, 
    handle_scheduler_status, 
    handle_get_scheduler_logs
)
from controllers.landingController import handle_get_landing_data

# Load environment variables
load_dotenv()

scheduler = None

app = Flask(__name__)
CORS(app)  # Enable CORS for the UI

@app.route('/login', methods=['POST'])
def login():
    return handle_login()

@app.route('/stream-logs')
def stream_logs():
    return handle_stream_logs()

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "running", "message":"Server is running", "status_code":200})

@app.route('/topics', methods=['GET'])
def get_topics():
    return handle_topics()

@app.route('/chat', methods=['POST'])
def chat():
    return handle_chat()

@app.route('/graph-data', methods=['GET'])
def graph_data():
    return handle_graph_data()

@app.route('/graph', methods=['GET'])
def view_graph():
    return handle_view_graph()

@app.route('/connectors', methods=['GET', 'POST'])
def handle_api_connectors_route():
    return handle_api_connectors()

@app.route('/articles', methods=['GET'])
def get_articles():
    return handle_get_articles()

@app.route('/ingestion-logs', methods=['GET'])
def get_ingestion_logs():
    return handle_get_ingestion_logs()

@app.route('/landing-data', methods=['GET'])
def get_landing_data():
    return handle_get_landing_data()

@app.route('/trigger-scrape', methods=['POST'])
def trigger_scrape():
    return handle_trigger_scrape()

@app.route('/scheduler-status', methods=['GET'])
def scheduler_status():
    return handle_scheduler_status(scheduler)

@app.route('/scheduler-logs', methods=['GET'])
def get_scheduler_logs():
    return handle_get_scheduler_logs()

if __name__ == '__main__':
    # Initialize the background scheduler directly here
    from apscheduler.schedulers.background import BackgroundScheduler
    scheduler = BackgroundScheduler()
    interval = int(os.getenv("SCHEDULER_INTERVAL_HOURS", "6"))
    
    start_time = get_next_run_time(interval)
    
    scheduler.add_job(
        func=daily_scraping_task, 
        trigger="interval", 
        hours=interval,
        start_date=start_time,
        id="scraping_job"
    )
    scheduler.start()
    
    # Share the scheduler instance globally with scheduler module
    scheduler_module._scheduler = scheduler
    
    from utils.logger import sys_logger
    sys_logger.log(f"Scheduler initialized directly in app.py to run every {interval} hours. Next automated run scheduled for: {start_time.strftime('%Y-%m-%d %H:%M:%S')}.", level="SYSTEM")
    
    # Start Flask application with debug=True
    app.run(host="0.0.0.0", port=3019, debug=True)
