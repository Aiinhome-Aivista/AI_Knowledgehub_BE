import queue
import datetime
import threading

class SystemLogger:
    def __init__(self):
        self.listeners = []
        self.lock = threading.Lock()
        
        # Keep a small history to send to new clients
        self.history = []
        self.history_limit = 50

    def listen(self):
        q = queue.Queue(maxsize=100)
        
        with self.lock:
            # Send history first
            for msg in self.history:
                try:
                    q.put_nowait(msg)
                except queue.Full:
                    pass
            self.listeners.append(q)
            
        return q

    def stop_listen(self, q):
        with self.lock:
            if q in self.listeners:
                self.listeners.remove(q)

    def log(self, message, level="INFO"):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        log_msg = f"[{timestamp}] [{level}] {message}"
        
        # Print to actual console as well
        print(log_msg)
        
        with self.lock:
            self.history.append(log_msg)
            if len(self.history) > self.history_limit:
                self.history.pop(0)
                
            for q in self.listeners:
                try:
                    q.put_nowait(log_msg)
                except queue.Full:
                    pass

# Global singleton instance
sys_logger = SystemLogger()
