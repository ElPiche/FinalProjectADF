import time
import uuid
import json
from utils import log_message as _utils_log_message


def log_message(message: str, level: str = "info", component: str = "mcp_tools", method: str = "entry", **kwargs):
    return _utils_log_message(level, component, method, message, **kwargs)


def list_available_algorithms() -> str:
    request_id = str(uuid.uuid4())[:8]
    start_time = time.time()

    log_message("Tool execution started", "info", "list_available_algorithms", "entry",
                request_id=request_id)

    algorithm_specs = {
        "ZScore": {
            "name": "ZScore",
            "description": "Statistical anomaly detection using standard deviation thresholds",
            "class_name": "ZScore",
            "parameters": [
                {
                    "name": "observedValue",
                    "type": "string",
                    "required": True,
                    "description": "Field name from SQL query output to monitor for anomalies"
                }
            ],
            "example": {
                "observedValue": "request_count"
            }
        },
        "ARMA": {
            "name": "ARMA",
            "description": "Time series forecasting using AutoRegressive Moving Average",
            "class_name": "ARMA",
            "parameters": [
                {"name": "p", "type": "integer", "description": "AR order"},
                {"name": "d", "type": "integer", "description": "Differencing order"},
                {"name": "q", "type": "integer", "description": "MA order"},
                {"name": "observedValue", "type": "string", "description": "Time series field"}
            ]
        },
        "KMeans": {
            "name": "KMeans",
            "description": "Clustering-based anomaly detection",
            "class_name": "KMeans",
            "parameters": [
                {"name": "nClusters", "type": "integer", "description": "Number of clusters"},
                {"name": "observedValue", "type": "string", "description": "Field to cluster"}
            ]
        },
        "IForest": {
            "name": "IForest",
            "description": "Isolation Forest anomaly detection",
            "class_name": "IForest",
            "parameters": [
                {"name": "nEstimators", "type": "integer", "description": "Number of trees"},
                {"name": "contamination", "type": "float", "description": "Expected anomaly ratio"},
                {"name": "randomState", "type": "integer", "description": "Random seed"},
                {"name": "observedValue", "type": "string", "description": "Field to analyze"}
            ]
        }
    }

    available_algorithms = []
    future_algorithms = []

    for alg_key, alg_spec in algorithm_specs.items():
        if alg_key.lower() in {"zscore"}:
            alg_info = alg_spec.copy()
            alg_info["status"] = "Implemented"
            available_algorithms.append(alg_info)
        else:
            alg_info = alg_spec.copy()
            alg_info["status"] = "Framework ready - implementation pending"
            future_algorithms.append(alg_info)

    algorithms_info = {
        "available_algorithms": available_algorithms,
        "future_algorithms": future_algorithms,
        "usage_notes": [
            "Only algorithms in SUPPORTED_ALGORITHMS can be used in configurations",
            "All algorithms require dimension to match SQL query output fields",
            "Framework is designed for easy addition of new algorithms",
            "Algorithm parameters are validated during configuration creation"
        ]
    }

    duration_ms = (time.time() - start_time) * 1000
    log_message("Algorithm list generated successfully", "info",
                "list_available_algorithms", "completion", request_id=request_id,
                duration_ms=duration_ms, extra_data={
                    "available_count": len(algorithms_info["available_algorithms"]),
                    "future_count": len(algorithms_info["future_algorithms"])
                })
    return json.dumps(algorithms_info, indent=2)

