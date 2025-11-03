import json
import time
import uuid
from typing import List

from mcp.server.fastmcp.exceptions import ToolError
from pydantic import ValidationError

from models import (
    AlgorithmConfig,
    AlgorithmConfigItem,
    DetectionConfig,
    KBConfig,
    SchedulingConfig,
    TrainingConfig,
)
from validation import validate_algorithms
from .algorithms import parse_algorithms_to_internal_format, validate_algorithm_dimensions
from .elasticsearch_sql import elasticsearch_sql
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
    algorithms: List[AlgorithmConfig] = None,
) -> str:
    request_id = str(uuid.uuid4())[:8]
    start_time = time.time()

    log_message(
        "Tool execution started",
        "info",
        "modify_kb_config",
        "entry",
        request_id=request_id,
        extra_data={"config_id": config_id},
    )

    client = connect_mongodb()
    if client is None:
        raise ToolError("Failed to connect to MongoDB")

    try:
        import db
        from bson import ObjectId

        db_instance = client[db.db_kb_name]
        collection = db_instance[db.db_kb_collection_name]

        try:
            object_id = ObjectId(config_id)
        except Exception as exc:
            raise ToolError(f"Invalid configuration ID format: '{config_id}' - {str(exc)}")

        config_doc = collection.find_one({"_id": object_id})
        if not config_doc:
            raise ToolError(f"Configuration with ID '{config_id}' not found")

        try:
            existing_config = KBConfig.model_validate({k: v for k, v in config_doc.items() if k != "_id"})
        except ValidationError as exc:
            raise ToolError(f"Stored configuration failed validation and cannot be updated: {exc}")

        updates_applied = False
        algorithms_updated = False
        training_query_updated = False
        detection_query_updated = False

        # Build updated configuration values, using existing as defaults
        updated_name = existing_config.name
        if description is not None:
            if not isinstance(description, str) or not description.strip():
                raise ToolError("description must be a non-empty string")
            cleaned_description = description.strip()
            if cleaned_description != existing_config.description:
                updated_description = cleaned_description
                updates_applied = True
            else:
                updated_description = existing_config.description
        else:
            updated_description = existing_config.description
        updated_change_flag = existing_config.change_flag + 1

        # Build training config updates
        training_config_updates = {}
        if training_query is not None:
            if not isinstance(training_query, str) or not training_query.strip():
                raise ToolError("training_query must be a non-empty string")
            cleaned_training_query = training_query.strip()
            if cleaned_training_query != existing_config.scheduling.training_config.training_query:
                training_config_updates["training_query"] = cleaned_training_query
                updates_applied = True
                training_query_updated = True

        if training_from is not None:
            if not isinstance(training_from, str) or not training_from.strip():
                raise ToolError("training_from must be a non-empty ISO timestamp string")
            if training_from != existing_config.scheduling.training_config.from_:
                training_config_updates["from_"] = training_from
                updates_applied = True

        if training_to is not None:
            if not isinstance(training_to, str) or not training_to.strip():
                raise ToolError("training_to must be a non-empty ISO timestamp string")
            if training_to != existing_config.scheduling.training_config.to:
                training_config_updates["to"] = training_to
                updates_applied = True

        # Build detection config updates
        detection_config_updates = {}
        if detection_query is not None:
            if not isinstance(detection_query, str) or not detection_query.strip():
                raise ToolError("detection_query must be a non-empty string")
            cleaned_detection_query = detection_query.strip()
            if cleaned_detection_query != existing_config.scheduling.detection_config.detection_query:
                detection_config_updates["detection_query"] = cleaned_detection_query
                updates_applied = True
                detection_query_updated = True

        if detection_start is not None:
            if not isinstance(detection_start, str) or not detection_start.strip():
                raise ToolError("detection_start must be a non-empty ISO timestamp string")
            if detection_start != existing_config.scheduling.detection_config.from_:
                detection_config_updates["from_"] = detection_start
                updates_applied = True

        if detection_frequency is not None:
            if not isinstance(detection_frequency, str) or not detection_frequency.strip():
                raise ToolError("detection_frequency must be a non-empty CRON expression")
            cleaned_detection_frequency = detection_frequency.strip()
            if cleaned_detection_frequency != existing_config.scheduling.detection_config.frequency:
                detection_config_updates["frequency"] = cleaned_detection_frequency
                updates_applied = True

        # Apply training config updates with validation
        if training_config_updates:
            try:
                updated_training_payload = existing_config.scheduling.training_config.model_dump()
                updated_training_payload.update(training_config_updates)
                updated_training_config = TrainingConfig.model_validate(updated_training_payload)
            except ValidationError as exc:
                raise ToolError(f"Invalid training configuration: {exc}")
        else:
            updated_training_config = existing_config.scheduling.training_config

        # Apply detection config updates with validation
        if detection_config_updates:
            try:
                updated_detection_payload = existing_config.scheduling.detection_config.model_dump()
                updated_detection_payload.update(detection_config_updates)
                updated_detection_config = DetectionConfig.model_validate(updated_detection_payload)
            except ValidationError as exc:
                raise ToolError(f"Invalid detection configuration: {exc}")
        else:
            updated_detection_config = existing_config.scheduling.detection_config

        # Build scheduling config
        try:
            updated_scheduling_config = SchedulingConfig(
                training_config=updated_training_config,
                detection_config=updated_detection_config
            )
        except ValidationError as exc:
            raise ToolError(f"Invalid scheduling configuration: {exc}")

        # Algorithm updates
        if algorithms is not None:
            try:
                validated_algorithm_items = []
                for alg in algorithms:
                    if isinstance(alg, AlgorithmConfigItem):
                        validated_algorithm_items.append(AlgorithmConfigItem.model_validate(alg.model_dump()))
                    elif isinstance(alg, dict):
                        validated_algorithm_items.append(AlgorithmConfigItem.model_validate(alg))
                    else:
                        raise ToolError(
                            f"Unsupported algorithm format: {type(alg)}. Expected AlgorithmConfigItem or dict with 'alg_name' and 'alg_parameters'."
                        )
            except ValidationError as exc:
                raise ToolError(f"Algorithm validation error: {exc}")

            existing_algorithms_dump = [alg.model_dump() for alg in existing_config.algorithms]
            new_algorithms_dump = [alg.model_dump() for alg in validated_algorithm_items]
            if new_algorithms_dump != existing_algorithms_dump:
                updated_algorithms = validated_algorithm_items
                updates_applied = True
                algorithms_updated = True
            else:
                updated_algorithms = existing_config.algorithms
        else:
            updated_algorithms = existing_config.algorithms

        if not updates_applied:
            log_message(
                "No valid updates provided",
                "warning",
                "modify_kb_config",
                "validation",
                request_id=request_id,
                extra_data={"config_id": config_id},
            )
            raise ToolError("No valid updates provided")

        # Build final configuration with validation
        try:
            new_config = KBConfig(
                name=updated_name,
                description=updated_description,
                change_flag=updated_change_flag,
                scheduling=updated_scheduling_config,
                algorithms=updated_algorithms
            )
        except ValidationError as exc:
            raise ToolError(f"Input validation failed: {exc}")

        # Validate time range logic if training times were updated
        if "from_" in training_config_updates or "to" in training_config_updates:
            from datetime import datetime
            try:
                training_from_dt = datetime.fromisoformat(new_config.scheduling.training_config.from_.replace('Z', '+00:00'))
                training_to_dt = datetime.fromisoformat(new_config.scheduling.training_config.to.replace('Z', '+00:00'))
                if training_to_dt <= training_from_dt:
                    raise ToolError("training_to must be after training_from")
            except ValueError as e:
                raise ToolError(f"Invalid timestamp format: {str(e)}")

        internal_algorithms = parse_algorithms_to_internal_format(new_config.algorithms)
        algorithm_errors = validate_algorithms(internal_algorithms)
        if algorithm_errors:
            error_msg = "Algorithm validation failed:\n" + "\n".join(f"- {err}" for err in algorithm_errors)
            raise ToolError(error_msg)

        validate_training_query = training_query_updated or algorithms_updated
        validate_detection_query = detection_query_updated or algorithms_updated

        if validate_training_query:
            validation_result = elasticsearch_sql(
                f"{new_config.scheduling.training_config.training_query} LIMIT 0"
            )
            if "ERROR" in validation_result:
                raise ToolError(f"Training SQL query validation failed: {validation_result}")
            try:
                result_data = json.loads(validation_result)
                available_fields = [col["name"] for col in result_data.get("columns", [])]
            except json.JSONDecodeError as exc:
                raise ToolError("Could not parse training SQL validation response") from exc

            validate_algorithm_dimensions(new_config.algorithms, available_fields, "training")

        if validate_detection_query:
            validation_result = elasticsearch_sql(
                f"{new_config.scheduling.detection_config.detection_query} LIMIT 0"
            )
            if "ERROR" in validation_result:
                raise ToolError(f"Detection SQL query validation failed: {validation_result}")
            try:
                result_data = json.loads(validation_result)
                available_fields = [col["name"] for col in result_data.get("columns", [])]
            except json.JSONDecodeError as exc:
                raise ToolError("Could not parse detection SQL validation response") from exc

            validate_algorithm_dimensions(new_config.algorithms, available_fields, "detection")

        payload = new_config.model_dump(by_alias=True)

        result = collection.update_one(
            {"_id": object_id},
            {"$set": payload},
        )

        if result.modified_count == 0:
            log_message(
                "No changes were made to the configuration",
                "warning",
                "modify_kb_config",
                "update",
                request_id=request_id,
                extra_data={"config_id": config_id},
            )
            raise ToolError("No changes were made to the configuration")

        duration_ms = (time.time() - start_time) * 1000
        log_message(
            f"Configuration '{config_id}' updated successfully",
            "info",
            "modify_kb_config",
            "completion",
            request_id=request_id,
            duration_ms=duration_ms,
            extra_data={"config_id": config_id},
        )
        return f"SUCCESS: Configuration '{config_id}' updated successfully."

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_message(
            f"Error modifying configuration {config_id}: {str(e)}",
            "error",
            "modify_kb_config",
            "error",
            request_id=request_id,
            duration_ms=duration_ms,
            extra_data={"config_id": config_id, "error_type": type(e).__name__},
        )
        raise ToolError(f"Failed to modify configuration: {str(e)}")
    finally:
        try:
            client.close()
        except:  # best effort cleanup
            pass