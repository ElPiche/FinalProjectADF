#!/usr/bin/env python3
"""
Stack Profiler - REAL-TIME Docker Container Performance Monitor

Uses STREAMING stats API for true real-time (~1 second) metrics collection.
Each container has its own stats stream thread for maximum performance.

Architecture:
- Each container gets a dedicated thread that streams stats continuously
- Docker's streaming stats API emits updates every ~1 second per container
- A shared queue collects metrics from all threads
- A bulk indexer flushes metrics to Elasticsearch every second
"""

import os
import sys
import time
import signal
import logging
import platform
import threading
import queue
from datetime import datetime, timezone
from typing import Optional, Dict, Any

import docker
from docker.models.containers import Container
from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Configuration from environment
ES_HOST = os.getenv('ES_URL', os.getenv('ES_HOST', 'http://localhost:9201'))
INDEX_NAME = os.getenv('INDEX_NAME', 'docker-container-metrics')
BATCH_SIZE = int(os.getenv('BATCH_SIZE', '50'))  # Max metrics per bulk request
FLUSH_INTERVAL = float(os.getenv('FLUSH_INTERVAL', '1.0'))  # Seconds between flushes

# Global flag for graceful shutdown
running = True
metrics_queue: queue.Queue = queue.Queue()


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    global running
    if running:
        logger.info("Received shutdown signal. Stopping profiler...")
        running = False


def calculate_cpu_percent(stats: dict) -> float:
    """
    Calculate CPU usage percentage from Docker stats.
    Uses the same formula as `docker stats` command.
    """
    cpu_stats = stats.get('cpu_stats', {})
    precpu_stats = stats.get('precpu_stats', {})
    
    cpu_usage = cpu_stats.get('cpu_usage', {})
    precpu_usage = precpu_stats.get('cpu_usage', {})
    
    cpu_total = cpu_usage.get('total_usage', 0)
    precpu_total = precpu_usage.get('total_usage', 0)
    
    system_cpu = cpu_stats.get('system_cpu_usage', 0)
    presystem_cpu = precpu_stats.get('system_cpu_usage', 0)
    
    cpu_delta = cpu_total - precpu_total
    system_delta = system_cpu - presystem_cpu
    
    if system_delta > 0 and cpu_delta > 0:
        num_cpus = cpu_stats.get('online_cpus', 1)
        if num_cpus == 0:
            percpu = cpu_usage.get('percpu_usage', [])
            num_cpus = len(percpu) if percpu else 1
        
        cpu_percent = (cpu_delta / system_delta) * num_cpus * 100.0
        return round(cpu_percent, 2)
    
    return 0.0


def calculate_memory_stats(stats: dict) -> dict:
    """Extract memory usage statistics."""
    memory_stats = stats.get('memory_stats', {})
    
    usage = memory_stats.get('usage', 0)
    limit = memory_stats.get('limit', 0)
    
    cache = memory_stats.get('stats', {}).get('cache', 0)
    actual_usage = usage - cache if cache else usage
    
    memory_mb = actual_usage / (1024 * 1024)
    limit_mb = limit / (1024 * 1024) if limit else 0
    
    percent = (actual_usage / limit) * 100.0 if limit > 0 else 0.0
    
    return {
        'usage_mb': round(memory_mb, 2),
        'limit_mb': round(limit_mb, 2),
        'percent': round(percent, 2)
    }


def calculate_network_stats(stats: dict) -> dict:
    """Extract network I/O statistics."""
    networks = stats.get('networks', {})
    
    rx_bytes = sum(data.get('rx_bytes', 0) for data in networks.values())
    tx_bytes = sum(data.get('tx_bytes', 0) for data in networks.values())
    
    return {
        'rx_mb': round(rx_bytes / (1024 * 1024), 4),
        'tx_mb': round(tx_bytes / (1024 * 1024), 4)
    }


def calculate_block_io_stats(stats: dict) -> dict:
    """Extract block I/O statistics."""
    blkio_stats = stats.get('blkio_stats', {})
    io_service_bytes = blkio_stats.get('io_service_bytes_recursive', []) or []
    
    read_bytes = sum(e.get('value', 0) for e in io_service_bytes if e.get('op', '').lower() == 'read')
    write_bytes = sum(e.get('value', 0) for e in io_service_bytes if e.get('op', '').lower() == 'write')
    
    return {
        'read_mb': round(read_bytes / (1024 * 1024), 4),
        'write_mb': round(write_bytes / (1024 * 1024), 4)
    }


def parse_stats(container: Container, stats: dict) -> dict:
    """Parse Docker stats into an Elasticsearch metric document."""
    cpu_percent = calculate_cpu_percent(stats)
    memory = calculate_memory_stats(stats)
    network = calculate_network_stats(stats)
    block_io = calculate_block_io_stats(stats)
    pids = stats.get('pids_stats', {}).get('current', 0)
    
    return {
        '@timestamp': datetime.now(timezone.utc).isoformat(),
        'container_id': container.short_id,
        'container_name': container.name,
        'container_image': container.image.tags[0] if container.image.tags else 'unknown',
        'status': container.status,
        'cpu_percent': cpu_percent,
        'memory_usage_mb': memory['usage_mb'],
        'memory_limit_mb': memory['limit_mb'],
        'memory_percent': memory['percent'],
        'network_rx_mb': network['rx_mb'],
        'network_tx_mb': network['tx_mb'],
        'block_read_mb': block_io['read_mb'],
        'block_write_mb': block_io['write_mb'],
        'pids': pids
    }


def stream_container_stats(container: Container, q: queue.Queue):
    """
    Stream stats from a single container continuously.
    
    Docker's streaming stats API emits updates every ~1 second automatically!
    Each stats update is pushed to the shared queue for bulk indexing.
    """
    container_name = container.name
    logger.debug(f"Starting stats stream for {container_name}")
    
    try:
        # stream=True returns a generator that yields stats every ~1 second
        for stats in container.stats(stream=True, decode=True):
            if not running:
                break
            
            try:
                metric = parse_stats(container, stats)
                q.put(metric)
            except Exception as e:
                logger.debug(f"Error parsing stats for {container_name}: {e}")
                
    except Exception as e:
        if running:  # Only log if not shutting down
            logger.warning(f"Stats stream ended for {container_name}: {type(e).__name__}")


def create_index_template(es: Elasticsearch, index_name: str) -> None:
    """Create index template with proper mappings for real-time metrics."""
    template_name = f"{index_name}-template"
    
    if es.indices.exists_index_template(name=template_name):
        logger.info(f"Index template '{template_name}' already exists")
        return
    
    template_body = {
        "index_patterns": [f"{index_name}*"],
        "template": {
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 0,
                "index.refresh_interval": "1s"  # Fast refresh for real-time dashboards
            },
            "mappings": {
                "properties": {
                    "@timestamp": {"type": "date"},
                    "container_id": {"type": "keyword"},
                    "container_name": {"type": "keyword"},
                    "container_image": {"type": "keyword"},
                    "status": {"type": "keyword"},
                    "cpu_percent": {"type": "float"},
                    "memory_usage_mb": {"type": "float"},
                    "memory_limit_mb": {"type": "float"},
                    "memory_percent": {"type": "float"},
                    "network_rx_mb": {"type": "float"},
                    "network_tx_mb": {"type": "float"},
                    "block_read_mb": {"type": "float"},
                    "block_write_mb": {"type": "float"},
                    "pids": {"type": "integer"}
                }
            }
        }
    }
    
    es.indices.put_index_template(name=template_name, body=template_body)
    logger.info(f"Created index template '{template_name}'")


def bulk_indexer(es: Elasticsearch, q: queue.Queue):
    """
    Background thread that batches metrics and sends to Elasticsearch.
    Flushes either when batch_size is reached or flush_interval passes.
    """
    global running
    batch = []
    last_flush = time.time()
    total_indexed = 0
    
    while running or not q.empty():
        try:
            # Get metrics with timeout to allow checking running flag
            try:
                metric = q.get(timeout=0.1)
                batch.append({
                    "_index": INDEX_NAME,
                    "_source": metric
                })
            except queue.Empty:
                pass
            
            # Flush if batch is full or interval passed
            current_time = time.time()
            should_flush = (
                len(batch) >= BATCH_SIZE or 
                (len(batch) > 0 and current_time - last_flush >= FLUSH_INTERVAL)
            )
            
            if should_flush:
                try:
                    success, failed = bulk(
                        es, batch,
                        raise_on_error=False,
                        raise_on_exception=False
                    )
                    total_indexed += success
                    if failed:
                        logger.warning(f"Failed to index {len(failed)} documents")
                    
                    logger.info(f"📊 Indexed {success} metrics (queue: {q.qsize()}) | Total: {total_indexed}")
                    
                except Exception as e:
                    logger.error(f"Bulk indexing error: {e}")
                
                batch = []
                last_flush = current_time
                
        except Exception as e:
            logger.error(f"Error in bulk indexer: {e}")
    
    # Final flush
    if batch:
        try:
            success, _ = bulk(es, batch, raise_on_error=False, raise_on_exception=False)
            total_indexed += success
            logger.info(f"Final flush: {success} metrics | Total: {total_indexed}")
        except Exception as e:
            logger.error(f"Final flush error: {e}")
    
    logger.info(f"Bulk indexer stopped. Total indexed: {total_indexed}")


def manage_container_streams(docker_client: docker.DockerClient, q: queue.Queue):
    """
    Manages stats streams for all containers.
    Starts new streams for new containers, cleans up stopped ones.
    """
    global running
    active_streams: Dict[str, threading.Thread] = {}
    
    while running:
        try:
            # Get current running containers
            containers = docker_client.containers.list(filters={'status': 'running'})
            current_ids = {c.id for c in containers}
            
            # Start streams for new containers
            for container in containers:
                if container.id not in active_streams or not active_streams[container.id].is_alive():
                    thread = threading.Thread(
                        target=stream_container_stats,
                        args=(container, q),
                        daemon=True,
                        name=f"stats-{container.name}"
                    )
                    thread.start()
                    active_streams[container.id] = thread
                    logger.info(f"🚀 Started stats stream for: {container.name}")
            
            # Clean up stopped container threads
            stopped = [cid for cid in active_streams if cid not in current_ids]
            for cid in stopped:
                logger.info(f"🛑 Container stopped, removing stream")
                del active_streams[cid]
            
            # Check every 5 seconds for container changes
            time.sleep(5)
            
        except Exception as e:
            logger.error(f"Error managing streams: {e}")
            time.sleep(5)
    
    logger.info("Container stream manager stopped")


def main():
    """Main entry point."""
    global running
    
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    if platform.system() != 'Windows':
        signal.signal(signal.SIGTERM, signal_handler)
    
    logger.info("=" * 60)
    logger.info("🚀 Stack Profiler - REAL-TIME Docker Performance Monitor")
    logger.info("=" * 60)
    logger.info(f"Elasticsearch Host: {ES_HOST}")
    logger.info(f"Mode: STREAMING (updates every ~1 second per container)")
    logger.info(f"Flush Interval: {FLUSH_INTERVAL}s | Batch Size: {BATCH_SIZE}")
    logger.info(f"Index Name: {INDEX_NAME}")
    logger.info("=" * 60)
    
    # Initialize Docker client
    try:
        docker_client = docker.from_env()
        docker_info = docker_client.info()
        logger.info(f"Connected to Docker: {docker_info.get('Name', 'unknown')}")
        logger.info(f"Docker Version: {docker_info.get('ServerVersion', 'unknown')}")
        logger.info(f"Total Containers: {docker_info.get('Containers', 0)}")
    except Exception as e:
        logger.error(f"Failed to connect to Docker: {e}")
        sys.exit(1)
    
    # Initialize Elasticsearch client
    try:
        es = Elasticsearch(ES_HOST)
        info = es.info()
        logger.info(f"Connected to Elasticsearch: {info['cluster_name']}")
        logger.info(f"Elasticsearch Version: {info['version']['number']}")
    except Exception as e:
        logger.error(f"Failed to connect to Elasticsearch at {ES_HOST}: {e}")
        sys.exit(1)
    
    # Create index template
    try:
        create_index_template(es, INDEX_NAME)
    except Exception as e:
        logger.error(f"Failed to create index template: {e}")
        sys.exit(1)
    
    logger.info("")
    logger.info("🔴 Starting REAL-TIME metrics streaming... (Press Ctrl+C to stop)")
    logger.info("")
    
    # Start bulk indexer thread
    indexer_thread = threading.Thread(
        target=bulk_indexer,
        args=(es, metrics_queue),
        daemon=True,
        name="bulk-indexer"
    )
    indexer_thread.start()
    
    # Start container stream manager (runs in main thread)
    try:
        manage_container_streams(docker_client, metrics_queue)
    except KeyboardInterrupt:
        pass
    
    running = False
    
    # Wait for indexer to finish
    logger.info("Waiting for indexer to flush remaining metrics...")
    indexer_thread.join(timeout=5)
    
    logger.info("")
    logger.info("=" * 60)
    logger.info("Profiler stopped.")
    logger.info("=" * 60)


if __name__ == '__main__':
    main()
