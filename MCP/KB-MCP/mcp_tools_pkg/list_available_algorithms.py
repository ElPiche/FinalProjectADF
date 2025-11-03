import time
import uuid
import json
from utils import log_message as _utils_log_message


def log_message(message: str, level: str = "info", component: str = "mcp_tools", method: str = "entry", **kwargs):
    return _utils_log_message(message, level, component, method, **kwargs)


__tool_description__ = "List available DA algorithms with canonical parameter names, short descriptions, example configs that match the KBConfigTemplate.json. Current implementation: only 'zscore' is implemented; 'kmeans' is planned." 


def list_available_algorithms() -> str:
    request_id = str(uuid.uuid4())[:8]
    start_time = time.time()

    log_message("Tool execution started", "info", "list_available_algorithms", "entry",
                request_id=request_id)

    # Only expose currently supported algorithms and format examples to match
    # the KB config template: each algorithm is represented by 'alg_name' and
    # 'alg_parameters' (an array of parameter objects). We keep the metadata
    # concise and canonical (use 'dimension').
    algorithm_specs = {
        "zscore": {
            "alg_name": "zscore",
            "description": "Statistical anomaly detection using z-score thresholds",
            "example_config": {
                "alg_name": "zscore",
                "alg_parameters": [
                    {"dimension": "status_code_200_counter"},
                    {"dimension": "status_code_5xx_counter"}
                ]
            },
            "parameters": [
                {"name": "dimension", "type": "string", "required": True, "description": "Canonical metric field name from SQL output to monitor for anomalies."}
            ]
        },
        "kmeans": {
            "alg_name": "kmeans",
            "description": "Clustering-based anomaly detection (KMeans)",
            "example_config": {
                "alg_name": "kmeans",
                "alg_parameters": [
                    {"dimension": "status_code_5xx_counter", "alg_metadata": [{"key": "clusters", "values": "3"}]},
                    {"dimension": "status_code_5xx_counter", "alg_metadata": [{"key": "clusters", "values": "5"}]}
                ]
            },
            "parameters": [
                {"name": "dimension", "type": "string", "required": True, "description": "Canonical field to cluster (dimension)."},
                {"name": "alg_metadata", "type": "array", "required": False, "description": "Optional key/value metadata for algorithm parameters (e.g., clusters)."}
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
            alg_info["status"] = "Not implemented"
            future_algorithms.append(alg_info)

    # Build a Markdown response for human/AI callers (matching style used by
    # `list_kb_configurations`) which includes implemented/planned lists and a
    # JSON example showing how to fill the 'algorithms' section in
    # KBConfigTemplate.json.
    md_lines = []
    md_lines.append("# Available Anomaly Detection Algorithms\n")

    md_lines.append("## Implemented\n")
    for a in available_algorithms:
        md_lines.append(f"- **{a.get('alg_name', a.get('name', 'unknown'))}**: {a.get('description', '')}  ")

    md_lines.append("\n## Planned / Not implemented\n")
    for a in future_algorithms:
        md_lines.append(f"- **{a.get('alg_name', a.get('name', 'unknown'))}**: {a.get('description', '')}  ")

    md_lines.append("\n## Usage notes\n")
    md_lines.append("- All algorithms require the `dimension` field to match an output field from your SQL query.")
    md_lines.append("- Algorithm parameters are validated during configuration creation.")

    # Add a concrete JSON example showing the 'algorithms' portion of KBConfigTemplate.json
    example_algorithms = [
        available_algorithms[0]['example_config'],
        future_algorithms[0]['example_config']
    ]
    md_lines.append("\n## Example: how to fill the 'algorithms' section in KBConfigTemplate.json\n")
    md_lines.append("```json")
    md_lines.append(json.dumps({"algorithms": example_algorithms}, indent=2))
    md_lines.append("```")

    duration_ms = (time.time() - start_time) * 1000
    log_message("Algorithm list generated successfully (markdown)", "info",
                "list_available_algorithms", "completion", request_id=request_id,
                duration_ms=duration_ms, extra_data={
                    "available_count": len(available_algorithms),
                    "future_count": len(future_algorithms)
                })

    return "\n".join(md_lines)

