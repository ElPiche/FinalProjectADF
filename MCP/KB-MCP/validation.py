# validation.py - SQL parsing and validation functions for KB-MCP

import logging
import os
import re

logger = logging.getLogger(__name__)


def _get_int_env(var_name: str, default: int) -> int:
    """Return integer env override while shielding import-time failures."""
    raw_value = os.getenv(var_name)
    if raw_value is None:
        return default
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        logger.warning(
            "Invalid value '%s' for %s; falling back to default %s",
            raw_value,
            var_name,
            default,
        )
        return default


VALIDATION_CONSTANTS = {
    "MIN_TRAINING_WINDOW_SECONDS": _get_int_env("MIN_TRAINING_WINDOW_SECONDS", 1),
    "MIN_DETECTION_WINDOW_SECONDS": _get_int_env("MIN_DETECTION_WINDOW_SECONDS", 1),
    "LARGE_WINDOW_THRESHOLD_DAYS": _get_int_env("LARGE_WINDOW_THRESHOLD_DAYS", 30),
}


def validate_window_size(window_seconds: int, window_type: str = "training") -> dict:
    """Validate configured window size. Returns dict with optional warning.

    Args:
        window_seconds: Window duration in seconds.
        window_type: "training" or "detection".

    Raises:
        ValueError: If the window is invalid.
    """

    min_key = f"MIN_{window_type.upper()}_WINDOW_SECONDS"
    min_value = VALIDATION_CONSTANTS.get(min_key, 1)

    if not isinstance(window_seconds, int):
        raise ValueError(
            f"{window_type.capitalize()} window must be an integer (got {type(window_seconds).__name__})."
        )

    if window_seconds < min_value:
        if min_value >= 60:
            human_min = f"{min_value // 60} minute(s)"
        else:
            human_min = f"{min_value} second(s)"
        raise ValueError(
            f"{window_type.capitalize()} window must be >= {min_value} seconds ({human_min}); got {window_seconds}."
        )

    threshold_days = VALIDATION_CONSTANTS.get("LARGE_WINDOW_THRESHOLD_DAYS", 30)
    threshold_seconds = threshold_days * 86400
    warning = None

    if window_seconds > threshold_seconds:
        window_days = window_seconds / 86400
        warning = (
            f"Large {window_type} window requested: {window_days:.1f} days (threshold: {threshold_days} days). "
            "Very large windows may slow Elasticsearch queries, increase MongoDB document size, and impact ETL/dispatcher performance."
        )
        logger.warning(warning)

    return {"valid": True, "warning": warning}

def extract_sql_output_fields(sql_query: str) -> list[str]:
    """
    Extract all output field names from SQL query.

    This function parses SQL queries to identify all field names that
    could be available as output from the SELECT clause.

    Args:
        sql_query (str): The complete SQL query string

    Returns:
        list[str]: List of all field names that could be output from the query

    Raises:
        ValueError: If query parsing fails due to malformed syntax

    Examples:
        >>> extract_sql_output_fields("SELECT field1, field2 FROM table WHERE condition")
        ['field1', 'field2']
    """
    import re

    # Find SELECT clause
    select_match = re.search(r'\bSELECT\s+(.+?)\s+FROM', sql_query, re.IGNORECASE | re.DOTALL)
    if not select_match:
        return []

    select_content = select_match.group(1).strip()

    # Split by commas, handling functions and aliases
    field_names = []
    fields = re.split(r',', select_content)
    for field in fields:
        field = field.strip()
        # Extract alias or field name
        alias_match = re.search(r'\s+AS\s+([a-zA-Z_][a-zA-Z0-9_]*)', field, re.IGNORECASE)
        if alias_match:
            field_names.append(alias_match.group(1))
        else:
            # Extract field name from expressions like COUNT(field) AS count
            name_match = re.search(r'([a-zA-Z_][a-zA-Z0-9_]*)\s*$', field)
            if name_match:
                field_names.append(name_match.group(1))

    return sorted(list(set(field_names)))


def extract_sql_select_fields(sql_query: str) -> list[str]:
    """
    Extract output field names from SQL SELECT clauses.

    This function parses SQL queries to identify field names defined in SELECT clauses,
    handling aggregations and aliases.

    Args:
        sql_query (str): The complete SQL query string

    Returns:
        list[str]: List of field names extracted from SELECT clauses

    Raises:
        ValueError: If SELECT clause parsing fails due to malformed syntax

    Examples:
        >>> extract_sql_select_fields("SELECT COUNT(*) as count, AVG(field) as avg_val FROM table")
        ['count', 'avg_val']
    """
    import re

    # Find SELECT clause
    select_match = re.search(r'\bSELECT\s+(.+?)\s+FROM', sql_query, re.IGNORECASE | re.DOTALL)
    if not select_match:
        return []

    select_content = select_match.group(1).strip()

    # Split by commas
    fields = re.split(r',', select_content)
    field_names = []
    for field in fields:
        field = field.strip()
        # Extract alias
        alias_match = re.search(r'\s+AS\s+([a-zA-Z_][a-zA-Z0-9_]*)', field, re.IGNORECASE)
        if alias_match:
            field_names.append(alias_match.group(1))
        else:
            # For simple fields or aggregations without alias
            name_match = re.search(r'([a-zA-Z_][a-zA-Z0-9_]*)\s*$', field)
            if name_match:
                field_names.append(name_match.group(1))

    return sorted(list(set(field_names)))


def _extract_eval_field_names(esql_query: str) -> list[str]:
    """
    Extract field names created by EVAL clauses in an ESQL query.

    Args:
        esql_query (str): The complete ESQL query string

    Returns:
        list[str]: List of field names created by EVAL clauses
    """
    import re

    field_names = []

    # Find all EVAL clauses in the query
    eval_matches = re.findall(r'\bEVAL\s+(.+?)(?:\s*\|\s*|\s*$)', esql_query, re.IGNORECASE | re.DOTALL)

    for eval_content in eval_matches:
        # Split by commas to handle multiple assignments in one EVAL
        assignments = _split_eval_assignments(eval_content.strip())

        for assignment in assignments:
            field_name = _extract_field_name_from_eval_assignment(assignment.strip())
            if field_name:
                field_names.append(field_name)

    return field_names


def _split_eval_assignments(eval_content: str) -> list[str]:
    """
    Split EVAL content by commas, handling nested functions and complex expressions.

    Args:
        eval_content (str): The content between EVAL and next pipe

    Returns:
        list[str]: Individual assignment expressions
    """
    assignments = []
    current_assignment = ""
    paren_depth = 0
    in_quotes = False
    quote_char = None

    i = 0
    while i < len(eval_content):
        char = eval_content[i]

        # Handle quotes
        if char in ('"', "'") and (i == 0 or eval_content[i-1] != '\\'):
            if not in_quotes:
                in_quotes = True
                quote_char = char
            elif char == quote_char:
                in_quotes = False
                quote_char = None

        # Handle parentheses
        elif not in_quotes:
            if char == '(':
                paren_depth += 1
            elif char == ')':
                paren_depth -= 1

        # Handle commas (only at top level)
        if char == ',' and paren_depth == 0 and not in_quotes:
            assignments.append(current_assignment.strip())
            current_assignment = ""
        else:
            current_assignment += char

        i += 1

    # Add the last assignment
    if current_assignment.strip():
        assignments.append(current_assignment.strip())

    return assignments


def _extract_field_name_from_eval_assignment(assignment: str) -> str:
    """
    Extract the field name from an EVAL assignment expression.

    Handles patterns like:
    - field_name = expression
    - field_name=expression (no spaces)

    Args:
        assignment (str): A single assignment from EVAL clause

    Returns:
        str: The field name, or empty string if parsing fails
    """
    # Look for field_name = expression pattern
    match = re.match(r'^([a-zA-Z_][a-zA-Z0-9_]*)\s*=', assignment.strip())
    if match:
        return match.group(1).strip()

    return ""


def _split_stats_fields(stats_content: str) -> list[str]:
    """
    Split STATS content by commas, handling nested functions and WHERE clauses.

    Args:
        stats_content (str): The content between STATS and BY keywords

    Returns:
        list[str]: Individual field definitions
    """
    fields = []
    current_field = ""
    paren_depth = 0
    in_quotes = False
    quote_char = None

    i = 0
    while i < len(stats_content):
        char = stats_content[i]

        # Handle quotes
        if char in ('"', "'") and (i == 0 or stats_content[i-1] != '\\'):
            if not in_quotes:
                in_quotes = True
                quote_char = char
            elif char == quote_char:
                in_quotes = False
                quote_char = None

        # Handle parentheses
        elif not in_quotes:
            if char == '(':
                paren_depth += 1
            elif char == ')':
                paren_depth -= 1

        # Handle commas (only at top level)
        if char == ',' and paren_depth == 0 and not in_quotes:
            fields.append(current_field.strip())
            current_field = ""
        else:
            current_field += char

        i += 1

    # Add the last field
    if current_field.strip():
        fields.append(current_field.strip())

    return fields


def _extract_field_name_from_definition(field_definition: str) -> str:
    """
    Extract the field name from a single STATS field definition.

    Handles patterns like:
    - field_name = expression
    - field_name = AGG_FUNCTION(...) WHERE condition

    Args:
        field_definition (str): A single field definition from STATS clause

    Returns:
        str: The field name, or empty string if parsing fails
    """
    # Remove WHERE clause if present (everything after WHERE)
    field_def = re.split(r'\s+WHERE\s+', field_definition, flags=re.IGNORECASE)[0].strip()

    # Look for field_name = expression pattern
    match = re.match(r'^([a-zA-Z_][a-zA-Z0-9_]*)\s*=', field_def.strip())
    if match:
        return match.group(1).strip()

    return ""


def validate_cron_expression(cron_expression: str) -> None:
    """Validate CRON expressions without duplicating croniter usage sites."""
    from models import CRON  # Local import to avoid circular import at module load

    try:
        CRON(cron_expression)
    except ValueError as exc:  # pragma: no cover - exercised by callers
        raise ValueError(f"Invalid CRON expression: {cron_expression}") from exc


def validate_algorithms(algorithms: list[dict] | dict | None) -> list[str]:
    """Validate algorithm configuration payloads (legacy list or new singular format)."""

    errors: list[str] = []

    if algorithms is None:
        errors.append("algorithm configuration cannot be empty")
        return errors

    if isinstance(algorithms, dict):
        algorithm_items = [algorithms]
    else:
        algorithm_items = list(algorithms)

    if not algorithm_items:
        errors.append("algorithm configuration list cannot be empty")
        return errors

    from models import SUPPORTED_ALGORITHMS

    for i, alg in enumerate(algorithm_items):
        if not isinstance(alg, dict):
            errors.append(f"algorithm {i}: must be a dictionary")
            continue

        name = alg.get("name") or alg.get("alg_name")
        if not name:
            errors.append(f"algorithm {i}: missing algorithm name")
            continue

        normalized_name = str(name).strip().lower()
        if normalized_name not in SUPPORTED_ALGORITHMS:
            errors.append(
                f"algorithm {i}: '{name}' is not supported. Supported algorithms: {sorted(SUPPORTED_ALGORITHMS)}"
            )
            continue

        params = alg.get("parameters") or alg.get("alg_parameters")
        if not isinstance(params, list):
            errors.append(f"algorithm {i}: parameters must be a list")
            continue

        if not params:
            errors.append(f"algorithm {i}: parameters cannot be empty")
            continue

        for j, param in enumerate(params):
            if not isinstance(param, dict):
                errors.append(f"algorithm {i}, parameter {j}: must be a dictionary")
                continue

            if not param.get("dimension"):
                errors.append(f"algorithm {i}, parameter {j}: missing dimension")

            metadata = param.get("metadata") or param.get("alg_metadata")
            if metadata is None:
                continue

            if not isinstance(metadata, list):
                errors.append(f"algorithm {i}, parameter {j}: metadata must be a list")
                continue

            for k, meta in enumerate(metadata):
                if not isinstance(meta, dict):
                    errors.append(f"algorithm {i}, parameter {j}, metadata {k}: must be a dictionary")
                    continue
                if "key" not in meta:
                    errors.append(f"algorithm {i}, parameter {j}, metadata {k}: missing key")
                if "value" not in meta:
                    errors.append(f"algorithm {i}, parameter {j}, metadata {k}: missing values")

    return errors