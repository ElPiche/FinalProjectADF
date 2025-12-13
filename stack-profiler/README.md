# Stack Profiler - Docker Container Performance Monitor

Real-time monitoring tool for Docker container performance metrics, sending data to Elasticsearch and visualizing in Kibana with **auto-refreshing dashboards**.

## Features

- **Real-time monitoring** of all running Docker containers
- **CPU, Memory, Network I/O, Block I/O** metrics collection
- **Elasticsearch integration** for time-series storage
- **Auto-generated Kibana dashboard** with 5-second refresh
- Configurable collection interval

## Quick Start

```powershell
cd stack-profiler
.\Start-Profiler.ps1
```

This will:
1. Create a Python virtual environment
2. Install dependencies
3. **Automatically create the Kibana dashboard**
4. Start collecting metrics

## Prerequisites

- Python 3.9+
- Docker running on the host
- Elasticsearch accessible (default: localhost:9200)
- Kibana accessible (default: localhost:5601)

## Installation

### Option 1: Run from Host (Recommended for Windows)

```powershell
# Navigate to the stack-profiler directory
cd stack-profiler

# Create virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Run the profiler
python profiler.py
```

### Option 2: Run in Docker (Linux/Mac)

```bash
docker-compose -f docker-compose.profiler.yml up -d
```

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `ES_HOST` | `http://localhost:9200` | Elasticsearch host URL |
| `COLLECTION_INTERVAL` | `5` | Seconds between metric collections |
| `INDEX_NAME` | `docker-container-metrics` | Elasticsearch index name |

## Metrics Collected

Each document contains:

- `@timestamp` - ISO 8601 timestamp
- `container_id` - Docker container ID (short)
- `container_name` - Container name
- `container_image` - Image name
- `cpu_percent` - CPU usage percentage
- `memory_usage_mb` - Memory usage in MB
- `memory_limit_mb` - Memory limit in MB
- `memory_percent` - Memory usage percentage
- `network_rx_mb` - Network received in MB
- `network_tx_mb` - Network transmitted in MB
- `block_read_mb` - Block I/O read in MB
- `block_write_mb` - Block I/O write in MB
- `pids` - Number of processes in container
- `status` - Container status

## Kibana Dashboard

After running the profiler, access Kibana at `http://localhost:5601` and:

1. The dashboard is **automatically created** when you run `Start-Profiler.ps1`
2. Or manually create it: `python create_dashboard.py`
3. Open: `http://localhost:5601/app/dashboards#/view/docker-stack-monitor-dashboard`

### Dashboard Features:
- **5-second auto-refresh** for real-time monitoring
- CPU usage per container over time
- Memory usage per container over time
- Network I/O (RX/TX) visualization
- Block I/O (Read/Write) visualization
- Real-time statistics table with all containers

## Usage Examples

```powershell
# Run with custom Elasticsearch host
$env:ES_HOST = "http://elasticsearch-dataset:9200"
python profiler.py

# Run with faster collection interval (2 seconds)
$env:COLLECTION_INTERVAL = "2"
python profiler.py
```

## Stopping the Profiler

Press `Ctrl+C` to gracefully stop the profiler.
