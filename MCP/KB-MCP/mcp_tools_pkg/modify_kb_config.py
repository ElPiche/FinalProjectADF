import asyncio
import time
import uuid
from datetime import datetime
from typing import List

from bson import ObjectId
from mcp.server.fastmcp import Context
from mcp.server.fastmcp.exceptions import ToolError
from pydantic import ValidationError

import db
from db import connect_mongodb
from models import (
    AlgorithmConfig,
    AlgorithmConfigItem,
    DetectionConfig,
    KBConfig,
    SchedulingConfig,
    TrainingConfig,
)
from utils import log_message as _utils_log_message
from validation import validate_algorithms, validate_cron_expression, validate_window_size
from .algorithms import parse_algorithms_to_internal_format, validate_algorithm_dimensions
from .config import ENABLE_PROGRESS_REPORTING, MAX_TOOL_EXECUTION_TIME
from .context_helpers import ContextReporter
from .elasticsearch_sql import elasticsearch_sql
from .query_validator import QueryValidator


def log_message(message: str, level: str = "info", component: str = "mcp_tools", method: str = "entry", **kwargs):
    return _utils_log_message(message, level, component, method, **kwargs)


async def modify_kb_config(
    config_id: str,
    description: str = None,
    training_query: str = None,
    detection_query: str = None,
    training_from: str = None,
    training_to: str = None,
    training_is_active: bool = None,
    detection_is_active: bool = None,
    training_window: int = None,
    detection_window: int = None,
    detection_frequency: str = None,
    detection_start: str = None,
    algorithms: List[AlgorithmConfig] = None,
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
        extra_data={"config_id": config_id},
    )

    client = await asyncio.to_thread(connect_mongodb)
    if client is None:
        raise ToolError("Failed to connect to MongoDB")

    try:
        async with asyncio.timeout(MAX_TOOL_EXECUTION_TIME):
            db_instance = client[db.db_kb_name]
            collection = db_instance[db.db_kb_collection_name]

            step_start = time.time()
            await reporter.step(1, "Step 1/4: Loading configuration")
            log_message(
                "Step 1/4: Loading configuration",
                "info",
                "modify_kb_config",
                "step",
                request_id=request_id,
                extra_data={"config_id": config_id},
            )

            try:
                object_id = ObjectId(config_id)
            except Exception as exc:
                raise ToolError(f"Invalid configuration ID format: '{config_id}' - {exc}")

            config_doc = await asyncio.to_thread(collection.find_one, {"_id": object_id})
            if not config_doc:
                raise ToolError(f"Configuration with ID '{config_id}' not found")

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
                extra_data={"config_id": config_id},
            )

            step_start = time.time()
            await reporter.step(2, "Step 2/4: Applying requested updates")
            log_message(
                "Step 2/4: Applying requested updates",
                "info",
                "modify_kb_config",
                "step",
                request_id=request_id,
                extra_data={"config_id": config_id},
            )

            updates_applied = False
            algorithms_updated = False
            training_query_updated = False
            detection_query_updated = False

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

            training_config_updates: dict[str, object] = {}
            if training_query is not None:
                if not isinstance(training_query, str) or not training_query.strip():
                    raise ToolError("training_query must be a non-empty string")
                cleaned_training_query = training_query.strip()
                if cleaned_training_query != existing_config.scheduling.training_config.training_query:
                    training_config_updates["training_query"] = cleaned_training_query
                    updates_applied = True
                    training_query_updated = True

            if training_window is not None:
                if not isinstance(training_window, int):
                    raise ToolError("training_window must be an integer")
                try:
                    validation_result = validate_window_size(training_window, "training")
                except ValueError as exc:
                    raise ToolError(f"Invalid window size: {exc}") from exc
                training_config_updates["training_window"] = training_window
                updates_applied = True
                if validation_result.get("warning"):
                    warning_text = f"⚠️  Warning: {validation_result['warning']}"
                    warnings.append(warning_text)
                    await reporter.warning(warning_text)
                    log_message(warning_text, "warning", "modify_kb_config", "step", request_id=request_id)

            if training_from is not None:
                if not isinstance(training_from, str) or not training_from.strip():
                    raise ToolError("training_from must be a non-empty ISO timestamp string")
                if training_from != existing_config.scheduling.training_config.from_:
                    training_config_updates["from"] = training_from
                    updates_applied = True

            if training_to is not None:
                if not isinstance(training_to, str) or not training_to.strip():
                    raise ToolError("training_to must be a non-empty ISO timestamp string")
                if training_to != existing_config.scheduling.training_config.to:
                    training_config_updates["to"] = training_to
                    updates_applied = True

            if training_is_active is not None:
                if not isinstance(training_is_active, bool):
                    raise ToolError("training_is_active must be a boolean")
                if training_is_active != existing_config.scheduling.training_config.is_active:
                    training_config_updates["is_active"] = training_is_active
                    updates_applied = True

            detection_config_updates: dict[str, object] = {}
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
                    detection_config_updates["from"] = detection_start
                    updates_applied = True

            if detection_frequency is not None:
                if not isinstance(detection_frequency, str) or not detection_frequency.strip():
                    raise ToolError("detection_frequency must be a non-empty CRON expression")
                cleaned_detection_frequency = detection_frequency.strip()
                try:
                    validate_cron_expression(cleaned_detection_frequency)
                except ValueError as exc:
                    raise ToolError(str(exc)) from exc
                if cleaned_detection_frequency != existing_config.scheduling.detection_config.frequency:
                    detection_config_updates["frequency"] = cleaned_detection_frequency
                    updates_applied = True

            if detection_window is not None:
                if not isinstance(detection_window, int):
                    raise ToolError("detection_window must be an integer")
                try:
                    validation_result = validate_window_size(detection_window, "detection")
                except ValueError as exc:
                    raise ToolError(f"Invalid window size: {exc}") from exc
                detection_config_updates["detection_window"] = detection_window
                updates_applied = True
                if validation_result.get("warning"):
                    warning_text = f"⚠️  Warning: {validation_result['warning']}"
                    warnings.append(warning_text)
                    await reporter.warning(warning_text)
                    log_message(warning_text, "warning", "modify_kb_config", "step", request_id=request_id)

            if detection_is_active is not None:
                if not isinstance(detection_is_active, bool):
                    raise ToolError("detection_is_active must be a boolean")
                if detection_is_active != existing_config.scheduling.detection_config.is_active:
                    detection_config_updates["is_active"] = detection_is_active
                    updates_applied = True

            if training_config_updates:
                try:
                    updated_training_payload = existing_config.scheduling.training_config.model_dump(by_alias=True)
                    updated_training_payload.update(training_config_updates)
                    updated_training_config = TrainingConfig.model_validate(updated_training_payload)
                except ValidationError as exc:
                    raise ToolError(f"Invalid training configuration: {exc}")
            else:
                updated_training_config = existing_config.scheduling.training_config

            if detection_config_updates:
                try:
                    updated_detection_payload = existing_config.scheduling.detection_config.model_dump(by_alias=True)
                    updated_detection_payload.update(detection_config_updates)
                    updated_detection_config = DetectionConfig.model_validate(updated_detection_payload)
                except ValidationError as exc:
                    raise ToolError(f"Invalid detection configuration: {exc}")
            else:
                updated_detection_config = existing_config.scheduling.detection_config

            try:
                updated_scheduling_config = SchedulingConfig(
                    training_config=updated_training_config,
                    detection_config=updated_detection_config,
                )
            except ValidationError as exc:
                raise ToolError(f"Invalid scheduling configuration: {exc}")

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

            try:
                new_config = KBConfig(
                    name=updated_name,
                    description=updated_description,
                    change_flag=updated_change_flag,
                    scheduling=updated_scheduling_config,
                    algorithms=updated_algorithms,
                )
            except ValidationError as exc:
                raise ToolError(f"Input validation failed: {exc}")

            if "from" in training_config_updates or "to" in training_config_updates:
                try:
                    training_from_dt = datetime.fromisoformat(new_config.scheduling.training_config.from_.replace("Z", "+00:00"))
                    training_to_dt = datetime.fromisoformat(new_config.scheduling.training_config.to.replace("Z", "+00:00"))
                except ValueError as exc:
                    raise ToolError(f"Invalid timestamp format: {exc}")
                if training_to_dt <= training_from_dt:
                    raise ToolError("training_to must be after training_from")

            log_message(
                f"✓ Step 2 completed in {time.time() - step_start:.2f}s",
                "info",
                "modify_kb_config",
                "step",
                request_id=request_id,
                extra_data={"config_id": config_id},
            )

            step_start = time.time()
            await reporter.step(3, "Step 3/4: Validating algorithms and SQL queries")
            log_message(
                "Step 3/4: Validating algorithms and SQL queries",
                "info",
                "modify_kb_config",
                "step",
                request_id=request_id,
                extra_data={"config_id": config_id},
            )

            internal_algorithms = parse_algorithms_to_internal_format(new_config.algorithms)
            algorithm_errors = validate_algorithms(internal_algorithms)
            if algorithm_errors:
                error_msg = "Algorithm validation failed:\n" + "\n".join(f"- {err}" for err in algorithm_errors)
                raise ToolError(error_msg)

            validate_training_query = training_query_updated or algorithms_updated
            validate_detection_query = detection_query_updated or algorithms_updated

            async def _validate_query(query: str, label: str):
                await asyncio.to_thread(QueryValidator.validate, query, label)
                preview = await elasticsearch_sql(f"{query} LIMIT 0", ctx=ctx)
                available_fields = [col.get("name") for col in preview.get("columns", []) if col.get("name")]
                validate_algorithm_dimensions(new_config.algorithms, available_fields, label)

            if validate_training_query:
                await _validate_query(new_config.scheduling.training_config.training_query, "training")

            if validate_detection_query:
                await _validate_query(new_config.scheduling.detection_config.detection_query, "detection")

            log_message(
                f"✓ Step 3 completed in {time.time() - step_start:.2f}s",
                "info",
                "modify_kb_config",
                "step",
                request_id=request_id,
                extra_data={"config_id": config_id},
            )

            payload = new_config.model_dump(by_alias=True)

            step_start = time.time()
            await reporter.step(4, "Step 4/4: Persisting configuration")
            log_message(
                "Step 4/4: Persisting configuration",
                "info",
                "modify_kb_config",
                "step",
                request_id=request_id,
                extra_data={"config_id": config_id},
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
                    extra_data={"config_id": config_id},
                )
                raise ToolError("No changes were made to the configuration")

            log_message(
                f"✓ Step 4 completed in {time.time() - step_start:.2f}s",
                "info",
                "modify_kb_config",
                "step",
                request_id=request_id,
                extra_data={"config_id": config_id},
            )

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
            success_msg = f"SUCCESS: Configuration '{config_id}' updated successfully."
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
            extra_data={"config_id": config_id},
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
            extra_data={"config_id": config_id},
        )
        raise
    except Exception as exc:
        await reporter.error(f"❌ modify_kb_config hit an unexpected error: {exc}")
        duration_ms = (time.time() - start_time) * 1000
        log_message(
            f"Unexpected error modifying configuration {config_id}: {exc}",
            "error",
            "modify_kb_config",
            "error",
            request_id=request_id,
            duration_ms=duration_ms,
            extra_data={"config_id": config_id, "error_type": type(exc).__name__},
        )
        raise ToolError(f"Failed to modify configuration: {exc}") from exc
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass
