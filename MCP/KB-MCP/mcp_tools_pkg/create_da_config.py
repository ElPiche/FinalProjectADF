import uuid
import time
import json
from typing import List
from pydantic import Field

from mcp.server.fastmcp.exceptions import ToolError

from models import AlgorithmConfig
from db import connect_mongodb
from validation import validate_algorithms
from utils import log_message as _utils_log_message
from .algorithms import parse_algorithms_to_internal_format, validate_algorithm_dimensions
from .elasticsearch_sql import elasticsearch_sql
from .query_validator import QueryValidator


def log_message(message: str, level: str = "info", component: str = "mcp_tools", method: str = "entry", **kwargs):
    return _utils_log_message(message, level, component, method, **kwargs)


def create_da_config(
    name: str,
    description: str,
    training_query: str,
    detection_query: str,
    training_from: str,
    training_to: str,
    training_is_active: bool,
    detection_is_active: bool,
    training_window: int,
    detection_window: int,
    detection_frequency: str,
    detection_start: str,
    algorithms: List[AlgorithmConfig]
) -> str:
    request_id = str(uuid.uuid4())[:8]
    start_time = time.time()

    log_message("Tool execution started", "info", "create_da_config", "entry",
                request_id=request_id, extra_data={
                    "config_name": name,
                    "algorithm_count": len(algorithms) if algorithms else 0
                })

    # Validate input using Pydantic models
    try:
        from pydantic import ValidationError
        from models import KBConfig, TrainingConfig, DetectionConfig, SchedulingConfig, AlgorithmConfigItem

        # Convert algorithms to AlgorithmConfigItem format
        algorithm_items = []
        for alg in algorithms or []:
            try:
                if isinstance(alg, AlgorithmConfigItem):
                    algorithm_items.append(AlgorithmConfigItem.model_validate(alg.model_dump()))
                elif isinstance(alg, dict):
                    algorithm_items.append(AlgorithmConfigItem.model_validate(alg))
                else:
                    raise ToolError(
                        f"Unsupported algorithm format: {type(alg)}. Expected AlgorithmConfigItem or dict with 'alg_name' and 'alg_parameters'."
                    )
            except ValidationError as exc:
                raise ToolError(f"Algorithm validation error: {exc}") from exc

        # Create and validate KBConfig instance
        config = KBConfig(
            name=name,
            description=description,
            change_flag=0,
            scheduling=SchedulingConfig(
                training_config=TrainingConfig(
                    training_query=training_query,
                    **{"from": training_from},
                    to=training_to,
                    training_window=training_window,
                    is_active=training_is_active
                ),
                detection_config=DetectionConfig(
                    detection_query=detection_query,
                    **{"from": detection_start},
                    frequency=detection_frequency,
                    detection_window=detection_window,
                    is_active=detection_is_active
                )
            ),
            algorithms=algorithm_items
        )

        log_message("Pydantic validation successful", "info", "create_da_config", "validation",
                    request_id=request_id)

    except Exception as e:
        log_message(f"Pydantic validation failed: {str(e)}", "error", "create_da_config", "validation",
                    request_id=request_id)
        raise ToolError(f"Input validation failed: {str(e)}")

    # Validate time range logic
    from datetime import datetime
    try:
        training_from_dt = datetime.fromisoformat(training_from.replace('Z', '+00:00'))
        training_to_dt = datetime.fromisoformat(training_to.replace('Z', '+00:00'))
        if training_to_dt <= training_from_dt:
            raise ToolError("training_to must be after training_from")
    except ValueError as e:
        raise ToolError(f"Invalid timestamp format: {str(e)}")

    # Parse algorithms to internal format (using validated config)
    internal_algorithms = parse_algorithms_to_internal_format(config.algorithms)

    algorithm_errors = validate_algorithms(internal_algorithms)
    if algorithm_errors:
        error_msg = "Algorithm validation failed:\n" + "\n".join(f"- {err}" for err in algorithm_errors)
        log_message(f"Algorithm validation failed: {len(algorithm_errors)} errors", "error",
                    "create_da_config", "validation", request_id=request_id)
        raise ToolError(error_msg)

    # Cross-validate algorithms against SQL queries
    if config.scheduling.training_config.training_query:
        QueryValidator.validate(config.scheduling.training_config.training_query, "training")
        validation_result = elasticsearch_sql(config.scheduling.training_config.training_query + " LIMIT 0")
        if "ERROR" in validation_result:
            raise ToolError(f"Training SQL query validation failed: {validation_result}")
        else:
            try:
                result_data = json.loads(validation_result)
                available_fields = [col['name'] for col in result_data.get('columns', [])]

                validate_algorithm_dimensions(config.algorithms, available_fields, "training")
            except json.JSONDecodeError:
                raise ToolError("Could not parse training SQL validation response")

    if config.scheduling.detection_config.detection_query:
        QueryValidator.validate(config.scheduling.detection_config.detection_query, "detection")
        validation_result = elasticsearch_sql(config.scheduling.detection_config.detection_query + " LIMIT 0")
        if "ERROR" in validation_result:
            raise ToolError(f"Detection SQL query validation failed: {validation_result}")
        else:
            try:
                result_data = json.loads(validation_result)
                available_fields = [col['name'] for col in result_data.get('columns', [])]

                validate_algorithm_dimensions(config.algorithms, available_fields, "detection")
            except json.JSONDecodeError:
                raise ToolError("Could not parse detection SQL validation response")

    # Convert validated config to dict for storage
    config_to_store = config.model_dump(by_alias=True)

    log_message(f"Configuration validation successful for: {config.name}", "info",
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
