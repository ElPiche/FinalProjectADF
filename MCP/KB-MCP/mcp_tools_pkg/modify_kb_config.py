import asyncio
import time
import uuid
from datetime import datetime
from typing import Optional

from bson import ObjectId
from mcp.server.fastmcp import Context
from mcp.server.fastmcp.exceptions import ToolError
from pydantic import ValidationError

import db
from db import connect_mongodb
from models import (
    AlgorithmConfig,
    AnomalyConfig,
    DetectionConfig,
    KBConfig,
    QueryMode,
    SchedulingConfig,
    TrainingConfig,
)
from utils import log_message as _utils_log_message
from validation import validate_algorithms, validate_cron_expression, validate_window_size
from .algorithms import validate_algorithm_dimensions
from .create_da_config import (
    _enforce_detection_frequency_floor,
    _validate_query_via_extractor,
    _validate_query_mode_via_extractor,
    _validate_timestamp_field_via_extractor,
)
from .config import ENABLE_PROGRESS_REPORTING, MAX_TOOL_EXECUTION_TIME
from .context_helpers import ContextReporter
from .elasticsearch_sql import elasticsearch_sql
from .query_validator import materialize_query_time_range


def log_message(message: str, level: str = "info", component: str = "mcp_tools", method: str = "entry", **kwargs):
    return _utils_log_message(message, level, component, method, **kwargs)


async def modify_kb_config(
    kb_id: str,
    description: Optional[str] = None,
    elasticsearch_sql_query: Optional[str] = None,
    query_mode: Optional[QueryMode] = None,
    training_from: Optional[str] = None,
    training_to: Optional[str] = None,
    training_is_active: Optional[bool] = None,
    detection_is_active: Optional[bool] = None,
    detection_frequency: Optional[str] = None,
    detection_window: Optional[int] = None,
    detection_start: Optional[str] = None,
    algorithm: Optional[AlgorithmConfig] = None,
    bucket_profile_id: Optional[str] = None,
    source_index: Optional[str] = None,
    anomaly_config: Optional[AnomalyConfig] = None,
    ctx: Context | None = None,
) -> str:
    request_id = str(uuid.uuid4())[:8]
    start_time = time.time()
    warnings: list[str] = []
    reporter = ContextReporter(ctx, total_steps=4, enabled=ENABLE_PROGRESS_REPORTING)
    client = None

    await reporter.info("Starting modify_kb_config")

    log_message(
        "Tool execution started",
        "info",
        "modify_kb_config",
        "entry",
        request_id=request_id,
        extra_data={"kb_id": kb_id},
    )

    client = await asyncio.to_thread(connect_mongodb)
    if client is None:
        raise ToolError("Failed to connect to MongoDB")

    try:
        async with asyncio.timeout(MAX_TOOL_EXECUTION_TIME):
            db_instance = client[db.db_kb_name]
            collection = db_instance[db.db_kb_collection_name]
            # Bucket profiles are stored in knowledge_base database
            bucket_profiles_collection = db_instance.get_collection("bucket_profiles")

            step_start = time.time()
            await reporter.step(1, "Step 1/4: Loading configuration")
            log_message(
                "Step 1/4: Loading configuration",
                "info",
                "modify_kb_config",
                "step",
                request_id=request_id,
                extra_data={"kb_id": kb_id},
            )

            try:
                object_id = ObjectId(kb_id)
            except Exception as exc:
                raise ToolError(f"Invalid KB ID format: '{kb_id}' - {exc}")

            config_doc = await asyncio.to_thread(collection.find_one, {"_id": object_id})
            if not config_doc:
                raise ToolError(f"Configuration with KB ID '{kb_id}' not found")

            try:
                existing_config = KBConfig.model_validate({k: v for k, v in config_doc.items() if k != "_id"})
            except ValidationError as exc:
                raise ToolError(f"Stored configuration failed validation and cannot be updated: {exc}")

            log_message(
                f"✓ Step 1 completed in {time.time() - step_start:.2f}s",
                "info",
                "modify_kb_config",
                "step",
                request_id=request_id,
                extra_data={"kb_id": kb_id},
            )

            step_start = time.time()
            await reporter.step(2, "Step 2/4: Applying requested updates")
            log_message(
                "Step 2/4: Applying requested updates",
                "info",
                "modify_kb_config",
                "step",
                request_id=request_id,
                extra_data={"kb_id": kb_id},
            )

            updates_applied = False
            query_updated = False
            algorithm_updated = False
            query_mode_updated = False
            time_range_updated = False

            updated_description = existing_config.description
            if description is not None:
                if not isinstance(description, str) or not description.strip():
                    raise ToolError("description must be a non-empty string")
                cleaned_description = description.strip()
                if cleaned_description != existing_config.description:
                    updated_description = cleaned_description
                    updates_applied = True

            updated_query = existing_config.elasticsearch_sql_query
            if elasticsearch_sql_query is not None:
                if not isinstance(elasticsearch_sql_query, str) or not elasticsearch_sql_query.strip():
                    raise ToolError("elasticsearch_sql_query must be a non-empty string")
                cleaned_query = elasticsearch_sql_query.strip()
                if cleaned_query != existing_config.elasticsearch_sql_query:
                    updated_query = cleaned_query
                    updates_applied = True
                    query_updated = True

            resulting_query_mode = existing_config.query_mode
            if query_mode is not None:
                try:
                    validated_query_mode = (
                        query_mode if isinstance(query_mode, QueryMode) else QueryMode.model_validate(query_mode)
                    )
                except ValidationError as exc:
                    raise ToolError(f"Invalid query_mode payload: {exc}") from exc
                if validated_query_mode.model_dump() != existing_config.query_mode.model_dump():
                    resulting_query_mode = validated_query_mode
                    updates_applied = True
                    query_mode_updated = True

            algorithm_to_use = existing_config.algorithm
            if algorithm is not None:
                try:
                    validated_algorithm = (
                        algorithm if isinstance(algorithm, AlgorithmConfig) else AlgorithmConfig.model_validate(algorithm)
                    )
                except ValidationError as exc:
                    raise ToolError(f"Algorithm validation error: {exc}") from exc
                if validated_algorithm.model_dump(by_alias=True) != existing_config.algorithm.model_dump(by_alias=True):
                    algorithm_to_use = validated_algorithm
                    updates_applied = True
                    algorithm_updated = True

            updated_bucket_profile_id = existing_config.bucket_profile_id
            if bucket_profile_id is not None:
                if not isinstance(bucket_profile_id, str):
                    raise ToolError("bucket_profile_id must be a string")
                cleaned_bucket_profile_id = bucket_profile_id.strip()
                if cleaned_bucket_profile_id == "":
                    cleaned_bucket_profile_id = None
                if cleaned_bucket_profile_id != existing_config.bucket_profile_id:
                    updated_bucket_profile_id = cleaned_bucket_profile_id
                    updates_applied = True

            updated_source_index = existing_config.source_index
            if source_index is not None:
                if not isinstance(source_index, str):
                    raise ToolError("source_index must be a string")
                cleaned_source_index = source_index.strip()
                if cleaned_source_index == "":
                    raise ToolError("source_index cannot be empty")
                if cleaned_source_index != existing_config.source_index:
                    updated_source_index = cleaned_source_index
                    updates_applied = True

            updated_anomaly_config = existing_config.anomaly_config
            if anomaly_config is not None:
                try:
                    validated_anomaly_config = (
                        anomaly_config
                        if isinstance(anomaly_config, AnomalyConfig)
                        else AnomalyConfig.model_validate(anomaly_config)
                    )
                except ValidationError as exc:
                    raise ToolError(f"Invalid anomaly_config payload: {exc}") from exc
                existing_dump = existing_config.anomaly_config.model_dump() if existing_config.anomaly_config else None
                if validated_anomaly_config.model_dump() != existing_dump:
                    updated_anomaly_config = validated_anomaly_config
                    updates_applied = True

            training_payload = existing_config.scheduling.training_config.model_dump(by_alias=True)
            if training_from is not None:
                if not isinstance(training_from, str) or not training_from.strip():
                    raise ToolError("training_from must be a non-empty ISO timestamp string")
                cleaned_training_from = training_from.strip()
                if cleaned_training_from != training_payload.get("from"):
                    training_payload["from"] = cleaned_training_from
                    updates_applied = True
                    time_range_updated = True

            if training_to is not None:
                if not isinstance(training_to, str) or not training_to.strip():
                    raise ToolError("training_to must be a non-empty ISO timestamp string")
                cleaned_training_to = training_to.strip()
                if cleaned_training_to != training_payload.get("to"):
                    training_payload["to"] = cleaned_training_to
                    updates_applied = True
                    time_range_updated = True

            if training_is_active is not None:
                if not isinstance(training_is_active, bool):
                    raise ToolError("training_is_active must be a boolean")
                if training_is_active != training_payload.get("is_active"):
                    training_payload["is_active"] = training_is_active
                    updates_applied = True

            detection_payload = existing_config.scheduling.detection_config.model_dump(by_alias=True)
            if detection_start is not None:
                if not isinstance(detection_start, str) or not detection_start.strip():
                    raise ToolError("detection_start must be a non-empty ISO timestamp string")
                cleaned_detection_start = detection_start.strip()
                if cleaned_detection_start != detection_payload.get("from"):
                    detection_payload["from"] = cleaned_detection_start
                    updates_applied = True

            if detection_frequency is not None:
                if not isinstance(detection_frequency, str) or not detection_frequency.strip():
                    raise ToolError("detection_frequency must be a non-empty CRON expression")
                cleaned_detection_frequency = detection_frequency.strip()
                try:
                    validate_cron_expression(cleaned_detection_frequency)
                except ValueError as exc:
                    raise ToolError(str(exc)) from exc
                _enforce_detection_frequency_floor(resulting_query_mode.type, cleaned_detection_frequency)
                if cleaned_detection_frequency != detection_payload.get("frequency"):
                    detection_payload["frequency"] = cleaned_detection_frequency
                    updates_applied = True

            if detection_window is not None:
                if not isinstance(detection_window, int):
                    raise ToolError("detection_window must be an integer")
                try:
                    detection_window_result = validate_window_size(detection_window, "detection")
                except ValueError as exc:
                    raise ToolError(f"Invalid window size: {exc}") from exc
                detection_payload["detection_window"] = detection_window
                updates_applied = True
                if detection_window_result.get("warning"):
                    warning_text = f"⚠️  Warning: {detection_window_result['warning']}"
                    warnings.append(warning_text)
                    await reporter.warning(warning_text)
                    log_message(warning_text, "warning", "modify_kb_config", "step", request_id=request_id)

            if detection_is_active is not None:
                if not isinstance(detection_is_active, bool):
                    raise ToolError("detection_is_active must be a boolean")
                if detection_is_active != detection_payload.get("is_active"):
                    detection_payload["is_active"] = detection_is_active
                    updates_applied = True

            if query_mode_updated and detection_payload.get("frequency"):
                _enforce_detection_frequency_floor(resulting_query_mode.type, detection_payload["frequency"])

            if not updates_applied:
                log_message(
                    "No valid updates provided",
                    "warning",
                    "modify_kb_config",
                    "validation",
                    request_id=request_id,
                    extra_data={"kb_id": kb_id},
                )
                raise ToolError("No valid updates provided")

            try:
                updated_training_config = TrainingConfig.model_validate(training_payload)
                updated_detection_config = DetectionConfig.model_validate(detection_payload)
                updated_scheduling_config = SchedulingConfig(
                    training_config=updated_training_config,
                    detection_config=updated_detection_config,
                )
            except ValidationError as exc:
                raise ToolError(f"Invalid scheduling configuration: {exc}") from exc

            new_config = KBConfig(
                name=existing_config.name,
                description=updated_description,
                change_flag=existing_config.change_flag + 1,
                elasticsearch_sql_query=updated_query,
                source_index=updated_source_index,
                query_mode=resulting_query_mode,
                bucket_profile_id=updated_bucket_profile_id,
                anomaly_config=updated_anomaly_config,
                algorithm=algorithm_to_use,
                scheduling=updated_scheduling_config,
            )

            if time_range_updated:
                try:
                    training_from_dt = datetime.fromisoformat(
                        new_config.scheduling.training_config.from_.replace("Z", "+00:00")
                    )
                    training_to_dt = datetime.fromisoformat(
                        new_config.scheduling.training_config.to.replace("Z", "+00:00")
                    )
                except ValueError as exc:
                    raise ToolError(f"Invalid timestamp format: {exc}") from exc
                if training_to_dt <= training_from_dt:
                    raise ToolError("training_to must be after training_from")

            if new_config.bucket_profile_id:
                bucket_profile = await asyncio.to_thread(
                    bucket_profiles_collection.find_one,
                    {"_id": new_config.bucket_profile_id},
                    {"_id": 1},
                )
                if bucket_profile is None:
                    raise ToolError(
                        f"bucket_profile_id '{new_config.bucket_profile_id}' does not exist in bucket_profiles collection"
                    )

            log_message(
                f"✓ Step 2 completed in {time.time() - step_start:.2f}s",
                "info",
                "modify_kb_config",
                "step",
                request_id=request_id,
                extra_data={"kb_id": kb_id},
            )

            step_start = time.time()
            await reporter.step(3, "Step 3/4: Validating updates via extractor")
            log_message(
                "Step 3/4: Validating updates via extractor (point-to-point)",
                "info",
                "modify_kb_config",
                "step",
                request_id=request_id,
                extra_data={"kb_id": kb_id},
            )

            algorithm_payload = new_config.algorithm.model_dump(by_alias=True)
            algorithm_errors = validate_algorithms(algorithm_payload)
            if algorithm_errors:
                error_msg = "Algorithm validation failed:\n" + "\n".join(f"- {err}" for err in algorithm_errors)
                raise ToolError(error_msg)

            # Point-to-point validation: only validate what changed
            # Each validation uses its own individual endpoint

            # If query_mode changed, validate it via /query-mode endpoint
            if query_mode_updated:
                log_message("Validating query_mode via extractor", "info", "modify_kb_config", "step", request_id=request_id)
                await asyncio.to_thread(
                    _validate_query_mode_via_extractor,
                    resulting_query_mode.type,
                )

            # If timestamp_field changed, validate via /timestamp-field endpoint
            timestamp_field_updated = query_mode_updated and (
                resulting_query_mode.timestamp_field != existing_config.query_mode.timestamp_field
            )
            if timestamp_field_updated:
                log_message("Validating timestamp_field via extractor", "info", "modify_kb_config", "step", request_id=request_id)
                await asyncio.to_thread(
                    _validate_timestamp_field_via_extractor,
                    resulting_query_mode.timestamp_field,
                )

            # If query, query_mode, or time_range changed, validate query via /query endpoint
            needs_query_validation = query_updated or query_mode_updated or time_range_updated
            if needs_query_validation:
                log_message("Validating query via extractor", "info", "modify_kb_config", "step", request_id=request_id)
                materialized_query = materialize_query_time_range(
                    new_config.elasticsearch_sql_query,
                    new_config.scheduling.training_config.from_,
                    new_config.scheduling.training_config.to,
                    "elasticsearch_sql_query",
                )
                await asyncio.to_thread(
                    _validate_query_via_extractor,
                    materialized_query,
                    new_config.query_mode.type,
                    new_config.query_mode.timestamp_field,
                )

            # If query, algorithm, or query_mode changed, revalidate dimensions
            needs_dimension_validation = query_updated or algorithm_updated or query_mode_updated or time_range_updated
            if needs_dimension_validation:
                log_message("Validating algorithm dimensions", "info", "modify_kb_config", "step", request_id=request_id)
                materialized_query = materialize_query_time_range(
                    new_config.elasticsearch_sql_query,
                    new_config.scheduling.training_config.from_,
                    new_config.scheduling.training_config.to,
                    "elasticsearch_sql_query",
                )
                preview = await elasticsearch_sql(f"{materialized_query} LIMIT 0", ctx=ctx)
                available_fields = [col.get("name") for col in preview.get("columns", []) if col.get("name")]
                if new_config.query_mode.timestamp_field not in available_fields:
                    raise ToolError(
                        f"timestamp_field '{new_config.query_mode.timestamp_field}' was not returned by the query. "
                        f"Available fields: {available_fields}"
                    )
                validate_algorithm_dimensions(new_config.algorithm, available_fields, "unified")

            log_message(
                f"✓ Step 3 completed in {time.time() - step_start:.2f}s",
                "info",
                "modify_kb_config",
                "step",
                request_id=request_id,
                extra_data={"kb_id": kb_id},
            )

            payload = new_config.model_dump(by_alias=True, exclude_none=True)

            step_start = time.time()
            await reporter.step(4, "Step 4/4: Persisting configuration")
            log_message(
                "Step 4/4: Persisting configuration",
                "info",
                "modify_kb_config",
                "step",
                request_id=request_id,
                extra_data={"kb_id": kb_id},
            )

            result = await asyncio.to_thread(
                collection.update_one,
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
                    extra_data={"kb_id": kb_id},
                )
                raise ToolError("No changes were made to the configuration")

            log_message(
                f"✓ Step 4 completed in {time.time() - step_start:.2f}s",
                "info",
                "modify_kb_config",
                "step",
                request_id=request_id,
                extra_data={"kb_id": kb_id},
            )

            duration_ms = (time.time() - start_time) * 1000
            log_message(
                f"Configuration '{kb_id}' updated successfully",
                "info",
                "modify_kb_config",
                "completion",
                request_id=request_id,
                duration_ms=duration_ms,
                extra_data={"kb_id": kb_id},
            )
            success_msg = f"SUCCESS: Configuration '{kb_id}' updated successfully."
            if warnings:
                success_msg += "\n" + "\n".join(warnings)

            await reporter.complete("modify_kb_config completed")
            return success_msg

    except asyncio.TimeoutError as exc:
        await reporter.error(f"❌ modify_kb_config timed out after {MAX_TOOL_EXECUTION_TIME} seconds.")
        duration_ms = (time.time() - start_time) * 1000
        log_message(
            "modify_kb_config timed out",
            "error",
            "modify_kb_config",
            "failure",
            request_id=request_id,
            duration_ms=duration_ms,
            extra_data={"kb_id": kb_id},
        )
        raise ToolError(f"modify_kb_config exceeded the timeout limit ({MAX_TOOL_EXECUTION_TIME}s).") from exc
    except ToolError:
        duration_ms = (time.time() - start_time) * 1000
        await reporter.error("❌ modify_kb_config failed")
        log_message(
            "modify_kb_config failed (ToolError)",
            "error",
            "modify_kb_config",
            "failure",
            request_id=request_id,
            duration_ms=duration_ms,
            extra_data={"kb_id": kb_id},
        )
        raise
    except Exception as exc:
        await reporter.error(f"❌ modify_kb_config hit an unexpected error: {exc}")
        duration_ms = (time.time() - start_time) * 1000
        log_message(
            f"Unexpected error modifying configuration {kb_id}: {exc}",
            "error",
            "modify_kb_config",
            "error",
            request_id=request_id,
            duration_ms=duration_ms,
            extra_data={"kb_id": kb_id, "error_type": type(exc).__name__},
        )
        raise ToolError(f"Failed to modify configuration: {exc}") from exc
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass
