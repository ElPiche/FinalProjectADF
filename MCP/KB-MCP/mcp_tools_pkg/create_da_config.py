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

    # Validate input using Pydantic models
    try:
        from models import KBConfig, TrainingConfig, DetectionConfig, SchedulingConfig, AlgorithmConfigItem, AlgorithmParameter

        # Convert algorithms to AlgorithmConfigItem format
        algorithm_items = []
        for alg in algorithms or []:
            if hasattr(alg, 'alg_name') and hasattr(alg, 'alg_parameters'):
                # Already in AlgorithmConfigItem format
                algorithm_items.append(alg)
            elif hasattr(alg, 'algorithm') and hasattr(alg, 'dimensions'):
                # ZScoreConfig format: {"algorithm": "zscore", "dimensions": ["dim1", "dim2"]}
                alg_name = alg.algorithm
                dimensions = alg.dimensions
                
                alg_params = [AlgorithmParameter(dimension=dim) for dim in dimensions]
                algorithm_items.append(AlgorithmConfigItem(
                    alg_name=alg_name,
                    alg_parameters=alg_params
                ))
            elif isinstance(alg, dict):
                # Dictionary format: {"algorithm": "zscore", "dimensions": ["dim1", "dim2"]}
                alg_name = alg.get('algorithm') or alg.get('alg_name', 'zscore')
                dimensions = alg.get('dimensions', [])
                
                alg_params = [AlgorithmParameter(dimension=dim) for dim in dimensions]
                algorithm_items.append(AlgorithmConfigItem(
                    alg_name=alg_name,
                    alg_parameters=alg_params
                ))
            else:
                # Try to convert from other formats
                alg_params = []
                if hasattr(alg, 'alg_parameters'):
                    for param in alg.alg_parameters:
                        if hasattr(param, 'dimension'):
                            alg_params.append(AlgorithmParameter(dimension=param.dimension))
                algorithm_items.append(AlgorithmConfigItem(
                    alg_name=getattr(alg, 'alg_name', getattr(alg, 'algorithm', 'zscore')),
                    alg_parameters=alg_params
                ))

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
                    training_window=3600,
                    is_active=True
                ),
                detection_config=DetectionConfig(
                    detection_query=detection_query,
                    **{"from": detection_start},
                    frequency=detection_frequency,
                    detection_window=3600,
                    is_active=False
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

    # Parse algorithms to internal format (using validated config)
    internal_algorithms = parse_algorithms_to_internal_format(config.algorithms)

    algorithm_errors = validate_algorithms(internal_algorithms)
    if algorithm_errors:
        error_msg = "Algorithm validation failed:\n" + "\n".join(f"- {err}" for err in algorithm_errors)
        log_message(f"Algorithm validation failed: {len(algorithm_errors)} errors", "error",
                    "create_da_config", "validation", request_id=request_id)
        raise ToolError(error_msg)

    # Cross-validate algorithms against SQL queries
    from .elasticsearch_sql import elasticsearch_sql

    if config.scheduling.training_config.training_query:
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
