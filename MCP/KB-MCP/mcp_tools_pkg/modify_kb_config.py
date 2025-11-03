import time
import uuid
from mcp.server.fastmcp.exceptions import ToolError
from validation import validate_algorithms

from utils import log_message as _utils_log_message
from db import connect_mongodb


def log_message(message: str, level: str = "info", component: str = "mcp_tools", method: str = "entry", **kwargs):
    return _utils_log_message(message, level, component, method, **kwargs)


__tool_description__ = "Update an existing configuration by config_id. Supply any fields from creation to update them (description, queries, scheduling, algorithms). Returns confirmation or validation errors."


def modify_kb_config(
    config_id: str,
    description: str = None,
    training_query: str = None,
    detection_query: str = None,
    training_from: str = None,
    training_to: str = None,
    detection_frequency: str = None,
    detection_start: str = None,
    algorithms: dict = None
) -> str:
    request_id = str(uuid.uuid4())[:8]
    start_time = time.time()

    log_message("Tool execution started", "info", "modify_kb_config", "entry",
                request_id=request_id, extra_data={"config_id": config_id})

    client = connect_mongodb()
    if client is None:
        raise ToolError("Failed to connect to MongoDB")

    try:
        import db
        db_instance = client[db.db_kb_name]
        collection = db_instance[db.db_kb_collection_name]

        try:
            from bson import ObjectId
            config_doc = collection.find_one({"_id": ObjectId(config_id)})
        except Exception as e:
            raise ToolError(f"Invalid configuration ID format: '{config_id}' - {str(e)}")

        if not config_doc:
            raise ToolError(f"Configuration with ID '{config_id}' not found")

        updates = {}

        if description is not None:
            updates["description"] = description

        if training_query is not None:
            # Use lightweight validation helper to extract output fields instead of requiring SQL class
            try:
                from validation import extract_sql_output_fields
                _ = extract_sql_output_fields(training_query)
                updates["scheduling.training_config.training_query"] = training_query
            except Exception as e:
                raise ToolError(f"Invalid training query: {str(e)}")

        if detection_query is not None:
            try:
                from validation import extract_sql_output_fields
                _ = extract_sql_output_fields(detection_query)
                updates["scheduling.detection_config.detection_query"] = detection_query
            except Exception as e:
                raise ToolError(f"Invalid detection query: {str(e)}")

        if training_from is not None:
            updates["scheduling.training_config.from"] = training_from

        if training_to is not None:
            updates["scheduling.training_config.to"] = training_to

        if detection_frequency is not None:
            try:
                from models import CRON
                CRON(detection_frequency)
                updates["scheduling.detection_config.frequency"] = detection_frequency
            except ValueError as e:
                raise ToolError(f"Invalid detection frequency: {str(e)}")

        if detection_start is not None:
            updates["scheduling.detection_config.from"] = detection_start

        if algorithms is not None:
            # Accept dict/list inputs from MCP client; coerce into storage format used by validate_algorithms
            algs_to_validate = algorithms
            if isinstance(algorithms, dict):
                algs_to_validate = [algorithms]
            algorithm_errors = validate_algorithms(algs_to_validate)
            if algorithm_errors:
                error_msg = "Algorithm validation failed:\n" + "\n".join(f"- {err}" for err in algorithm_errors)
                raise ToolError(error_msg)
            updates["algorithms"] = algs_to_validate

        if not updates:
            log_message("No valid updates provided", "warning", "modify_kb_config", "validation",
                        request_id=request_id, extra_data={"config_id": config_id})
            raise ToolError("No valid updates provided")

        updates["change_flag"] = config_doc.get("change_flag", 0) + 1

        result = collection.update_one(
            {"_id": ObjectId(config_id)},
            {"$set": updates}
        )

        if result.modified_count == 0:
            log_message("No changes were made to the configuration", "warning",
                        "modify_kb_config", "update", request_id=request_id,
                        extra_data={"config_id": config_id})
            raise ToolError("No changes were made to the configuration")

        updated_doc = collection.find_one({"_id": ObjectId(config_id)}, {"_id": 0})
        duration_ms = (time.time() - start_time) * 1000

        if updated_doc:
            log_message(f"Configuration '{config_id}' updated successfully", "info",
                       "modify_kb_config", "completion", request_id=request_id,
                       duration_ms=duration_ms, extra_data={"config_id": config_id})
            return f"SUCCESS: Configuration '{config_id}' updated successfully."
        else:
            log_message(f"Configuration '{config_id}' updated but could not retrieve document", "warning",
                       "modify_kb_config", "completion", request_id=request_id,
                       duration_ms=duration_ms, extra_data={"config_id": config_id})
            return f"SUCCESS: Configuration '{config_id}' updated successfully, but could not retrieve updated document."

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_message(f"Error modifying configuration {config_id}: {str(e)}", "error",
                    "modify_kb_config", "error", request_id=request_id,
                    duration_ms=duration_ms, extra_data={"config_id": config_id, "error_type": type(e).__name__})
        raise ToolError(f"Failed to modify configuration: {str(e)}")
    finally:
        try:
            client.close()
        except:
            pass

