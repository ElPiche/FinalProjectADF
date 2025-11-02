import uuid
import time
import json
from mcp.server.fastmcp.exceptions import ToolError
from db import connect_mongodb
from utils import log_message as _utils_log_message


def log_message(message: str, level: str = "info", component: str = "mcp_tools", method: str = "entry", **kwargs):
    return _utils_log_message(message, level, component, method, **kwargs)


def list_kb_configurations() -> str:
    request_id = str(uuid.uuid4())[:8]
    start_time = time.time()

    log_message("Tool execution started", "info", "list_kb_configurations", "entry",
                request_id=request_id)

    client = connect_mongodb()
    if client is None:
        raise ToolError("Failed to connect to MongoDB")

    try:
        import db
        db_instance = client[db.db_kb_name]
        collection = db_instance[db.db_kb_collection_name]

        configs = list(collection.find({}, {}))

        if not configs:
            log_message("No KB configurations found in database", "info",
                        "list_kb_configurations", "query", request_id=request_id)
            return "No KB configurations found in the database."

        log_message(f"Found {len(configs)} configurations in database", "info",
                    "list_kb_configurations", "query", request_id=request_id,
                    extra_data={"config_count": len(configs)})
        output = "# KB Configurations Summary\n\n"
        output += f"Found {len(configs)} configuration(s):\n\n"

        for config_doc in configs:
            kb_config = config_doc

            config_id = str(kb_config.get("_id", "Unknown"))
            name = kb_config.get("name", "Unknown")
            description = kb_config.get("description", "No description")

            algorithms_list = kb_config.get("algorithms", [])
            algorithms = []
            for alg_config in algorithms_list:
                alg_name = alg_config.get("alg_name", "unknown")
                alg_parameters = alg_config.get("alg_parameters", [])
                dimensions = [p.get("dimension", "unknown") for p in alg_parameters if isinstance(p, dict)]
                algorithms.append(f"{alg_name}({', '.join(dimensions)})")

            scheduling = kb_config.get("scheduling", {})
            training_config = scheduling.get("training_config", {})
            detection_config = scheduling.get("detection_config", {})

            training_from = training_config.get("from", "Unknown")
            training_to = training_config.get("to", "Unknown")
            detection_freq = detection_config.get("frequency", "Unknown")
            detection_from = detection_config.get("from", "Unknown")

            output += f"## Configuration: {name}\n"
            output += f"- **ID**: {config_id}\n"
            output += f"- **Description**: {description}\n"
            output += f"- **Algorithms**: {', '.join(algorithms) if algorithms else 'None'}\n"
            output += f"- **Training Period**: {training_from} to {training_to}\n"
            output += f"- **Detection**: Every {detection_freq} starting {detection_from}\n\n"

        duration_ms = (time.time() - start_time) * 1000
        log_message(f"Configurations list generated successfully", "info",
                    "list_kb_configurations", "completion", request_id=request_id,
                    duration_ms=duration_ms, extra_data={"config_count": len(configs)})
        return output

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_message(f"Error listing configurations: {str(e)}", "error",
                    "list_kb_configurations", "error", request_id=request_id,
                    duration_ms=duration_ms, extra_data={"error_type": type(e).__name__})
        raise ToolError(f"Failed to list configurations: {str(e)}")
    finally:
        try:
            client.close()
        except:
            pass
