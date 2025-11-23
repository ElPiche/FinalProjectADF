import asyncio
import json
import os
import sys
import time
import uuid
from typing import List

from mcp.server.fastmcp import Context
from mcp.server.fastmcp.exceptions import ToolError

from models import AlgorithmConfig
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


async def create_da_config(
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
    algorithms: List[AlgorithmConfig],
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
        extra_data={"config_name": name, "algorithm_count": len(algorithms) if algorithms else 0},
    )

    try:
        async with asyncio.timeout(MAX_TOOL_EXECUTION_TIME):
            # Step 1: Window validation
            step_start = time.time()
            await reporter.step(1, "Step 1/5: Validating window sizes")
            log_message("Step 1/5: Validating window sizes", "info", "create_da_config", "step", request_id=request_id)
            try:
                training_window_result = validate_window_size(training_window, "training")
                detection_window_result = validate_window_size(detection_window, "detection")
            except ValueError as exc:
                raise ToolError(f"Invalid window size: {exc}") from exc

            for result in (training_window_result, detection_window_result):
                if result.get("warning"):
                    warning_text = f"⚠️  Warning: {result['warning']}"
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
            from pydantic import ValidationError
            from models import KBConfig, TrainingConfig, DetectionConfig, SchedulingConfig, AlgorithmConfigItem

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

            try:
                validate_cron_expression(detection_frequency)
            except ValueError as exc:
                raise ToolError(str(exc)) from exc

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
                        is_active=training_is_active,
                    ),
                    detection_config=DetectionConfig(
                        detection_query=detection_query,
                        **{"from": detection_start},
                        frequency=detection_frequency,
                        detection_window=detection_window,
                        is_active=detection_is_active,
                    ),
                ),
                algorithms=algorithm_items,
            )

            from datetime import datetime

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
            await reporter.step(3, "Step 3/5: Validating algorithms and SQL queries")
            log_message("Step 3/5: Validating algorithms and SQL queries", "info", "create_da_config", "step", request_id=request_id)
            internal_algorithms = parse_algorithms_to_internal_format(config.algorithms)
            algorithm_errors = validate_algorithms(internal_algorithms)
            if algorithm_errors:
                error_msg = "Algorithm validation failed:\n" + "\n".join(f"- {err}" for err in algorithm_errors)
                raise ToolError(error_msg)

            async def _validate_query(query: str, label: str):
                materialized_query = materialize_query_time_range(
                    query,
                    training_from,
                    training_to,
                    label,
                )
                await asyncio.to_thread(QueryValidator.validate, materialized_query, label)
                preview = await elasticsearch_sql(f"{materialized_query} LIMIT 0", ctx=ctx)
                available_fields = [col.get("name") for col in preview.get("columns", []) if col.get("name")]
                validate_algorithm_dimensions(config.algorithms, available_fields, label)

            if config.scheduling.training_config.training_query:
                await _validate_query(config.scheduling.training_config.training_query, "training")

            if config.scheduling.detection_config.detection_query:
                await _validate_query(config.scheduling.detection_config.detection_query, "detection")

            log_message(
                f"✓ Step 3 completed in {time.time() - step_start:.2f}s",
                "info",
                "create_da_config",
                "step",
                request_id=request_id,
            )

            # Prepare config dict for persistence
            config_to_store = config.model_dump(by_alias=True)
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
