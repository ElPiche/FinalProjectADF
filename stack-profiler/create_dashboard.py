#!/usr/bin/env python3
"""
Create Kibana Dashboard for Docker Container Metrics using NDJSON Import.

This script programmatically creates:
1. A data view (index-pattern) for docker-container-metrics index
2. A comprehensive dashboard with real-time auto-refresh (5 seconds)
3. Multiple Lens visualizations for CPU, Memory, Network, and Block I/O

Uses the Kibana saved objects import API with NDJSON format for reliable dashboard creation.
"""

import os
import sys
import json
import time
import requests

KIBANA_URL = os.getenv('KIBANA_URL', 'http://localhost:5601')
ES_URL = os.getenv('ES_URL', 'http://localhost:9200')
INDEX_PATTERN = 'docker-container-metrics*'
DATA_VIEW_ID = 'docker-metrics-dataview'
DASHBOARD_ID = 'docker-stack-monitor-dashboard'

HEADERS = {
    'kbn-xsrf': 'true'
}


def wait_for_kibana(max_retries=30, delay=2):
    """Wait for Kibana to be ready."""
    print(f"Waiting for Kibana at {KIBANA_URL}...")
    for i in range(max_retries):
        try:
            resp = requests.get(f"{KIBANA_URL}/api/status", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('status', {}).get('overall', {}).get('level') == 'available':
                    print("✓ Kibana is ready!")
                    return True
        except:
            pass
        print(f"  Retry {i+1}/{max_retries}...")
        time.sleep(delay)
    return False


def check_data_exists():
    """Check if metrics data exists in Elasticsearch."""
    try:
        resp = requests.get(f"{ES_URL}/docker-container-metrics/_count", timeout=5)
        if resp.status_code == 200:
            count = resp.json().get('count', 0)
            print(f"✓ Found {count} documents in index")
            return count > 0
    except Exception as e:
        print(f"✗ Error checking data: {e}")
    return False


def delete_existing_objects():
    """Delete existing dashboard and data view if they exist."""
    print("Removing existing objects...")
    
    # Delete dashboard
    try:
        resp = requests.delete(
            f"{KIBANA_URL}/api/saved_objects/dashboard/{DASHBOARD_ID}",
            headers=HEADERS,
            timeout=10
        )
        if resp.status_code in (200, 404):
            print("  Deleted existing dashboard")
    except:
        pass
    
    # Delete data view by ID
    try:
        resp = requests.delete(
            f"{KIBANA_URL}/api/data_views/data_view/{DATA_VIEW_ID}",
            headers=HEADERS,
            timeout=10
        )
        if resp.status_code in (200, 404):
            print("  Deleted existing data view")
    except:
        pass
    
    # Find and delete any data view with docker pattern
    try:
        resp = requests.get(f"{KIBANA_URL}/api/data_views", headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            data_views = resp.json().get('data_view', [])
            for dv in data_views:
                if 'docker' in dv.get('title', '').lower() or 'docker' in dv.get('name', '').lower():
                    dv_id = dv.get('id')
                    requests.delete(
                        f"{KIBANA_URL}/api/data_views/data_view/{dv_id}",
                        headers=HEADERS,
                        timeout=10
                    )
                    print(f"  Deleted data view: {dv_id}")
    except:
        pass
    
    time.sleep(1)


def create_metric_panel(panel_index, title, x, y, w, h, source_field, operation, layer_id):
    """Create a metric visualization panel."""
    return {
        "type": "lens",
        "gridData": {"x": x, "y": y, "w": w, "h": h, "i": panel_index},
        "panelIndex": panel_index,
        "embeddableConfig": {
            "attributes": {
                "title": title,
                "visualizationType": "lnsMetric",
                "type": "lens",
                "references": [
                    {"id": DATA_VIEW_ID, "name": f"indexpattern-datasource-layer-{layer_id}", "type": "index-pattern"}
                ],
                "state": {
                    "visualization": {
                        "metricAccessor": "metric",
                        "layerId": layer_id,
                        "layerType": "data"
                    },
                    "query": {"query": "", "language": "kuery"},
                    "filters": [],
                    "datasourceStates": {
                        "formBased": {
                            "layers": {
                                layer_id: {
                                    "columnOrder": ["metric"],
                                    "columns": {
                                        "metric": {
                                            "label": title,
                                            "dataType": "number",
                                            "operationType": operation,
                                            "sourceField": source_field,
                                            "isBucketed": False,
                                            "params": {}
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }


def create_xy_panel(panel_index, title, x, y, w, h, source_field, series_type, layer_id):
    """Create an XY (line/area) visualization panel with breakdown by container."""
    return {
        "type": "lens",
        "gridData": {"x": x, "y": y, "w": w, "h": h, "i": panel_index},
        "panelIndex": panel_index,
        "embeddableConfig": {
            "attributes": {
                "title": title,
                "visualizationType": "lnsXY",
                "type": "lens",
                "references": [
                    {"id": DATA_VIEW_ID, "name": f"indexpattern-datasource-layer-{layer_id}", "type": "index-pattern"}
                ],
                "state": {
                    "visualization": {
                        "preferredSeriesType": series_type,
                        "legend": {"isVisible": True, "position": "right"},
                        "layers": [{
                            "layerId": layer_id,
                            "layerType": "data",
                            "splitAccessor": "breakdown",
                            "accessors": ["value"],
                            "xAccessor": "time",
                            "seriesType": series_type
                        }]
                    },
                    "query": {"query": "", "language": "kuery"},
                    "filters": [],
                    "datasourceStates": {
                        "formBased": {
                            "layers": {
                                layer_id: {
                                    "columnOrder": ["time", "breakdown", "value"],
                                    "columns": {
                                        "time": {
                                            "label": "Time",
                                            "dataType": "date",
                                            "operationType": "date_histogram",
                                            "sourceField": "@timestamp",
                                            "isBucketed": True,
                                            "params": {"interval": "auto"}
                                        },
                                        "breakdown": {
                                            "label": "Container",
                                            "dataType": "string",
                                            "operationType": "terms",
                                            "sourceField": "container_name",
                                            "isBucketed": True,
                                            "params": {
                                                "orderBy": {"type": "column", "columnId": "value"},
                                                "size": 10,
                                                "orderDirection": "desc"
                                            }
                                        },
                                        "value": {
                                            "label": f"Avg {source_field}",
                                            "dataType": "number",
                                            "operationType": "average",
                                            "sourceField": source_field,
                                            "isBucketed": False,
                                            "params": {}
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }


def create_xy_panel_dual(panel_index, title, x, y, w, h, source_field1, label1, source_field2, label2, series_type, layer_id):
    """Create an XY visualization with two metrics."""
    return {
        "type": "lens",
        "gridData": {"x": x, "y": y, "w": w, "h": h, "i": panel_index},
        "panelIndex": panel_index,
        "embeddableConfig": {
            "attributes": {
                "title": title,
                "visualizationType": "lnsXY",
                "type": "lens",
                "references": [
                    {"id": DATA_VIEW_ID, "name": f"indexpattern-datasource-layer-{layer_id}", "type": "index-pattern"}
                ],
                "state": {
                    "visualization": {
                        "preferredSeriesType": series_type,
                        "legend": {"isVisible": True, "position": "right"},
                        "layers": [{
                            "layerId": layer_id,
                            "layerType": "data",
                            "splitAccessor": "breakdown",
                            "accessors": ["value1", "value2"],
                            "xAccessor": "time",
                            "seriesType": series_type
                        }]
                    },
                    "query": {"query": "", "language": "kuery"},
                    "filters": [],
                    "datasourceStates": {
                        "formBased": {
                            "layers": {
                                layer_id: {
                                    "columnOrder": ["time", "breakdown", "value1", "value2"],
                                    "columns": {
                                        "time": {
                                            "label": "Time",
                                            "dataType": "date",
                                            "operationType": "date_histogram",
                                            "sourceField": "@timestamp",
                                            "isBucketed": True,
                                            "params": {"interval": "auto"}
                                        },
                                        "breakdown": {
                                            "label": "Container",
                                            "dataType": "string",
                                            "operationType": "terms",
                                            "sourceField": "container_name",
                                            "isBucketed": True,
                                            "params": {
                                                "orderBy": {"type": "column", "columnId": "value1"},
                                                "size": 10,
                                                "orderDirection": "desc"
                                            }
                                        },
                                        "value1": {
                                            "label": label1,
                                            "dataType": "number",
                                            "operationType": "average",
                                            "sourceField": source_field1,
                                            "isBucketed": False,
                                            "params": {}
                                        },
                                        "value2": {
                                            "label": label2,
                                            "dataType": "number",
                                            "operationType": "average",
                                            "sourceField": source_field2,
                                            "isBucketed": False,
                                            "params": {}
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }


def create_table_panel(panel_index, title, x, y, w, h, layer_id):
    """Create a data table panel."""
    return {
        "type": "lens",
        "gridData": {"x": x, "y": y, "w": w, "h": h, "i": panel_index},
        "panelIndex": panel_index,
        "embeddableConfig": {
            "attributes": {
                "title": title,
                "visualizationType": "lnsDatatable",
                "type": "lens",
                "references": [
                    {"id": DATA_VIEW_ID, "name": f"indexpattern-datasource-layer-{layer_id}", "type": "index-pattern"}
                ],
                "state": {
                    "visualization": {
                        "layerId": layer_id,
                        "layerType": "data",
                        "columns": [
                            {"columnId": "container", "isTransposed": False},
                            {"columnId": "cpu", "isTransposed": False},
                            {"columnId": "memory", "isTransposed": False},
                            {"columnId": "mem_pct", "isTransposed": False},
                            {"columnId": "net_rx", "isTransposed": False},
                            {"columnId": "net_tx", "isTransposed": False},
                            {"columnId": "pids", "isTransposed": False}
                        ]
                    },
                    "query": {"query": "", "language": "kuery"},
                    "filters": [],
                    "datasourceStates": {
                        "formBased": {
                            "layers": {
                                layer_id: {
                                    "columnOrder": ["container", "cpu", "memory", "mem_pct", "net_rx", "net_tx", "pids"],
                                    "columns": {
                                        "container": {
                                            "label": "Container",
                                            "dataType": "string",
                                            "operationType": "terms",
                                            "sourceField": "container_name",
                                            "isBucketed": True,
                                            "params": {
                                                "orderBy": {"type": "column", "columnId": "cpu"},
                                                "size": 20,
                                                "orderDirection": "desc"
                                            }
                                        },
                                        "cpu": {
                                            "label": "CPU %",
                                            "dataType": "number",
                                            "operationType": "last_value",
                                            "sourceField": "cpu_percent",
                                            "isBucketed": False,
                                            "params": {"sortField": "@timestamp"}
                                        },
                                        "memory": {
                                            "label": "Memory MB",
                                            "dataType": "number",
                                            "operationType": "last_value",
                                            "sourceField": "memory_usage_mb",
                                            "isBucketed": False,
                                            "params": {"sortField": "@timestamp"}
                                        },
                                        "mem_pct": {
                                            "label": "Memory %",
                                            "dataType": "number",
                                            "operationType": "last_value",
                                            "sourceField": "memory_percent",
                                            "isBucketed": False,
                                            "params": {"sortField": "@timestamp"}
                                        },
                                        "net_rx": {
                                            "label": "Net RX MB",
                                            "dataType": "number",
                                            "operationType": "last_value",
                                            "sourceField": "network_rx_mb",
                                            "isBucketed": False,
                                            "params": {"sortField": "@timestamp"}
                                        },
                                        "net_tx": {
                                            "label": "Net TX MB",
                                            "dataType": "number",
                                            "operationType": "last_value",
                                            "sourceField": "network_tx_mb",
                                            "isBucketed": False,
                                            "params": {"sortField": "@timestamp"}
                                        },
                                        "pids": {
                                            "label": "PIDs",
                                            "dataType": "number",
                                            "operationType": "last_value",
                                            "sourceField": "pids",
                                            "isBucketed": False,
                                            "params": {"sortField": "@timestamp"}
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }


def create_data_view():
    """Create data view for docker-container-metrics index."""
    print("Creating data view...")
    
    payload = {
        "data_view": {
            "id": DATA_VIEW_ID,
            "title": INDEX_PATTERN,
            "name": "Docker Container Metrics",
            "timeFieldName": "@timestamp"
        }
    }
    
    try:
        resp = requests.post(
            f"{KIBANA_URL}/api/data_views/data_view",
            headers={**HEADERS, 'Content-Type': 'application/json'},
            json=payload,
            timeout=30
        )
        
        if resp.status_code in (200, 201):
            print(f"✓ Created data view: {DATA_VIEW_ID}")
            return True
        elif resp.status_code == 400 and 'Duplicate' in resp.text:
            print(f"✓ Data view already exists: {DATA_VIEW_ID}")
            return True
        else:
            print(f"✗ Failed to create data view: {resp.status_code} - {resp.text}")
            return False
    except Exception as e:
        print(f"✗ Error creating data view: {e}")
        return False


def create_dashboard():
    """Create the monitoring dashboard using saved objects API."""
    print("Creating dashboard with visualizations...")
    
    # Build panel configurations
    panels = []
    references = []
    
    # Panel 1: Total Containers (Metric)
    panels.append(create_metric_panel(
        panel_index="1", title="Total Containers",
        x=0, y=0, w=8, h=5,
        source_field="container_name", operation="unique_count",
        layer_id="layer1"
    ))
    references.append({"id": DATA_VIEW_ID, "name": "1:indexpattern-datasource-layer-layer1", "type": "index-pattern"})
    
    # Panel 2: Avg CPU %
    panels.append(create_metric_panel(
        panel_index="2", title="Avg CPU %",
        x=8, y=0, w=8, h=5,
        source_field="cpu_percent", operation="average",
        layer_id="layer2"
    ))
    references.append({"id": DATA_VIEW_ID, "name": "2:indexpattern-datasource-layer-layer2", "type": "index-pattern"})
    
    # Panel 3: Avg Memory MB
    panels.append(create_metric_panel(
        panel_index="3", title="Avg Memory MB",
        x=16, y=0, w=8, h=5,
        source_field="memory_usage_mb", operation="average",
        layer_id="layer3"
    ))
    references.append({"id": DATA_VIEW_ID, "name": "3:indexpattern-datasource-layer-layer3", "type": "index-pattern"})
    
    # Panel 4: Total Network RX MB
    panels.append(create_metric_panel(
        panel_index="4", title="Total Network RX",
        x=24, y=0, w=8, h=5,
        source_field="network_rx_mb", operation="sum",
        layer_id="layer4"
    ))
    references.append({"id": DATA_VIEW_ID, "name": "4:indexpattern-datasource-layer-layer4", "type": "index-pattern"})
    
    # Panel 5: Total Network TX MB
    panels.append(create_metric_panel(
        panel_index="5", title="Total Network TX",
        x=32, y=0, w=8, h=5,
        source_field="network_tx_mb", operation="sum",
        layer_id="layer5"
    ))
    references.append({"id": DATA_VIEW_ID, "name": "5:indexpattern-datasource-layer-layer5", "type": "index-pattern"})
    
    # Panel 6: Avg PIDs
    panels.append(create_metric_panel(
        panel_index="6", title="Avg PIDs",
        x=40, y=0, w=8, h=5,
        source_field="pids", operation="average",
        layer_id="layer6"
    ))
    references.append({"id": DATA_VIEW_ID, "name": "6:indexpattern-datasource-layer-layer6", "type": "index-pattern"})
    
    # Panel 7: CPU Usage Over Time (Line chart)
    panels.append(create_xy_panel(
        panel_index="7", title="CPU Usage Over Time (%)",
        x=0, y=5, w=24, h=12,
        source_field="cpu_percent", series_type="line",
        layer_id="layer7"
    ))
    references.append({"id": DATA_VIEW_ID, "name": "7:indexpattern-datasource-layer-layer7", "type": "index-pattern"})
    
    # Panel 8: Memory Usage Over Time (Area chart)
    panels.append(create_xy_panel(
        panel_index="8", title="Memory Usage Over Time (MB)",
        x=24, y=5, w=24, h=12,
        source_field="memory_usage_mb", series_type="area",
        layer_id="layer8"
    ))
    references.append({"id": DATA_VIEW_ID, "name": "8:indexpattern-datasource-layer-layer8", "type": "index-pattern"})
    
    # Panel 9: Network I/O (Line chart with 2 metrics)
    panels.append(create_xy_panel_dual(
        panel_index="9", title="Network I/O (MB)",
        x=0, y=17, w=24, h=12,
        source_field1="network_rx_mb", label1="RX",
        source_field2="network_tx_mb", label2="TX",
        series_type="line",
        layer_id="layer9"
    ))
    references.append({"id": DATA_VIEW_ID, "name": "9:indexpattern-datasource-layer-layer9", "type": "index-pattern"})
    
    # Panel 10: Block I/O (Area chart with 2 metrics)
    panels.append(create_xy_panel_dual(
        panel_index="10", title="Block I/O (MB)",
        x=24, y=17, w=24, h=12,
        source_field1="block_read_mb", label1="Read",
        source_field2="block_write_mb", label2="Write",
        series_type="area",
        layer_id="layer10"
    ))
    references.append({"id": DATA_VIEW_ID, "name": "10:indexpattern-datasource-layer-layer10", "type": "index-pattern"})
    
    # Panel 11: Container Statistics Table
    panels.append(create_table_panel(
        panel_index="11", title="Container Statistics",
        x=0, y=29, w=48, h=10,
        layer_id="layer11"
    ))
    references.append({"id": DATA_VIEW_ID, "name": "11:indexpattern-datasource-layer-layer11", "type": "index-pattern"})
    
    # Dashboard payload for saved objects API
    dashboard_payload = {
        "attributes": {
            "title": "Docker Stack Performance Monitor",
            "description": "Real-time monitoring of Docker container performance with 5-second auto-refresh",
            "panelsJSON": json.dumps(panels),
            "optionsJSON": json.dumps({
                "useMargins": True,
                "syncColors": True,
                "syncCursor": True,
                "syncTooltips": True,
                "hidePanelTitles": False
            }),
            "timeRestore": True,
            "timeTo": "now",
            "timeFrom": "now-15m",
            "refreshInterval": {
                "pause": False,
                "value": 5000  # 5 seconds
            },
            "kibanaSavedObjectMeta": {
                "searchSourceJSON": json.dumps({
                    "query": {"language": "kuery", "query": ""},
                    "filter": []
                })
            },
            "version": 3
        },
        "references": references
    }
    
    try:
        resp = requests.post(
            f"{KIBANA_URL}/api/saved_objects/dashboard/{DASHBOARD_ID}",
            headers={**HEADERS, 'Content-Type': 'application/json'},
            json=dashboard_payload,
            timeout=30
        )
        
        if resp.status_code in (200, 201):
            print(f"✓ Created dashboard: {DASHBOARD_ID}")
            return True
        else:
            print(f"✗ Failed to create dashboard: {resp.status_code}")
            print(resp.text[:500] if resp.text else "No response body")
            return False
    except Exception as e:
        print(f"✗ Error creating dashboard: {e}")
        return False


def main():
    print("=" * 60)
    print("Docker Stack Profiler - Kibana Dashboard Creator")
    print("=" * 60)
    print()
    
    # Wait for Kibana
    if not wait_for_kibana():
        print("ERROR: Kibana is not available")
        return 1
    
    # Check for data
    if not check_data_exists():
        print("\nWARNING: No data in docker-container-metrics index!")
        print("Run the profiler first: python profiler.py")
        print("Continuing anyway to create dashboard structure...\n")
    
    # Delete existing objects
    delete_existing_objects()
    
    # Create data view
    if not create_data_view():
        print("ERROR: Failed to create data view")
        return 1
    
    # Create dashboard using saved objects API
    if not create_dashboard():
        print("ERROR: Failed to create dashboard")
        return 1
    
    dashboard_url = f"{KIBANA_URL}/app/dashboards#/view/{DASHBOARD_ID}"
    
    print()
    print("=" * 60)
    print("✓ Dashboard created successfully!")
    print("=" * 60)
    print()
    print(f"Dashboard URL: {dashboard_url}")
    print()
    print("Features:")
    print("  • Auto-refresh every 5 seconds")
    print("  • 6 metric cards (Containers, CPU, Memory, Network, PIDs)")
    print("  • CPU usage per container over time (line chart)")
    print("  • Memory usage per container over time (area chart)")
    print("  • Network I/O visualization (RX/TX)")
    print("  • Block I/O visualization (Read/Write)")
    print("  • Real-time container statistics table")
    print()
    print("=" * 60)
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
