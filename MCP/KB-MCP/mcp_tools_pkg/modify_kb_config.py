import time
import uuid
from typing import List
from mcp.server.fastmcp.exceptions import ToolError
from models import AlgorithmConfig
from validation import validate_algorithms
from .algorithms import parse_algorithms_to_internal_format

from utils import log_message as _utils_log_message
from db import connect_mongodb


def log_message(message: str, level: str = "info", component: str = "mcp_tools", method: str = "entry", **kwargs):
    return _utils_log_message(message, level, component, method, **kwargs)


def modify_kb_config(
    config_id: str,
    description: str = None,
    training_query: str = None,
    detection_query: str = None,
    training_from: str = None,
    training_to: str = None,
    detection_frequency: str = None,
    detection_start: str = None,
    algorithms: List[AlgorithmConfig] = None
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

        # Validate provided fields using Pydantic models
        validated_updates = {}

        # Validate description if provided
        if description is not None:
            if not isinstance(description, str) or not description.strip():
                raise ToolError("description must be a non-empty string")
            validated_updates["description"] = description

        # Validate training_query if provided
        if training_query is not None:
            if not isinstance(training_query, str) or not training_query.strip():
                raise ToolError("training_query must be a non-empty string")
            # Use lightweight validation helper to extract output fields
            try:
                from validation import extract_sql_output_fields
                _ = extract_sql_output_fields(training_query)
                validated_updates["scheduling.training_config.training_query"] = training_query
            except Exception as e:
                raise ToolError(f"Invalid training query: {str(e)}")

        # Validate detection_query if provided
        if detection_query is not None:
            if not isinstance(detection_query, str) or not detection_query.strip():
                raise ToolError("detection_query must be a non-empty string")
            try:
                from validation import extract_sql_output_fields
                _ = extract_sql_output_fields(detection_query)
                validated_updates["scheduling.detection_config.detection_query"] = detection_query
            except Exception as e:
                raise ToolError(f"Invalid detection query: {str(e)}")

        # Validate timestamps using Pydantic field validation
        if training_from is not None:
            try:
                from models import TrainingConfig
                # Create a minimal instance to validate the timestamp
                TrainingConfig(training_query="dummy", **{"from": training_from}, to="2025-01-01T00:00:00Z", training_window=3600, is_active=True)
                validated_updates["scheduling.training_config.from"] = training_from
            except Exception as e:
                raise ToolError(f"Invalid training_from: {str(e)}")

        if training_to is not None:
            try:
                from models import TrainingConfig
                TrainingConfig(training_query="dummy", **{"from": "2025-01-01T00:00:00Z"}, to=training_to, training_window=3600, is_active=True)
                validated_updates["scheduling.training_config.to"] = training_to
            except Exception as e:
                raise ToolError(f"Invalid training_to: {str(e)}")

        if detection_start is not None:
            try:
                from models import DetectionConfig
                DetectionConfig(detection_query="dummy", **{"from": detection_start}, frequency="* * * * *", detection_window=3600, is_active=True)
                validated_updates["scheduling.detection_config.from"] = detection_start
            except Exception as e:
                raise ToolError(f"Invalid detection_start: {str(e)}")

        # Validate detection_frequency using CRON model
        if detection_frequency is not None:
            try:
                from models import CRON, DetectionConfig
                DetectionConfig(detection_query="dummy", **{"from": "2025-01-01T00:00:00Z"}, frequency=detection_frequency, detection_window=3600, is_active=True)
                validated_updates["scheduling.detection_config.frequency"] = detection_frequency
            except Exception as e:
                raise ToolError(f"Invalid detection_frequency: {str(e)}")

        # Validate algorithms using Pydantic models
        if algorithms is not None:
            try:
                from models import AlgorithmConfigItem, AlgorithmParameter

                # Convert and validate algorithms
                validated_algorithms = []
                for alg in algorithms:
                    if hasattr(alg, 'alg_name') and hasattr(alg, 'alg_parameters'):
                        # Already in AlgorithmConfigItem format
                        validated_alg = AlgorithmConfigItem(
                            alg_name=alg.alg_name,
                            alg_parameters=[AlgorithmParameter(dimension=param.dimension) for param in alg.alg_parameters]
                        )
                    elif hasattr(alg, 'algorithm') and hasattr(alg, 'dimensions'):
                        # ZScoreConfig format: {"algorithm": "zscore", "dimensions": ["dim1", "dim2"]}
                        alg_name = alg.algorithm
                        dimensions = alg.dimensions
                        
                        alg_params = [AlgorithmParameter(dimension=dim) for dim in dimensions]
                        validated_alg = AlgorithmConfigItem(
                            alg_name=alg_name,
                            alg_parameters=alg_params
                        )
                    elif isinstance(alg, dict):
                        # Dictionary format: {"algorithm": "zscore", "dimensions": ["dim1", "dim2"]}
                        alg_name = alg.get('algorithm') or alg.get('alg_name', 'zscore')
                        dimensions = alg.get('dimensions', [])
                        
                        alg_params = [AlgorithmParameter(dimension=dim) for dim in dimensions]
                        validated_alg = AlgorithmConfigItem(
                            alg_name=alg_name,
                            alg_parameters=alg_params
                        )
                    else:
                        # Try to convert from other formats
                        alg_params = []
                        if hasattr(alg, 'alg_parameters'):
                            for param in alg.alg_parameters:
                                if hasattr(param, 'dimension'):
                                    alg_params.append(AlgorithmParameter(dimension=param.dimension))
                        validated_alg = AlgorithmConfigItem(
                            alg_name=getattr(alg, 'alg_name', getattr(alg, 'algorithm', 'zscore')),
                            alg_parameters=alg_params
                        )
                    validated_algorithms.append(validated_alg)

                # Parse algorithms to internal format
                internal_algorithms = parse_algorithms_to_internal_format(validated_algorithms)

                algorithm_errors = validate_algorithms(internal_algorithms)
                if algorithm_errors:
                    error_msg = "Algorithm validation failed:\n" + "\n".join(f"- {err}" for err in algorithm_errors)
                    raise ToolError(error_msg)
                validated_updates["algorithms"] = internal_algorithms

            except Exception as e:
                raise ToolError(f"Algorithm validation failed: {str(e)}")

        if not validated_updates:
            log_message("No valid updates provided", "warning", "modify_kb_config", "validation",
                        request_id=request_id, extra_data={"config_id": config_id})
            raise ToolError("No valid updates provided")

        # Apply updates
        updates = validated_updates.copy()
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

