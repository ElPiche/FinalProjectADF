"""utils.py - Enhanced dual logging system for KB-MCP

Provides non-blocking structured logging to both file (always) and MongoDB (best effort).
Maintains backward compatibility with existing log_message() calls.
"""

import logging
import sys
import os
import json
import uuid
import threading
import queue
import time
from datetime import datetime
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict
from contextlib import contextmanager
import inspect

# Configuration
LOGS_DIR = "logs"
LOG_FILE = "kb-mcp.log"
STRUCTURED_LOG_FILE = "structured_logs.jsonl"
QUEUE_SIZE = 1000
BATCH_SIZE = 10
FLUSH_INTERVAL = 1.0  # seconds


@dataclass
class LogEntry:
    """Structured log entry matching original MongoDB schema."""
    timestamp: str
    session_id: str
    level: str
    component: str
    method: str
    message: str
    request_id: Optional[str] = None
    duration_ms: Optional[float] = None
    extra_data: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data = asdict(self)
        if data['extra_data'] is None:
            data['extra_data'] = {}
        return data

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict())


class FileLogger:
    """Handles file logging operations."""
    
    def __init__(self, logs_dir: str = LOGS_DIR):
        self.logs_dir = logs_dir
        self.log_file_path = os.path.join(logs_dir, LOG_FILE)
        self.structured_log_path = os.path.join(logs_dir, STRUCTURED_LOG_FILE)
        self._ensure_directory()
    
    def _ensure_directory(self):
        """Ensure logs directory exists."""
        os.makedirs(self.logs_dir, exist_ok=True)
    
    def write_entry(self, entry: LogEntry):
        """Write log entry to both human-readable and JSON files."""
        try:
            # Human-readable format
            request_id_str = f"[REQ:{entry.request_id[:8]}]" if entry.request_id else ""
            duration_str = f" ({entry.duration_ms:.1f}ms)" if entry.duration_ms else ""
            session_str = f"[SESSION:{entry.session_id[:8]}]"
            
            human_readable = (
                f"[{entry.timestamp}] [{entry.level}] [{entry.component}:{entry.method}] "
                f"{entry.message}{duration_str} {request_id_str} {session_str}"
            )
            
            # Write human-readable log
            with open(self.log_file_path, "a", encoding="utf-8") as f:
                f.write(human_readable + "\n")
            
            # Write structured JSON log
            with open(self.structured_log_path, "a", encoding="utf-8") as f:
                f.write(entry.to_json() + "\n")
                
        except Exception as e:
            # Emergency fallback to stdout
            print(f"[FILE_LOG_ERROR] {entry.message} (Error: {e})", file=sys.stderr)


class MongoLogger:
    """Handles MongoDB logging operations with connection management."""
    
    def __init__(self):
        self.client = None
        self.collection = None
        self.connected = False
        self._connection_string = None
    
    def connect(self, connection_string: str) -> bool:
        """Connect to MongoDB logs database."""
        try:
            from pymongo import MongoClient
            # Debug: show which connection string is being used
            print(f"[MONGO_CONNECT_DEBUG] Attempting connect with: {repr(connection_string)}", file=sys.stderr)
            self._connection_string = connection_string
            # Use a small serverSelectionTimeoutMS to fail fast when testing
            try:
                self.client = MongoClient(connection_string, serverSelectionTimeoutMS=2000)
            except TypeError:
                # Fallback if pymongo version doesn't accept serverSelectionTimeoutMS here
                self.client = MongoClient(connection_string)
            db = self.client["kb-mcp-logs"]
            self.collection = db["logs"]
            # Test connection
            self.client.admin.command('ping')
            self.connected = True
            return True
        except Exception as e:
            # Emit detailed debug info so we can see why connect failed
            print(f"[MONGO_CONNECT_DEBUG] Connection failed: {e}", file=sys.stderr)
            try:
                import traceback
                traceback.print_exc(file=sys.stderr)
            except Exception:
                pass
            self.connected = False
            return False
    
    def write_entry(self, entry: LogEntry) -> bool:
        """Write log entry to MongoDB. Returns success status."""
        if not self.connected or self.collection is None:
            print(f"[MONGO_DEBUG] Not connected or no collection", file=sys.stderr)
            return False
        
        try:
            result = self.collection.insert_one(entry.to_dict())
            print(f"[MONGO_DEBUG] Inserted entry with ID: {result.inserted_id}", file=sys.stderr)
            return True
        except Exception as e:
            print(f"[MONGO_DEBUG] Insert failed: {e}", file=sys.stderr)
            # Try to reconnect once
            if self._connection_string and self.connect(self._connection_string):
                try:
                    result = self.collection.insert_one(entry.to_dict())
                    print(f"[MONGO_DEBUG] Reconnect successful, inserted ID: {result.inserted_id}", file=sys.stderr)
                    return True
                except Exception as e2:
                    print(f"[MONGO_DEBUG] Reconnect insert failed: {e2}", file=sys.stderr)
            self.connected = False
            return False
    
    def write_batch(self, entries: list[LogEntry]) -> int:
        """Write batch of entries. Returns number of successful writes."""
        if not self.connected or self.collection is None:
            return 0

        try:
            documents = [entry.to_dict() for entry in entries]
            result = self.collection.insert_many(documents)
            return len(result.inserted_ids)
        except Exception as e:
            print(f"[MONGO_DEBUG] Batch insert failed: {e}", file=sys.stderr)
            try:
                import traceback
                traceback.print_exc(file=sys.stderr)
            except Exception:
                pass
            # Try individual writes as fallback
            success_count = 0
            for entry in entries:
                try:
                    if self.write_entry(entry):
                        success_count += 1
                except Exception as e2:
                    print(f"[MONGO_DEBUG] Individual write also failed: {e2}", file=sys.stderr)
            return success_count


class LogQueue:
    """Background thread that processes log entries."""
    
    def __init__(self):
        self.queue = queue.Queue(maxsize=QUEUE_SIZE)
        self.file_logger = FileLogger()
        self.mongo_logger = MongoLogger()
        self.thread = None
        self.running = False
        self.session_id = str(uuid.uuid4())
    
    def start(self, mongo_connection_string: Optional[str] = None):
        """Start background logging thread."""
        if self.running:
            return
        
        # Try to connect to MongoDB if connection string provided
        # Debug: print the connection string received by LogQueue.start
        print(f"[LOGQUEUE_START_DEBUG] received mongo_connection_string: {repr(mongo_connection_string)}", file=sys.stderr)
        if mongo_connection_string:
            self.mongo_logger.connect(mongo_connection_string)
        
        self.running = True
        self.thread = threading.Thread(target=self._process_queue, daemon=True)
        self.thread.start()
    
    def stop(self):
        """Stop background logging thread."""
        self.running = False
        if self.thread and self.thread.is_alive():
            # Add sentinel to wake up thread
            try:
                self.queue.put(None, timeout=1.0)
            except queue.Full:
                pass
            self.thread.join(timeout=2.0)
    
    def add_entry(self, entry: LogEntry):
        """Add log entry to queue. Non-blocking."""
        try:
            self.queue.put_nowait(entry)
        except queue.Full:
            # Emergency fallback - write directly to stdout
            print(f"[QUEUE_FULL] {entry.message}", file=sys.stderr)
    
    def _process_queue(self):
        """Background thread that processes log entries."""
        batch = []
        last_flush = time.time()
        
        while self.running:
            try:
                # Get entry with timeout
                timeout = FLUSH_INTERVAL - (time.time() - last_flush)
                timeout = max(0.1, timeout)  # Minimum timeout
                
                entry = self.queue.get(timeout=timeout)
                
                # Sentinel to stop thread
                if entry is None:
                    break
                
                batch.append(entry)
                
                # Process batch if full or timeout reached
                should_flush = (
                    len(batch) >= BATCH_SIZE or 
                    (time.time() - last_flush) >= FLUSH_INTERVAL
                )
                
                if should_flush:
                    self._process_batch(batch)
                    batch = []
                    last_flush = time.time()
                    
            except queue.Empty:
                # Timeout - flush any pending entries
                if batch:
                    self._process_batch(batch)
                    batch = []
                    last_flush = time.time()
            except Exception as e:
                # Log error and continue
                print(f"[LOG_QUEUE_ERROR] {e}", file=sys.stderr)
        
        # Process any remaining entries
        if batch:
            self._process_batch(batch)
    
    def _process_batch(self, batch: list[LogEntry]):
        """Process a batch of log entries."""
        print(f"[PROCESS_BATCH_DEBUG] Processing batch of {len(batch)} entries", file=sys.stderr)
        
        # Always write to file first (guaranteed to work)
        for entry in batch:
            self.file_logger.write_entry(entry)
        
        # Attempt MongoDB batch write (best effort)
        print(f"[PROCESS_BATCH_DEBUG] MongoDB connected: {self.mongo_logger.connected}", file=sys.stderr)
        if self.mongo_logger.connected:
            print(f"[PROCESS_BATCH_DEBUG] Attempting MongoDB batch write", file=sys.stderr)
            result = self.mongo_logger.write_batch(batch)
            print(f"[PROCESS_BATCH_DEBUG] MongoDB batch write result: {result}", file=sys.stderr)
        else:
            print(f"[PROCESS_BATCH_DEBUG] MongoDB not connected, skipping", file=sys.stderr)


# Global logging infrastructure
_log_queue = None
_logger_lock = threading.Lock()


def initialize_logging(mongo_connection_string: Optional[str] = None) -> str:
    """Initialize the logging system. Returns session_id."""
    global _log_queue
    
    with _logger_lock:
        if _log_queue is None:
            _log_queue = LogQueue()
            # If no connection string passed, try to import from db module
            if not mongo_connection_string:
                try:
                    from db import mongo_connection_string as db_mongo_conn
                    mongo_connection_string = db_mongo_conn
                    print(f"[INIT_LOGGING_DEBUG] initialize_logging found db.mongo_connection_string: {repr(mongo_connection_string)}", file=sys.stderr)
                except Exception:
                    # Leave as None if not available
                    print("[INIT_LOGGING_DEBUG] initialize_logging: no mongo_connection_string provided and db import failed", file=sys.stderr)

            _log_queue.start(mongo_connection_string)

        return _log_queue.session_id


def shutdown_logging():
    """Shutdown the logging system."""
    global _log_queue
    
    with _logger_lock:
        if _log_queue:
            _log_queue.stop()
            _log_queue = None


class StructuredLogger:
    """Compatibility class that provides the original StructuredLogger interface."""
    
    def __init__(self, component: str = "KB-MCP"):
        self.component = component
        self.logger = logging.getLogger(component)
        if not self.logger.handlers:
            handler = logging.StreamHandler(sys.stderr)
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)
    
    def log(self, level: str, method: str, message: str, **kwargs):
        """Log a structured message."""
        log_level = getattr(logging, level.upper(), logging.INFO)
        extra = {
            'component': self.component,
            'method': method,
            **kwargs
        }
        self.logger.log(log_level, f"{method}: {message}", extra=extra)


# Global logger instance for backward compatibility
structured_logger = StructuredLogger()


def log_message(message: str, level: str = "info", component: str = None, method: str = None,
                request_id: str = None, duration_ms: float = None, extra_data: dict = None):
    """
    Enhanced logging with dual file + MongoDB storage.
    
    Maintains exact signature of original log_message function for backward compatibility.
    
    Args:
        message: Log message
        level: Log level (error, warning, info, debug)
        component: Component name (auto-detected if None)  
        method: Method name (auto-detected if None)
        request_id: Request correlation ID
        duration_ms: Operation duration in milliseconds
        extra_data: Additional structured data
    """
    global _log_queue
    
    # Auto-detect component/method from call stack if not provided
    if component is None or method is None:
        frame = inspect.currentframe().f_back
        method_name = frame.f_code.co_name
        
        # Try to get class name from self
        component_name = "unknown"
        if 'self' in frame.f_locals:
            component_name = frame.f_locals['self'].__class__.__name__
        
        if component is None:
            component = component_name
        if method is None:
            method = method_name
    
    # Initialize logging if not already done
    if _log_queue is None:
        initialize_logging()
    
    # Create log entry
    entry = LogEntry(
        timestamp=datetime.utcnow().isoformat(),
        session_id=_log_queue.session_id,
        level=level.upper(),
        component=component,
        method=method,
        message=message,
        request_id=request_id,
        duration_ms=duration_ms,
        extra_data=extra_data or {}
    )
    
    # Add to queue (non-blocking)
    _log_queue.add_entry(entry)
    
    # Also log to stdout for immediate visibility
    level_int = getattr(logging, level.upper(), logging.INFO)
    structured_logger.logger.log(level_int, f"{component}: {message}")