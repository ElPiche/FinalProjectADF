import uuid
import time
import json
from typing import List
from pydantic import Field

from mcp.server.fastmcp.exceptions import ToolError

from models import ZScoreConfig, AlgorithmConfig
from db import connect_mongodb
from validation import validate_algorithms
from utils import log_message as _utils_log_message


def log_message(message: str, level: str = "info", component: str = "mcp_tools", method: str = "entry", **kwargs):
    return _utils_log_message(message, level, component, method, **kwargs)


def create_da_config(
    name: str = Field(description="Configuration name"),
    description: str = Field(description="Human-readable description"),
    training_query: str = Field(description="SQL query for training data"),
    detection_query: str = Field(description="SQL query for detection"),
    training_from: str = Field(description="Training start timestamp (ISO format)"),
    training_to: str = Field(description="Training end timestamp (ISO format)"),
    detection_frequency: str = Field(description="Detection frequency (CRON format)"),
    detection_start: str = Field(description="Detection start timestamp (ISO format)"),
    algorithms: List[AlgorithmConfig] = Field(description="List of algorithm configurations")
) -> str:
    request_id = str(uuid.uuid4())[:8]
    start_time = time.time()

    log_message("Tool execution started", "info", "create_da_config", "entry",
                request_id=request_id, extra_data={
                    "config_name": name,
                    "algorithm_count": len(algorithms) if algorithms else 0
                })

    if not name or not isinstance(name, str):
        raise ToolError("name must be a non-empty string")
    if not description or not isinstance(description, str):
        raise ToolError("description must be a non-empty string")

    try:
        from models import CRON
        CRON(detection_frequency)
    except ValueError as e:
        raise ToolError(f"Invalid detection frequency CRON: {str(e)}")

    internal_algorithms = []
    # Be permissive with the MCP JSON input: accept a list of dicts, a single dict, or Pydantic model
    alg_items = algorithms or []
    if isinstance(alg_items, dict):
        alg_items = [alg_items]

    for alg_input in (alg_items or []):
        try:
            alg_config = None
            # If MCP sent a dict, try to coerce into the known model(s)
            if isinstance(alg_input, dict):
                # Accept either legacy keys or pydantic-shaped dicts
                try:
                    alg_config = ZScoreConfig(**alg_input)
                except Exception:
                    # Try alternative key shapes: {"className": "ZScore", "parameters": {...}}
                    cls_name = alg_input.get("className") or alg_input.get("name")
                    params = alg_input.get("parameters") or alg_input.get("params") or alg_input.get("parameters", {})
                    if cls_name and str(cls_name).lower().startswith("zscore"):
                        # Build a minimal ZScoreConfig-like object from provided params
                        dims = []
                        if isinstance(params, dict) and params.get("observedValue"):
                            dims = [params.get("observedValue")]
                        elif isinstance(params, dict) and params.get("dimensions"):
                            dims = params.get("dimensions")
                        elif isinstance(params, list):
                            dims = params
                        alg_config = ZScoreConfig(dimensions=dims)
            elif isinstance(alg_input, ZScoreConfig):
                alg_config = alg_input
            else:
                # Last resort: try to interpret strings as algorithm names
                if isinstance(alg_input, str) and alg_input.lower().startswith("zscore"):
                    alg_config = ZScoreConfig(dimensions=[])

            if alg_config is None:
                raise ToolError(f"Unsupported algorithm type: {type(alg_input)}")

            # Only zscore is supported at the moment
            if isinstance(alg_config, ZScoreConfig):
                internal_algorithms.append({
                    "alg_name": "zscore",
                    "alg_parameters": [{"dimension": dim} for dim in alg_config.dimensions]
                })
            else:
                raise ToolError(f"Unsupported algorithm type after parsing: {type(alg_config)}")

        except ToolError:
            # Re-raise our ToolError without additional wrapping
            raise
        except Exception as e:
            # Log parsing error and raise a ToolError to surface it to the caller
            log_message(f"Algorithm parsing/validation failed: {str(e)}", "error",
                        "create_da_config", "validation", request_id=request_id,
                        extra_data={"alg_input": alg_input})
            raise ToolError(f"Algorithm configuration invalid: {str(e)}")

    algorithm_errors = validate_algorithms(internal_algorithms)
    if algorithm_errors:
        error_msg = "Algorithm validation failed:\n" + "\n".join(f"- {err}" for err in algorithm_errors)
        log_message(f"Algorithm validation failed: {len(algorithm_errors)} errors", "error",
                    "create_da_config", "validation", request_id=request_id)
        raise ToolError(error_msg)

    # Cross-validate algorithms against SQL queries
    from .elasticsearch_sql import elasticsearch_sql

    if training_query:
        validation_result = elasticsearch_sql(training_query + " LIMIT 0")
        if "ERROR" in validation_result:
            raise ToolError(f"Training SQL query validation failed: {validation_result}")
        else:
            try:
                result_data = json.loads(validation_result)
                available_fields = [col['name'] for col in result_data.get('columns', [])]

                for alg_config in algorithms:
                    if isinstance(alg_config, ZScoreConfig):
                        for dimension in alg_config.dimensions:
                            if dimension not in available_fields:
                                raise ToolError(f"Dimension '{dimension}' not found in training query output. Available fields: {available_fields}")
            except json.JSONDecodeError:
                raise ToolError("Could not parse training SQL validation response")

    if detection_query:
        validation_result = elasticsearch_sql(detection_query + " LIMIT 0")
        if "ERROR" in validation_result:
            raise ToolError(f"Detection SQL query validation failed: {validation_result}")
        else:
            try:
                result_data = json.loads(validation_result)
                available_fields = [col['name'] for col in result_data.get('columns', [])]

                for alg_config in algorithms:
                    if isinstance(alg_config, ZScoreConfig):
                        for dimension in alg_config.dimensions:
                            if dimension not in available_fields:
                                raise ToolError(f"Dimension '{dimension}' not found in detection query output. Available fields: {available_fields}")
            except json.JSONDecodeError:
                raise ToolError("Could not parse detection SQL validation response")

    config_to_store = {
        "name": name,
        "description": description,
        "change_flag": 0,
        "scheduling": {
            "training_config": {
                "training_query": training_query,
                "from": training_from,
                "to": training_to,
                "training_window": 3600,
                "is_active": True
            },
            "detection_config": {
                "detection_query": detection_query,
                "from": detection_start,
                "frequency": detection_frequency,
                "detection_window": 3600,
                "is_active": False
            }
        },
        "algorithms": internal_algorithms
    }

    log_message(f"Configuration validation successful for: {name}", "info",
                "create_da_config", "validation", request_id=request_id)

    print("\nConfiguration Preview:")
    print(json.dumps(config_to_store, indent=2))
    print()

    client = connect_mongodb()
    if client is None:
        error_msg = "Failed to connect to MongoDB - configuration not saved"
        log_message(error_msg, "error", "create_da_config", "save", request_id=request_id)
        raise ToolError(error_msg)

    try:
        import db
        db_instance = client[db.db_kb_name]
        collection = db_instance[db.db_kb_collection_name]

        result = collection.insert_one(config_to_store)
        document_id = str(result.inserted_id)

        duration_ms = (time.time() - start_time) * 1000
        success_msg = f"SUCCESS: Configuration saved to MongoDB!\n\nDocument ID: {document_id}\n\nConfiguration saved successfully."
        log_message("Configuration creation completed successfully", "info",
                    "create_da_config", "completion", request_id=request_id,
                    duration_ms=duration_ms, extra_data={"document_id": document_id})
        return success_msg

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        error_msg = f"Failed to save configuration: {str(e)}"
        log_message(error_msg, "error", "create_da_config", "save", request_id=request_id,
                    duration_ms=duration_ms, extra_data={"error_type": type(e).__name__})
        raise ToolError(error_msg)
    finally:
        try:
            client.close()
        except:
            pass
