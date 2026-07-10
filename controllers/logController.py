from flask import Response
from utils.logger import sys_logger

def handle_stream_logs():
    """
    SSE handler to stream backend logs to client.
    """
    def generate():
        q = sys_logger.listen()
        try:
            while True:
                # Get log from queue, wait up to 10 seconds to send a heartbeat
                try:
                    msg = q.get(timeout=10)
                    yield f"data: {msg}\n\n"
                except Exception:
                    # Heartbeat to keep connection alive
                    yield ": heartbeat\n\n"
        finally:
            sys_logger.stop_listen(q)
            
    return Response(generate(), mimetype='text/event-stream')
