#!/usr/bin/env python3
"""
Setup Kibana Data View and Dashboard for Stack Profiler metrics.

This script creates:
1. A data view for 'docker-container-metrics*' index
2. Basic visualizations for monitoring container performance
"""

import os
import json
import time
import requests
from typing import Optional

KIBANA_URL = os.getenv('KIBANA_URL', 'http://localhost:5601')
INDEX_PATTERN = 'docker-container-metrics*'
DATA_VIEW_NAME = 'Docker Container Metrics'


def wait_for_kibana(max_retries: int = 30, delay: int = 2) -> bool:
    """Wait for Kibana to be ready."""
    print(f"Waiting for Kibana at {KIBANA_URL}...")
    
    for i in range(max_retries):
        try:
            response = requests.get(f"{KIBANA_URL}/api/status", timeout=5)
            if response.status_code == 200:
                status = response.json()
                if status.get('status', {}).get('overall', {}).get('level') == 'available':
                    print("Kibana is ready!")
                    return True
        except requests.exceptions.RequestException:
            pass
        
        print(f"  Retry {i + 1}/{max_retries}...")
        time.sleep(delay)
    
    return False


def check_data_exists(es_url: str = 'http://localhost:9200') -> bool:
    """Check if any data exists in the metrics index."""
    try:
        response = requests.get(f"{es_url}/docker-container-metrics/_count", timeout=5)
        if response.status_code == 200:
            count = response.json().get('count', 0)
            return count > 0
    except:
        pass
    return False


def create_data_view() -> Optional[str]:
    """Create a data view for the metrics index."""
    print(f"Creating data view for '{INDEX_PATTERN}'...")
    
    headers = {
        'kbn-xsrf': 'true',
        'Content-Type': 'application/json'
    }
    
    # Check if data view already exists
    try:
        response = requests.get(
            f"{KIBANA_URL}/api/data_views",
            headers=headers,
            timeout=10
        )
        if response.status_code == 200:
            data_views = response.json().get('data_view', [])
            for dv in data_views:
                if dv.get('title') == INDEX_PATTERN:
                    print(f"Data view already exists: {dv.get('id')}")
                    return dv.get('id')
    except Exception as e:
        print(f"Error checking data views: {e}")
    
    # Create new data view
    payload = {
        "data_view": {
            "title": INDEX_PATTERN,
            "name": DATA_VIEW_NAME,
            "timeFieldName": "@timestamp"
        }
    }
    
    try:
        response = requests.post(
            f"{KIBANA_URL}/api/data_views/data_view",
            headers=headers,
            json=payload,
            timeout=30
        )
        
        if response.status_code in (200, 201):
            data_view_id = response.json().get('data_view', {}).get('id')
            print(f"Created data view: {data_view_id}")
            return data_view_id
        else:
            print(f"Failed to create data view: {response.status_code}")
            print(response.text)
    except Exception as e:
        print(f"Error creating data view: {e}")
    
    return None


def create_dashboard(data_view_id: str) -> Optional[str]:
    """Create a monitoring dashboard with basic visualizations."""
    print("Creating dashboard...")
    
    headers = {
        'kbn-xsrf': 'true',
        'Content-Type': 'application/json'
    }
    
    # Dashboard definition with panels
    dashboard = {
        "attributes": {
            "title": "Docker Stack Performance Monitor",
            "description": "Real-time monitoring of Docker container performance metrics",
            "panelsJSON": json.dumps([
                {
                    "version": "8.10.0",
                    "type": "lens",
                    "gridData": {"x": 0, "y": 0, "w": 24, "h": 8, "i": "1"},
                    "panelIndex": "1",
                    "embeddableConfig": {
                        "attributes": {
                            "title": "CPU Usage Over Time",
                            "visualizationType": "lnsXY",
                            "state": {
                                "datasourceStates": {
                                    "formBased": {
                                        "layers": {
                                            "layer1": {
                                                "columns": {
                                                    "x-axis": {
                                                        "dataType": "date",
                                                        "sourceField": "@timestamp",
                                                        "operationType": "date_histogram",
                                                        "params": {"interval": "auto"}
                                                    },
                                                    "y-axis": {
                                                        "dataType": "number",
                                                        "sourceField": "cpu_percent",
                                                        "operationType": "average",
                                                        "label": "Avg CPU %"
                                                    },
                                                    "breakdown": {
                                                        "dataType": "string",
                                                        "sourceField": "container_name",
                                                        "operationType": "terms"
                                                    }
                                                },
                                                "columnOrder": ["breakdown", "x-axis", "y-axis"]
                                            }
                                        }
                                    }
                                },
                                "visualization": {
                                    "axisTitlesVisibilitySettings": {"x": True, "yLeft": True},
                                    "layers": [{
                                        "layerId": "layer1",
                                        "accessors": ["y-axis"],
                                        "xAccessor": "x-axis",
                                        "splitAccessor": "breakdown",
                                        "seriesType": "line"
                                    }]
                                }
                            },
                            "references": [{"type": "index-pattern", "id": data_view_id, "name": "indexpattern-datasource-layer-layer1"}]
                        }
                    }
                },
                {
                    "version": "8.10.0",
                    "type": "lens",
                    "gridData": {"x": 24, "y": 0, "w": 24, "h": 8, "i": "2"},
                    "panelIndex": "2",
                    "embeddableConfig": {
                        "attributes": {
                            "title": "Memory Usage Over Time",
                            "visualizationType": "lnsXY",
                            "state": {
                                "datasourceStates": {
                                    "formBased": {
                                        "layers": {
                                            "layer1": {
                                                "columns": {
                                                    "x-axis": {
                                                        "dataType": "date",
                                                        "sourceField": "@timestamp",
                                                        "operationType": "date_histogram",
                                                        "params": {"interval": "auto"}
                                                    },
                                                    "y-axis": {
                                                        "dataType": "number",
                                                        "sourceField": "memory_usage_mb",
                                                        "operationType": "average",
                                                        "label": "Avg Memory MB"
                                                    },
                                                    "breakdown": {
                                                        "dataType": "string",
                                                        "sourceField": "container_name",
                                                        "operationType": "terms"
                                                    }
                                                },
                                                "columnOrder": ["breakdown", "x-axis", "y-axis"]
                                            }
                                        }
                                    }
                                },
                                "visualization": {
                                    "axisTitlesVisibilitySettings": {"x": True, "yLeft": True},
                                    "layers": [{
                                        "layerId": "layer1",
                                        "accessors": ["y-axis"],
                                        "xAccessor": "x-axis",
                                        "splitAccessor": "breakdown",
                                        "seriesType": "area"
                                    }]
                                }
                            },
                            "references": [{"type": "index-pattern", "id": data_view_id, "name": "indexpattern-datasource-layer-layer1"}]
                        }
                    }
                }
            ]),
            "optionsJSON": json.dumps({"useMargins": True, "syncColors": False, "hidePanelTitles": False}),
            "timeRestore": True,
            "timeTo": "now",
            "timeFrom": "now-15m",
            "refreshInterval": {"pause": False, "value": 5000},
            "kibanaSavedObjectMeta": {
                "searchSourceJSON": json.dumps({"query": {"language": "kuery", "query": ""}, "filter": []})
            }
        }
    }
    
    try:
        response = requests.post(
            f"{KIBANA_URL}/api/saved_objects/dashboard",
            headers=headers,
            json=dashboard,
            timeout=30
        )
        
        if response.status_code in (200, 201):
            dashboard_id = response.json().get('id')
            print(f"Created dashboard: {dashboard_id}")
            print(f"\nDashboard URL: {KIBANA_URL}/app/dashboards#/view/{dashboard_id}")
            return dashboard_id
        else:
            print(f"Failed to create dashboard: {response.status_code}")
            print(response.text)
    except Exception as e:
        print(f"Error creating dashboard: {e}")
    
    return None


def main():
    print("=" * 60)
    print("Stack Profiler - Kibana Setup")
    print("=" * 60)
    print()
    
    # Wait for Kibana
    if not wait_for_kibana():
        print("Error: Kibana is not available")
        return 1
    
    print()
    
    # Check if data exists
    if not check_data_exists():
        print("Warning: No data found in docker-container-metrics index")
        print("Run the profiler first to collect some metrics, then run this setup again")
        print()
    
    # Create data view
    data_view_id = create_data_view()
    if not data_view_id:
        print("Failed to create data view")
        return 1
    
    print()
    print("=" * 60)
    print("Setup complete!")
    print()
    print(f"1. Open Kibana: {KIBANA_URL}")
    print(f"2. Go to Analytics > Discover")
    print(f"3. Select the '{DATA_VIEW_NAME}' data view")
    print(f"4. Explore your container metrics!")
    print()
    print("Tip: Create visualizations for CPU, Memory, Network I/O")
    print("=" * 60)
    
    return 0


if __name__ == '__main__':
    exit(main())
