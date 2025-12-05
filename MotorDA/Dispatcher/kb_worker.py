"""
Per-KB Worker Architecture for Multi-Dimensional Anomaly Detection

This module implements:
- KBWorker: Handles detection for a single KB config with filtered change stream
- DispatcherManager: Manages worker lifecycle (spawn/stop based on config changes)
- Observation buffering for multi-dimensional algorithms

Design: One KB Config = One Worker (isolated change streams, no coordination needed)
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Set, List, Callable
from concurrent.futures import ThreadPoolExecutor
from bson import ObjectId

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.change_stream import ChangeStream

# Algorithm interface for mode resolution
from MotorDA.Dispatcher.algorithm_interface import get_algorithm, resolve_algorithm_mode

# Orchestrator for detection
from MotorDA.Dispatcher.training_orchestrator import DetectionOrchestrator

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration Constants
# =============================================================================

# Buffer configuration for multi-dimensional observation assembly
BUFFER_TIMEOUT_MS = 500  # Discard incomplete observations after 500ms
BUFFER_CLEANUP_INTERVAL_MS = 100  # Clean up stale buffer entries every 100ms


# =============================================================================
# Observation Buffer
# =============================================================================

@dataclass
class ObservationBuffer:
    """Buffer for assembling multi-dimensional observations from per-dimension documents.
    
    The Extractor writes one document per dimension:
        {kbId, timestamp: T1, dim: "cpu", value: 45}
        {kbId, timestamp: T1, dim: "memory", value: 78}
    
    Multi-dimensional algorithms need complete vectors:
        {timestamp: T1, cpu: 45, memory: 78, requests: 120}
    
    This buffer collects dimensions until all are present, then emits the complete observation.
    
    ⚠️ CRITICAL: Incomplete observations are DISCARDED after timeout to avoid false positives.
    """
    
    expected_dimensions: Set[str] = field(default_factory=set)
    buffer: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    
    def add_dimension(self, timestamp_key: str, dimension: str, value: Any) -> Optional[Dict[str, Any]]:
        """Add a dimension value to the buffer.
        
        Args:
            timestamp_key: Unique key for the observation (usually ISO timestamp)
            dimension: Dimension name (e.g., "cpu", "memory")
            value: Dimension value
        
        Returns:
            Complete observation dict if all dimensions are present, None otherwise
        """
        with self._lock:
            if timestamp_key not in self.buffer:
                self.buffer[timestamp_key] = {
                    "_first_seen": time.time(),
                    "_dims": {},
                    "timestamp": timestamp_key
                }
            
            self.buffer[timestamp_key]["_dims"][dimension] = value
            
            # Check if all expected dimensions are present
            current_dims = set(self.buffer[timestamp_key]["_dims"].keys())
            if current_dims >= self.expected_dimensions:
                # Complete observation - extract and remove from buffer
                entry = self.buffer.pop(timestamp_key)
                observation = {"timestamp": timestamp_key}
                observation.update(entry["_dims"])
                return observation
            
            return None
    
    def cleanup_stale(self, timeout_ms: int = BUFFER_TIMEOUT_MS) -> List[Dict[str, Any]]:
        """Remove and return information about stale buffer entries.
        
        ⚠️ CRITICAL: Stale entries are DISCARDED, not processed.
        Partial vectors cause false positives in multi-dimensional algorithms.
        
        Args:
            timeout_ms: Age threshold in milliseconds
        
        Returns:
            List of discarded entry metadata (for logging)
        """
        now = time.time()
        timeout_seconds = timeout_ms / 1000.0
        discarded = []
        
        with self._lock:
            stale_keys = []
            for ts_key, entry in self.buffer.items():
                age = now - entry["_first_seen"]
                if age > timeout_seconds:
                    stale_keys.append(ts_key)
                    discarded.append({
                        "timestamp": ts_key,
                        "age_ms": int(age * 1000),
                        "received_dims": list(entry["_dims"].keys()),
                        "missing_dims": list(self.expected_dimensions - set(entry["_dims"].keys()))
                    })
            
            for key in stale_keys:
                del self.buffer[key]
        
        return discarded
    
    def clear(self):
        """Clear all buffered entries."""
        with self._lock:
            self.buffer.clear()


# =============================================================================
# KB Worker
# =============================================================================

@dataclass
class KBWorker:
    """Worker for processing a single KB configuration's detection.
    
    Each KBWorker:
    - Has a filtered change stream watching only its KB's data
    - Maintains an observation buffer for multi-dimensional assembly
    - Runs detection using the appropriate algorithm mode
    
    Lifecycle: Spawned by DispatcherManager when KB config becomes active,
               stopped when KB config becomes inactive.
    """
    
    kb_id: str
    kb_config: Dict[str, Any]
    training_result: Dict[str, Any]
    mongo_client: MongoClient
    db_name: str = "anomaly_detection"
    series_collection_name: str = "series"
    
    # Internal state
    _running: bool = field(default=False, init=False)
    _thread: Optional[threading.Thread] = field(default=None, init=False)
    _buffer: Optional[ObservationBuffer] = field(default=None, init=False)
    _change_stream: Optional[ChangeStream] = field(default=None, init=False)
    _detection_orchestrator: Optional[DetectionOrchestrator] = field(default=None, init=False)
    _on_anomaly_callback: Optional[Callable] = field(default=None, init=False)
    _algorithm_name: str = field(default="unknown", init=False)
    
    def __post_init__(self):
        """Initialize worker components."""
        # Extract algorithm info from kb_config
        alg_config = self.kb_config.get("algorithm", {})
        alg_name = alg_config.get("name", "zscore").lower()
        alg_params = alg_config.get("parameters", [])
        
        # Store algorithm name for later use
        self._algorithm_name = alg_name
        
        # Resolve algorithm mode
        self.is_multi_dimensional = resolve_algorithm_mode(alg_name, alg_params)
        
        # Extract expected dimensions from parameters
        expected_dims = set()
        for param in alg_params:
            dim = param.get("dimension")
            if dim and param.get("is_active", True):
                expected_dims.add(dim)
        
        # Initialize buffer (used for multi-dimensional or even single-dim batching)
        self._buffer = ObservationBuffer(expected_dimensions=expected_dims)
        
        # Get bucket profile if configured
        bucket_profile = None
        bucket_profile_id = self.kb_config.get("bucket_profile_id")
        if bucket_profile_id:
            kb_db = self.mongo_client["knowledge_base"]
            bucket_profile = kb_db["bucket_profiles"].find_one(
                {"$or": [{"profile_id": bucket_profile_id}, {"_id": bucket_profile_id}]}
            )
        
        # Create detection orchestrator
        self._detection_orchestrator = DetectionOrchestrator(
            algorithm_name=alg_name,
            parameters=alg_params,
            training_result=self.training_result,
            bucket_profile=bucket_profile,
            is_multi_dimensional=self.is_multi_dimensional
        )
        
        logger.info(
            f"[KBWORKER-{self.kb_id[:8]}] Initialized: "
            f"algorithm={alg_name}, mode={'multi' if self.is_multi_dimensional else 'single'}-dim, "
            f"dimensions={expected_dims}"
        )
    
    def set_anomaly_callback(self, callback: Callable[[Dict[str, Any]], None]):
        """Set callback function to be called when anomaly is detected.
        
        Args:
            callback: Function that accepts detection result dict
        """
        self._on_anomaly_callback = callback
    
    def _get_series_collection(self) -> Collection:
        """Get the series collection."""
        return self.mongo_client[self.db_name][self.series_collection_name]
    
    def _build_change_stream_pipeline(self) -> List[Dict[str, Any]]:
        """Build MongoDB change stream pipeline filtered for this KB.
        
        Returns:
            Pipeline that matches only this KB's detection-mode series documents
        """
        return [
            {
                "$match": {
                    "operationType": "insert",
                    "fullDocument.metadata.kbId": self.kb_id,
                    "fullDocument.metadata.mode": 1  # Detection mode
                }
            }
        ]
    
    def _process_document(self, doc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Process a single series document.
        
        For multi-dimensional algorithms, buffers the dimension until complete.
        For single-dimensional, processes immediately.
        
        Args:
            doc: Series document from change stream
        
        Returns:
            Complete observation if ready, None otherwise
        """
        metadata = doc.get("metadata", {})
        timestamp = doc.get("timestamp")
        dimension = metadata.get("dim")
        value = doc.get("value")
        
        if not timestamp or not dimension:
            return None
        
        # Convert timestamp to string key
        ts_key = timestamp.isoformat() if hasattr(timestamp, 'isoformat') else str(timestamp)
        
        if self.is_multi_dimensional:
            # Buffer until all dimensions arrive
            return self._buffer.add_dimension(ts_key, dimension, value)
        else:
            # Single-dimensional: process immediately
            return {"timestamp": ts_key, dimension: value}
    
    def _run_detection(self, observation: Dict[str, Any]):
        """Run detection on a complete observation.
        
        Args:
            observation: Complete observation dict with all dimensions
        """
        try:
            # Get timestamp field from kb_config query_mode
            query_mode = self.kb_config.get("query_mode", {})
            timestamp_field = query_mode.get("timestamp_field", "timestamp")
            
            # Log detection attempt
            logger.info(
                f"[KBWORKER-{self.kb_id[:8]}] Running detection: "
                f"timestamp={observation.get('timestamp')}"
            )
            
            result = self._detection_orchestrator.detect(
                observation=observation,
                timestamp_field=timestamp_field
            )
            
            if result.get("is_anomaly", False):
                logger.info(
                    f"[KBWORKER-{self.kb_id[:8]}] Anomaly detected: "
                    f"timestamp={observation.get('timestamp')}"
                )
                
                if self._on_anomaly_callback:
                    # Add KB context to result
                    result["kb_id"] = self.kb_id
                    result["kb_name"] = self.kb_config.get("name", "unknown")
                    result["algorithm"] = self._algorithm_name
                    result["observation"] = observation
                    self._on_anomaly_callback(result)
        
        except Exception as e:
            logger.error(f"[KBWORKER-{self.kb_id[:8]}] Detection error: {e}")
            import traceback
            traceback.print_exc()
    
    def _cleanup_loop(self):
        """Periodic cleanup of stale buffer entries.
        
        Runs in a separate thread while the worker is active.
        """
        while self._running:
            time.sleep(BUFFER_CLEANUP_INTERVAL_MS / 1000.0)
            
            if not self.is_multi_dimensional:
                continue  # No buffering for single-dimensional
            
            discarded = self._buffer.cleanup_stale(BUFFER_TIMEOUT_MS)
            for entry in discarded:
                logger.warning(
                    f"[KBWORKER-{self.kb_id[:8]}] Discarding incomplete observation: "
                    f"timestamp={entry['timestamp']}, age={entry['age_ms']}ms, "
                    f"received={entry['received_dims']}, missing={entry['missing_dims']}"
                )
    
    def _watch_loop(self):
        """Main watch loop - processes change stream events."""
        collection = self._get_series_collection()
        pipeline = self._build_change_stream_pipeline()
        
        logger.info(f"[KBWORKER-{self.kb_id[:8]}] Starting change stream watcher")
        
        try:
            with collection.watch(pipeline, full_document="updateLookup") as stream:
                self._change_stream = stream
                
                for change in stream:
                    if not self._running:
                        break
                    
                    try:
                        doc = change.get("fullDocument")
                        if not doc:
                            continue
                        
                        observation = self._process_document(doc)
                        
                        if observation:
                            self._run_detection(observation)
                    
                    except Exception as e:
                        logger.error(f"[KBWORKER-{self.kb_id[:8]}] Document processing error: {e}")
        
        except Exception as e:
            if self._running:  # Only log if not intentionally stopped
                logger.error(f"[KBWORKER-{self.kb_id[:8]}] Change stream error: {e}")
        
        finally:
            logger.info(f"[KBWORKER-{self.kb_id[:8]}] Change stream watcher stopped")
    
    def start(self):
        """Start the worker."""
        if self._running:
            return
        
        self._running = True
        
        # Start cleanup thread for multi-dimensional buffering
        if self.is_multi_dimensional:
            cleanup_thread = threading.Thread(
                target=self._cleanup_loop,
                name=f"KBWorker-{self.kb_id[:8]}-Cleanup",
                daemon=True
            )
            cleanup_thread.start()
        
        # Start main watch thread
        self._thread = threading.Thread(
            target=self._watch_loop,
            name=f"KBWorker-{self.kb_id[:8]}-Watch",
            daemon=True
        )
        self._thread.start()
        
        logger.info(f"[KBWORKER-{self.kb_id[:8]}] Started")
    
    def stop(self):
        """Stop the worker gracefully."""
        if not self._running:
            return
        
        self._running = False
        
        # Close change stream to unblock the watch loop
        if self._change_stream:
            try:
                self._change_stream.close()
            except Exception:
                pass
        
        # Clear buffer
        if self._buffer:
            self._buffer.clear()
        
        logger.info(f"[KBWORKER-{self.kb_id[:8]}] Stopped")


# =============================================================================
# Dispatcher Manager
# =============================================================================

class DispatcherManager:
    """Manages KBWorker lifecycle based on KB configuration changes.
    
    Responsibilities:
    - Watch kb_configs for active configurations
    - Spawn KBWorker for each active KB config with trained model
    - Stop workers when KB config becomes inactive
    - Restart workers when KB config or training result changes
    """
    
    def __init__(
        self,
        mongo_uri: str,
        anomaly_db_name: str = "anomaly_detection",
        kb_db_name: str = "knowledge_base",
        on_anomaly_callback: Optional[Callable] = None
    ):
        """Initialize the dispatcher manager.
        
        Args:
            mongo_uri: MongoDB connection URI
            anomaly_db_name: Name of anomaly detection database
            kb_db_name: Name of knowledge base database
            on_anomaly_callback: Callback for detected anomalies
        """
        self.mongo_uri = mongo_uri
        self.anomaly_db_name = anomaly_db_name
        self.kb_db_name = kb_db_name
        self.on_anomaly_callback = on_anomaly_callback
        
        self._workers: Dict[str, KBWorker] = {}
        self._workers_lock = threading.Lock()
        self._running = False
        self._watcher_thread: Optional[threading.Thread] = None
        
        # MongoDB connections
        self._mongo_client: Optional[MongoClient] = None
    
    def _get_mongo_client(self) -> MongoClient:
        """Get or create MongoDB client."""
        if self._mongo_client is None:
            self._mongo_client = MongoClient(self.mongo_uri)
        return self._mongo_client
    
    def _get_kb_collection(self) -> Collection:
        """Get the kb_configs collection."""
        return self._get_mongo_client()[self.kb_db_name]["kb_configs"]
    
    def _get_trained_models_collection(self) -> Collection:
        """Get the trained_models collection."""
        return self._get_mongo_client()[self.anomaly_db_name]["trained_models"]
    
    def _get_training_result(self, kb_id: str) -> Optional[Dict[str, Any]]:
        """Get trained model for a KB config.
        
        Args:
            kb_id: KB configuration ID
        
        Returns:
            Training result dict or None
        """
        collection = self._get_trained_models_collection()
        try:
            result = collection.find_one({"kb_id": ObjectId(kb_id)})
            return result
        except Exception:
            return None
    
    def _should_have_worker(self, kb_config: Dict[str, Any]) -> bool:
        """Check if a KB config should have an active worker.
        
        Args:
            kb_config: KB configuration document
        
        Returns:
            True if worker should be running
        """
        # Check detection is active
        scheduling = kb_config.get("scheduling", {})
        detection_config = scheduling.get("detection_config", {})
        
        if not detection_config.get("is_active", False):
            return False
        
        # Check training is complete (has trained model)
        kb_id = str(kb_config.get("_id", ""))
        if not kb_id:
            return False
        
        training_result = self._get_training_result(kb_id)
        return training_result is not None
    
    def _spawn_worker(self, kb_config: Dict[str, Any]):
        """Spawn a new worker for a KB config.
        
        If a worker already exists but the training result has changed,
        the old worker is stopped and a new one is spawned with the updated config.
        
        Args:
            kb_config: KB configuration document
        """
        kb_id = str(kb_config["_id"])
        
        training_result = self._get_training_result(kb_id)
        if not training_result:
            logger.warning(f"[MANAGER] No training result for KB {kb_id}, skipping")
            return
        
        with self._workers_lock:
            existing_worker = self._workers.get(kb_id)
            if existing_worker:
                # Check if training result has changed (compare updated_at timestamp)
                old_updated_at = existing_worker.training_result.get("updated_at")
                new_updated_at = training_result.get("updated_at")
                
                logger.debug(f"[MANAGER] Worker {kb_id[:8]} exists, checking for update: old={old_updated_at}, new={new_updated_at}")
                
                if old_updated_at == new_updated_at:
                    return  # No change, keep existing worker
                
                # Training result changed - restart worker
                logger.info(f"[MANAGER] Training result changed for KB {kb_id}, restarting worker")
                existing_worker.stop()
                del self._workers[kb_id]
            
            worker = KBWorker(
                kb_id=kb_id,
                kb_config=kb_config,
                training_result=training_result,
                mongo_client=self._get_mongo_client(),
                db_name=self.anomaly_db_name
            )
            
            if self.on_anomaly_callback:
                worker.set_anomaly_callback(self.on_anomaly_callback)
            
            worker.start()
            self._workers[kb_id] = worker
            
            logger.info(f"[MANAGER] Spawned worker for KB {kb_id} ({kb_config.get('name', 'unknown')})")
    
    def _stop_worker(self, kb_id: str):
        """Stop a worker.
        
        Args:
            kb_id: KB configuration ID
        """
        with self._workers_lock:
            worker = self._workers.pop(kb_id, None)
            if worker:
                worker.stop()
                logger.info(f"[MANAGER] Stopped worker for KB {kb_id}")
    
    def _sync_workers(self):
        """Synchronize workers with current KB configs.
        
        Called periodically and on config changes to ensure worker state
        matches desired state.
        """
        kb_collection = self._get_kb_collection()
        
        # Get all active detection configs
        active_configs = {}
        for kb_config in kb_collection.find():
            kb_id = str(kb_config["_id"])
            if self._should_have_worker(kb_config):
                active_configs[kb_id] = kb_config
        
        # Stop workers that should no longer be running
        with self._workers_lock:
            workers_to_stop = [
                kb_id for kb_id in self._workers
                if kb_id not in active_configs
            ]
        
        for kb_id in workers_to_stop:
            self._stop_worker(kb_id)
        
        # Start workers that should be running
        for kb_id, kb_config in active_configs.items():
            self._spawn_worker(kb_config)
    
    def _watch_kb_configs(self):
        """Watch kb_configs collection for changes.
        
        Triggers worker sync on inserts, updates, and deletes.
        """
        kb_collection = self._get_kb_collection()
        
        pipeline = [
            {
                "$match": {
                    "operationType": {"$in": ["insert", "update", "replace", "delete"]}
                }
            }
        ]
        
        logger.info("[MANAGER] Starting KB config watcher")
        
        try:
            with kb_collection.watch(pipeline, full_document="updateLookup") as stream:
                for change in stream:
                    if not self._running:
                        break
                    
                    try:
                        op_type = change.get("operationType")
                        logger.debug(f"[MANAGER] KB config change: {op_type}")
                        
                        # Sync workers on any change
                        self._sync_workers()
                    
                    except Exception as e:
                        logger.error(f"[MANAGER] Error processing KB change: {e}")
        
        except Exception as e:
            if self._running:
                logger.error(f"[MANAGER] KB config watcher error: {e}")
        
        finally:
            logger.info("[MANAGER] KB config watcher stopped")
    
    def _watch_trained_models(self):
        """Watch trained_models collection for new/updated models.
        
        Triggers worker sync when training completes.
        """
        trained_collection = self._get_trained_models_collection()
        
        logger.info(f"[MANAGER] Trained models watcher: watching {self.anomaly_db_name}.trained_models")
        
        pipeline = [
            {
                "$match": {
                    "operationType": {"$in": ["insert", "update", "replace"]}
                }
            }
        ]
        
        logger.info("[MANAGER] Starting trained models watcher")
        
        try:
            with trained_collection.watch(pipeline, full_document="updateLookup") as stream:
                logger.info("[MANAGER] Trained models change stream opened successfully")
                for change in stream:
                    if not self._running:
                        break
                    
                    try:
                        # Sync workers when training completes
                        logger.info(f"[MANAGER] Trained models change detected: {change.get('operationType')}")
                        self._sync_workers()
                    
                    except Exception as e:
                        logger.error(f"[MANAGER] Error processing training change: {e}")
        
        except Exception as e:
            if self._running:
                logger.error(f"[MANAGER] Trained models watcher error: {e}")
        
        finally:
            logger.info("[MANAGER] Trained models watcher stopped")
    
    def start(self):
        """Start the dispatcher manager."""
        if self._running:
            return
        
        self._running = True
        
        # Initial sync
        self._sync_workers()
        
        # Start watchers
        kb_watcher = threading.Thread(
            target=self._watch_kb_configs,
            name="Manager-KBWatcher",
            daemon=True
        )
        kb_watcher.start()
        
        models_watcher = threading.Thread(
            target=self._watch_trained_models,
            name="Manager-ModelsWatcher",
            daemon=True
        )
        models_watcher.start()
        
        logger.info(f"[MANAGER] Started with {len(self._workers)} active workers")
    
    def stop(self):
        """Stop the dispatcher manager and all workers."""
        if not self._running:
            return
        
        self._running = False
        
        # Stop all workers
        with self._workers_lock:
            for kb_id in list(self._workers.keys()):
                worker = self._workers.pop(kb_id)
                worker.stop()
        
        # Close MongoDB connection
        if self._mongo_client:
            self._mongo_client.close()
            self._mongo_client = None
        
        logger.info("[MANAGER] Stopped")
    
    def get_active_workers(self) -> Dict[str, Dict[str, Any]]:
        """Get information about active workers.
        
        Returns:
            Dict mapping kb_id to worker info
        """
        with self._workers_lock:
            return {
                kb_id: {
                    "kb_id": worker.kb_id,
                    "kb_name": worker.kb_config.get("name", "unknown"),
                    "is_multi_dimensional": worker.is_multi_dimensional,
                    "expected_dimensions": list(worker._buffer.expected_dimensions) if worker._buffer else []
                }
                for kb_id, worker in self._workers.items()
            }
