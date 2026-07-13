import datetime
import os
import sys
import threading
from database.dbConnection import get_mysql_connection
from utils.logger import sys_logger

_scraping_lock = threading.Lock()
_scheduler = None
_scheduler_next_run = None
_current_triggered_by = "scheduler"

def get_scheduler_next_run():
    """Returns the next scheduled run time as an ISO string, or None."""
    global _scheduler, _scheduler_next_run
    if _scheduler:
        try:
            job = _scheduler.get_job("scraping_job")
            if job and job.next_run_time:
                _scheduler_next_run = job.next_run_time.isoformat()
                return _scheduler_next_run
        except Exception:
            pass
    return _scheduler_next_run

def get_next_run_time(interval_hours):
    """Calculates the next run time relative to the last successful scrape execution recorded in database/audit logs."""
    last_run_time = None
    
    # Try database first
    try:
        conn = get_mysql_connection()
        if conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT run_at FROM scheduler_logs 
                WHERE status = 'SUCCESS' OR status = 'PARTIAL_FAILURE'
                ORDER BY id DESC LIMIT 1
            """)
            row = cursor.fetchone()
            if row and row[0]:
                last_run_time = row[0]
            cursor.close()
            conn.close()
    except Exception as e:
        sys_logger.log(f"Failed to fetch last run time from MySQL for next run calculation: {e}", level="WARNING")

    # Fallback to audit_logs.jsonl
    if not last_run_time:
        storage_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "storage")
        audit_file = os.path.join(storage_dir, "audit_logs.jsonl")
        if os.path.exists(audit_file):
            try:
                with open(audit_file, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    if lines:
                        import json
                        last_entry = json.loads(lines[-1].strip())
                        last_run_time_str = last_entry.get("timestamp")
                        if last_run_time_str:
                            last_run_time = datetime.datetime.fromisoformat(last_run_time_str.split(".")[0])
            except Exception:
                pass
                
    now = datetime.datetime.now()
    if last_run_time:
        next_run = last_run_time + datetime.timedelta(hours=interval_hours)
        if next_run < now:
            return now + datetime.timedelta(seconds=5)
        return next_run
    return now + datetime.timedelta(seconds=5)


def daily_scraping_task(triggered_by="scheduler"):
    global _current_triggered_by
    if not _scraping_lock.acquire(blocking=False):
        sys_logger.log("Scraping task is already running in another thread. Skipping this execution.", level="INFO")
        return
    _current_triggered_by = triggered_by
    try:
        from controllers.schedulerController import run_scraping_pipeline
        run_scraping_pipeline(triggered_by)
    finally:
        _scraping_lock.release()
