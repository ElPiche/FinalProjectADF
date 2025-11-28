import asyncio
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from mcp.server.fastmcp import Context
from mcp.server.fastmcp.exceptions import ToolError
from pydantic import ValidationError

from models import AlgorithmConfig, AnomalyConfig, DetectionConfig, KBConfig, QueryMode, SchedulingConfig, TrainingConfig
from db import connect_mongodb
from validation import validate_algorithms, validate_cron_expression, validate_window_size
from utils import log_message as _utils_log_message
from .algorithms import parse_algorithms_to_internal_format, validate_algorithm_dimensions
from .config import ENABLE_PROGRESS_REPORTING, MAX_TOOL_EXECUTION_TIME
from .context_helpers import ContextReporter
from .elasticsearch_sql import elasticsearch_sql
from .query_validator import QueryValidator, materialize_query_time_range


def log_message(message: str, level: str = "info", component: str = "mcp_tools", method: str = "entry", **kwargs):
    return _utils_log_message(message, level, component, method, **kwargs)


MIN_DETECTION_FREQUENCY_SECONDS = {
    "raw": 60,
    "aggregated": 10,
}


def _enforce_detection_frequency_floor(query_mode_type: str, cron_expression: str) -> None:
    """Ensure CRON schedules obey minimum per-mode frequencies."""

    from croniter import croniter

    reference = datetime.now(timezone.utc)
    try:
        iterator = croniter(cron_expression, reference)
        next_fire = iterator.get_next(datetime)
    except Exception as exc:  # pragma: no cover - croniter raises descriptive errors
        raise ToolError(f"Unable to evaluate detection_frequency '{cron_expression}': {exc}") from exc

    interval_seconds = (next_fire - reference).total_seconds()
    minimum = MIN_DETECTION_FREQUENCY_SECONDS.get((query_mode_type or "raw").lower(), 60)

    if interval_seconds < minimum:
        raise ToolError(
            f"Detection frequency '{cron_expression}' executes every {interval_seconds:.0f} seconds, "
            f"which is faster than the minimum {minimum} seconds allowed for query_mode '{query_mode_type}'."
        )


async def create_da_config(
    name: str,
    description: str,
    elasticsearch_sql_query: str,
    query_mode: QueryMode,
    training_from: str,
    training_to: str,
    training_is_active: bool,
    detection_is_active: bool,
    detection_frequency: str,
    detection_window: int,
    detection_start: str,
    algorithm: AlgorithmConfig,
    bucket_profile_id: Optional[str] = None,
    source_index: str = "",
    anomaly_config: Optional[AnomalyConfig] = None,
    ctx: Context | None = None,
) -> str:
    request_id = str(uuid.uuid4())[:8]
    total_start = time.time()
    warnings: list[str] = []
    client = None
    reporter = ContextReporter(ctx, total_steps=5, enabled=ENABLE_PROGRESS_REPORTING)

    await reporter.info("Starting create_da_config")
    log_message(
        "=== Starting create_da_config ===",
        "info",
        "create_da_config",
        "entry",
        request_id=request_id,
        extra_data={"config_name": name, "algorithm_name": getattr(algorithm, "name", None)},
    )

    try:
        async with asyncio.timeout(MAX_TOOL_EXECUTION_TIME):
            # Step 1: Window validation
            step_start = time.time()
            await reporter.step(1, "Step 1/5: Validating detection window")
            log_message("Step 1/5: Validating detection window", "info", "create_da_config", "step", request_id=request_id)
            try:
                detection_window_result = validate_window_size(detection_window, "detection")
            except ValueError as exc:
                raise ToolError(f"Invalid window size: {exc}") from exc

            if detection_window_result.get("warning"):
                warning_text = f"⚠️  Warning: {detection_window_result['warning']}"
                warnings.append(warning_text)
                await reporter.warning(warning_text)
                log_message(warning_text, "warning", "create_da_config", "step", request_id=request_id)

            log_message(
                f"✓ Step 1 completed in {time.time() - step_start:.2f}s",
                "info",
                "create_da_config",
                "step",
                request_id=request_id,
            )

            # Step 2: Schema validation (Pydantic + CRON + timestamps)
            step_start = time.time()
            await reporter.step(2, "Step 2/5: Validating configuration payload")
            log_message("Step 2/5: Validating configuration payload", "info", "create_da_config", "step", request_id=request_id)

            if not isinstance(elasticsearch_sql_query, str) or not elasticsearch_sql_query.strip():
                raise ToolError("elasticsearch_sql_query must be a non-empty string")

            cleaned_query = elasticsearch_sql_query.strip()

            try:
                validate_cron_expression(detection_frequency)
            except ValueError as exc:
                raise ToolError(str(exc)) from exc

            normalized_bucket_profile_id = bucket_profile_id.strip() if bucket_profile_id else None
            normalized_source_index = source_index.strip() if source_index else None
            
            if not normalized_source_index:
                raise ToolError("source_index is required - specify the Elasticsearch index being monitored (e.g., 'app-logs')")

            # Validate and normalize anomaly_config if provided
            validated_anomaly_config = None
            if anomaly_config is not None:
                try:
                    validated_anomaly_config = (
                        anomaly_config
                        if isinstance(anomaly_config, AnomalyConfig)
                        else AnomalyConfig.model_validate(anomaly_config)
                    )
                except ValidationError as exc:
                    raise ToolError(f"Invalid anomaly_config payload: {exc}") from exc

            try:
                validated_query_mode = (
                    query_mode
                    if isinstance(query_mode, QueryMode)
                    else QueryMode.model_validate(query_mode)
                )
            except ValidationError as exc:
                raise ToolError(f"Invalid query_mode payload: {exc}") from exc

            try:
                validated_algorithm = (
                    algorithm
                    if isinstance(algorithm, AlgorithmConfig)
                    else AlgorithmConfig.model_validate(algorithm)
                )
            except ValidationError as exc:
                raise ToolError(f"Algorithm validation error: {exc}") from exc

            _enforce_detection_frequency_floor(validated_query_mode.type, detection_frequency)

            training_kwargs = {"from": training_from}
            detection_kwargs = {"from": detection_start} if detection_start else {}

            config = KBConfig(
                name=name,
                description=description,
                change_flag=0,
                elasticsearch_sql_query=cleaned_query,
                source_index=normalized_source_index,
                query_mode=validated_query_mode,
                bucket_profile_id=normalized_bucket_profile_id,
                anomaly_config=validated_anomaly_config,
                algorithm=validated_algorithm,
                scheduling=SchedulingConfig(
                    training_config=TrainingConfig(
                        **training_kwargs,
                        to=training_to,
                        is_active=training_is_active,
                    ),
                    detection_config=DetectionConfig(
                        **detection_kwargs,
                        frequency=detection_frequency,
                        detection_window=detection_window,
                        is_active=detection_is_active,
                    ),
                ),
            )

            try:
                training_from_dt = datetime.fromisoformat(training_from.replace("Z", "+00:00"))
                training_to_dt = datetime.fromisoformat(training_to.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ToolError(f"Invalid timestamp format: {exc}") from exc

            if training_to_dt <= training_from_dt:
                raise ToolError("training_to must be after training_from")

            log_message(
                f"✓ Step 2 completed in {time.time() - step_start:.2f}s",
                "info",
                "create_da_config",
                "step",
                request_id=request_id,
            )

            # Step 3: Algorithm + SQL validation
            step_start = time.time()
            await reporter.step(3, "Step 3/5: Validating algorithms and SQL query")
            log_message("Step 3/5: Validating algorithms and SQL query", "info", "create_da_config", "step", request_id=request_id)

            internal_algorithms = parse_algorithms_to_internal_format(config.algorithm)
            algorithm_payload = internal_algorithms[0] if len(internal_algorithms) == 1 else internal_algorithms
            algorithm_errors = validate_algorithms(algorithm_payload)
            if algorithm_errors:
                error_msg = "Algorithm validation failed:\n" + "\n".join(f"- {err}" for err in algorithm_errors)
                raise ToolError(error_msg)

            async def _validate_unified_query() -> None:
                materialized_query = materialize_query_time_range(
                    config.elasticsearch_sql_query,
                    training_from,
                    training_to,
                    "elasticsearch_sql_query",
                )
                await asyncio.to_thread(
                    QueryValidator.validate,
                    materialized_query,
                    "unified",
                    query_mode=config.query_mode.type,
                    timestamp_field=config.query_mode.timestamp_field,
                )
                preview = await elasticsearch_sql(f"{materialized_query} LIMIT 0", ctx=ctx)
                available_fields = [col.get("name") for col in preview.get("columns", []) if col.get("name")]
                if config.query_mode.timestamp_field not in available_fields:
                    raise ToolError(
                        f"timestamp_field '{config.query_mode.timestamp_field}' was not returned by the query. "
                        f"Available fields: {available_fields}"
                    )
                validate_algorithm_dimensions(config.algorithm, available_fields, "unified")

            await _validate_unified_query()

            log_message(
                f"✓ Step 3 completed in {time.time() - step_start:.2f}s",
                "info",
                "create_da_config",
                "step",
                request_id=request_id,
            )

            # Prepare config dict for persistence
            config_to_store = config.model_dump(by_alias=True, exclude_none=True)
            sys.stderr.write("\n[KB-MCP] Configuration Preview:\n")
            sys.stderr.write(json.dumps(config_to_store, indent=2) + "\n\n")
            sys.stderr.flush()

            # Step 4: Duplicate name detection
            step_start = time.time()
            await reporter.step(4, "Step 4/5: Checking configuration name uniqueness")
            log_message("Step 4/5: Checking configuration name uniqueness", "info", "create_da_config", "step", request_id=request_id)
            client = await asyncio.to_thread(connect_mongodb)
            if client is None:
                raise ToolError("Failed to connect to MongoDB - configuration not saved")

            import db

            db_instance = client[db.db_kb_name]
            collection = db_instance[db.db_kb_collection_name]
            # Bucket profiles are stored in anomaly_detection database (via get_db())
            anomaly_detection_db = client["anomaly_detection"]
            bucket_profiles_collection = anomaly_detection_db.get_collection("bucket_profiles")
            enforce_unique = os.getenv("ENFORCE_UNIQUE_CONFIG_NAMES", "false").lower() == "true"
            existing = await asyncio.to_thread(collection.find_one, {"name": name})
            if existing:
                msg = f"Configuration with name '{name}' already exists (ID: {existing.get('_id')})."
                if enforce_unique:
                    raise ToolError(
                        f"Duplicate configuration name: {msg} Strict mode is enabled; choose a unique name or disable ENFORCE_UNIQUE_CONFIG_NAMES."
                    )
                warning_text = f"⚠️  Warning: {msg} Consider using a unique name to avoid confusion."
                warnings.append(warning_text)
                await reporter.warning(warning_text)
                log_message(warning_text, "warning", "create_da_config", "step", request_id=request_id)

            if config.bucket_profile_id:
                bucket_profile = await asyncio.to_thread(
                    bucket_profiles_collection.find_one,
                    {"_id": config.bucket_profile_id},
                    {"_id": 1},
                )
                if bucket_profile is None:
                    raise ToolError(
                        f"bucket_profile_id '{config.bucket_profile_id}' does not exist in bucket_profiles collection"
                    )

            log_message(
                f"✓ Step 4 completed in {time.time() - step_start:.2f}s",
                "info",
                "create_da_config",
                "step",
                request_id=request_id,
            )

            # Step 5: Persist configuration (fire-and-forget via MongoDB insert)
            step_start = time.time()
            await reporter.step(5, "Step 5/5: Persisting configuration")
            log_message("Step 5/5: Persisting configuration", "info", "create_da_config", "step", request_id=request_id)
            result = await asyncio.to_thread(collection.insert_one, config_to_store)
            document_id = str(result.inserted_id)
            log_message(
                f"✓ Step 5 completed in {time.time() - step_start:.2f}s",
                "info",
                "create_da_config",
                "step",
                request_id=request_id,
                extra_data={"document_id": document_id},
            )

            total_elapsed = time.time() - total_start
            success_msg = (
                "SUCCESS: Configuration saved to MongoDB!\n\n"
                f"Document ID: {document_id}\n\nConfiguration saved successfully."
            )
            if warnings:
                success_msg += "\n" + "\n".join(warnings)

            await reporter.complete("create_da_config completed")
            log_message(
                "Configuration creation completed successfully",
                "info",
                "create_da_config",
                "completion",
                request_id=request_id,
                duration_ms=int(total_elapsed * 1000),
                extra_data={"document_id": document_id},
            )
            return success_msg

    except asyncio.TimeoutError as exc:
        await reporter.error(
            f"❌ create_da_config timed out after {MAX_TOOL_EXECUTION_TIME} seconds. Check MongoDB/Elasticsearch connectivity."
        )
        total_elapsed = time.time() - total_start
        log_message(
            "create_da_config timed out",
            "error",
            "create_da_config",
            "failure",
            request_id=request_id,
            duration_ms=int(total_elapsed * 1000),
        )
        raise ToolError(
            f"create_da_config exceeded the timeout limit ({MAX_TOOL_EXECUTION_TIME}s)."
        ) from exc
    except ToolError:
        total_elapsed = time.time() - total_start
        log_message(
            "create_da_config failed (ToolError)",
            "error",
            "create_da_config",
            "failure",
            request_id=request_id,
            duration_ms=int(total_elapsed * 1000),
        )
        raise
    except Exception as exc:
        total_elapsed = time.time() - total_start
        log_message(
            f"Unexpected error: {exc}",
            "error",
            "create_da_config",
            "failure",
            request_id=request_id,
            duration_ms=int(total_elapsed * 1000),
            extra_data={"error_type": type(exc).__name__},
        )
        raise ToolError(f"Failed to create configuration: {exc}") from exc
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass
