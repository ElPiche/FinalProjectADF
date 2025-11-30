"""description_utils.py - Dynamic description generation for MCP tools

Provides utilities to generate programmatic descriptions based on type annotations
and Pydantic models, ensuring descriptions stay in sync with code changes.
"""

import inspect
from typing import List, Union, get_origin, get_args, Any
from pydantic import BaseModel
from pydantic_core import PydanticUndefined


def generate_algorithm_config_description() -> str:
    """
    Generate a dynamic description for List[AlgorithmConfig] based on current models.

    This function inspects the AlgorithmConfig type and all its variants to create
    a comprehensive description that stays in sync with code changes.
    """
    try:
        from models import SUPPORTED_ALGORITHMS

        supported_algorithms = sorted(str(alg) for alg in SUPPORTED_ALGORITHMS if alg)
        if not supported_algorithms:
            supported_algorithms = ["zscore"]

        main_desc = f"Algorithm configuration payload. Currently supports: {', '.join(supported_algorithms)}."

        format_details = []
        for alg in supported_algorithms:
            format_details.append(
                f"**{alg}** algorithm format:\n- parameters: List of parameter objects. "
                "Each parameter requires a 'dimension' key, optional 'metadata', and an 'is_active' toggle."
            )

        return f"{main_desc}\n\n" + "\n\n".join(format_details)

    except Exception as e:
        # Fallback to static description if introspection fails
        return "List of algorithm configurations (ZScore algorithm supported)"


def _extract_algorithm_info(alg_class: type) -> dict:
    """
    Extract information about an algorithm class for description generation.
    """
    name = getattr(alg_class, '__name__', 'UnknownAlgorithm')

    model_fields = getattr(alg_class, 'model_fields', {})
    alg_name_field = model_fields.get('alg_name')
    if (
        alg_name_field
        and hasattr(alg_name_field, 'default')
        and alg_name_field.default is not None
        and alg_name_field.default is not PydanticUndefined
    ):
        alg_name = alg_name_field.default
    else:
        alg_name = name.lower().replace('config', '')

    # Build field descriptions
    fields_info = []
    for field_name, field_info in model_fields.items():
        if field_name == 'alg_name':
            continue

        field_desc = field_info.description or f"Field: {field_name}"

        if field_name == 'alg_parameters':
            field_desc = (
                "List of parameter objects. Each parameter requires a 'dimension' key and may "
                "include optional 'alg_metadata'."
            )

        fields_info.append(f"- {field_name}: {field_desc}")

    description = f"**{alg_name}** algorithm format"
    if fields_info:
        description += ":\n" + "\n".join(fields_info)

    return {
        'name': alg_name,
        'description': description
    }


def get_supported_algorithms_list() -> List[str]:
    """
    Get a list of supported algorithm names for use in other descriptions.
    """
    try:
        from models import SUPPORTED_ALGORITHMS

        # Ensure we always return a list of strings, even if the source set changes type
        return sorted(str(alg) for alg in SUPPORTED_ALGORITHMS if alg)

    except Exception:
        return ['zscore']  # Fallback


def generate_available_algorithms_description() -> str:
    """
    Generate a dynamic description of all available algorithms for list_available_algorithms.
    """
    try:
        from models import AlgorithmConfig

        actual_type = AlgorithmConfig

        if hasattr(actual_type, '__args__'):
            algorithm_types = actual_type.__args__
        else:
            algorithm_types = [actual_type]

        descriptions = []
        for i, alg_type in enumerate(algorithm_types, 1):
            if inspect.isclass(alg_type) and issubclass(alg_type, BaseModel):
                alg_info = _extract_detailed_algorithm_info(alg_type)
                descriptions.append(f"{i}) {alg_info}")

        if descriptions:
            return "\n\n".join(descriptions)
        else:
            return "1) zscore\n- Description: Z-score based anomaly detection using standard deviation thresholds\n- Parameters:\n  - alg_parameters: List of parameter objects containing a 'dimension' key\n- Example:\n  {\n    \"alg_name\": \"zscore\",\n    \"alg_parameters\": [\n      {\"dimension\": \"response_time\"}\n    ]\n  }"

    except Exception as e:
        # Fallback
        return "1) zscore\n- Description: Z-score based anomaly detection using standard deviation thresholds\n- Parameters:\n  - alg_parameters: List of parameter objects containing a 'dimension' key\n- Example:\n  {\n    \"alg_name\": \"zscore\",\n    \"alg_parameters\": [\n      {\"dimension\": \"response_time\"}\n    ]\n  }"


def _extract_detailed_algorithm_info(alg_class: type) -> str:
    """
    Extract detailed information about an algorithm class for the available algorithms list.
    """
    name = getattr(alg_class, '__name__', 'UnknownAlgorithm')

    # Get the algorithm field default value
    algorithm_field = getattr(alg_class, 'model_fields', {}).get('alg_name')
    if algorithm_field and hasattr(algorithm_field, 'default') and algorithm_field.default is not None:
        alg_name = algorithm_field.default
    else:
        alg_name = name.lower().replace('config', '')

    # Get description from docstring or generate one
    description = alg_class.__doc__ or f"{alg_name.upper()} based anomaly detection"

    # Build parameters list
    params = []
    example_params = []

    for field_name, field_info in alg_class.model_fields.items():
        if field_name == 'alg_name':  # Skip the algorithm identifier field
            continue

        field_desc = field_info.description or f"Field: {field_name}"
        params.append(f"  - {field_name}: {field_desc}")

        # Generate example values
        if field_name == 'alg_parameters':
            example_params.append("      {\"dimension\": \"response_time\"}")

    # Build the full description
    result = f"{alg_name}\n- Description: {description}\n- Parameters:"
    if params:
        result += "\n" + "\n".join(params)
    result += f"\n- Example:\n  {{\n    \"alg_name\": \"{alg_name}\",\n    \"alg_parameters\": [\n"
    if example_params:
        result += ",\n".join(example_params) + "\n"
    else:
        result += "      {\"dimension\": \"column_name\"}\n"
    result += "    ]\n  }"

    return result


def generate_kb_config_template_description() -> str:
    """
    Generate a dynamic description based on the current KBConfigTemplate.json.

    This function reads the template file and creates a comprehensive description
    that stays in sync with any changes to the template structure.
    """
    try:
        import json
        import os

        # Path to the template file - relative to this module
        base_templates = os.path.join(os.path.dirname(__file__), '..', '..', 'Templates')
        template_path = os.path.join(base_templates, 'KBConfigTemplate.json')
        if not os.path.exists(template_path):
            template_path = os.path.join(base_templates, 'New-spec-KBConfigTemplate.json')

        with open(template_path, 'r', encoding='utf-8') as f:
            template = json.load(f)

        # Extract key sections for description
        description_parts = []

        # Basic info
        description_parts.append(f"**Configuration Name**: {template.get('name', 'N/A')}")
        description_parts.append(f"**Description**: {template.get('description', 'N/A')}")
        description_parts.append(f"**Change Flag**: {template.get('change_flag', 'N/A')} (used for triggering change streams)")

        # Scheduling section
        if 'scheduling' in template:
            sched = template['scheduling']
            description_parts.append("\n**Scheduling Configuration**:")

            if 'training_config' in sched:
                tc = sched['training_config']
                description_parts.append("  **Training Config**:")
                description_parts.append(f"    - Query: {tc.get('training_query', 'N/A')[:100]}...")
                description_parts.append(f"    - Time Range: {tc.get('from', 'N/A')} to {tc.get('to', 'N/A')}")
                description_parts.append(f"    - Training Window: {tc.get('training_window', 'N/A')} seconds")
                description_parts.append(f"    - Active: {tc.get('is_active', 'N/A')}")

            if 'detection_config' in sched:
                dc = sched['detection_config']
                description_parts.append("  **Detection Config**:")
                description_parts.append(f"    - Query: {dc.get('detection_query', 'N/A')[:100]}...")
                description_parts.append(f"    - Start Time: {dc.get('from', 'N/A')}")
                description_parts.append(f"    - Frequency: {dc.get('frequency', 'N/A')} (CRON expression)")
                description_parts.append(f"    - Detection Window: {dc.get('detection_window', 'N/A')} seconds")
                description_parts.append(f"    - Active: {dc.get('is_active', 'N/A')}")

        # Algorithms section
        if 'algorithms' in template:
            algorithms = template['algorithms']
            description_parts.append(f"\n**Algorithms** ({len(algorithms)} configured):")

            for i, alg in enumerate(algorithms, 1):
                alg_name = alg.get('alg_name', 'unknown')
                description_parts.append(f"  **Algorithm {i}**: {alg_name}")

                if 'alg_parameters' in alg:
                    params = alg['alg_parameters']
                    description_parts.append(f"    - Parameters ({len(params)} dimensions):")
                    for param in params:
                        if 'dimension' in param:
                            description_parts.append(f"      * Dimension: {param['dimension']}")
                        if 'alg_metadata' in param:
                            metadata = param['alg_metadata']
                            for meta in metadata:
                                description_parts.append(f"        - {meta.get('key', 'N/A')}: {meta.get('value', 'N/A')}")

        return "\n".join(description_parts)

    except Exception as e:
        # Fallback description if template can't be read
        return """**Configuration Structure** (based on KBConfigTemplate.json):
- name: Configuration name (string)
- description: Human-readable description (string)
- change_flag: Change flag for triggering change streams (integer, default: 0)
- scheduling: Contains training_config and detection_config sections
  - training_config: Training data query, time range, window, and active status
  - detection_config: Detection query, start time, frequency (CRON), window, and active status
- algorithms: List of algorithm configurations with alg_name and alg_parameters

**Error reading template**: {str(e)}"""


def generate_kb_config_fields_description() -> str:
    """
    Generate a description of all required and optional fields for KB configuration.
    """
    return """
**Required Fields**:
- name (string): Unique configuration name shown in MCP tooling.
- description (string): Human-readable summary of what the configuration monitors.
- elasticsearch_sql_query (string): Unified SQL query used for both training and detection phases. Must include `$from`/`$to` placeholders.
- query_mode (object): Describes how the SQL query returns data.
  - type ("raw" | "aggregated"): Raw returns individual events; aggregated expects `GROUP BY` output.
  - timestamp_field (string): Column alias in the SQL output that contains ISO 8601 timestamps.
- scheduling.training_config:
  - type ("static" | "rolling"): Training strategy.
  - from (ISO 8601 string): Historical start time for training data.
  - to (ISO 8601 string): Historical end time for training data.
  - is_active (bool): Toggle to pause training jobs.
- scheduling.detection_config:
  - frequency (CRON string): Detection cadence. Must satisfy query-mode minimums (raw ≥ 60s, aggregated ≥ 10s).
  - detection_window (int): Time window in seconds that each detection covers.
  - is_active (bool): Toggle to pause detection jobs.
- algorithm (AlgorithmConfig): Singular algorithm definition with at least one monitored dimension.

**Optional Fields**:
- change_flag (int): Increment to trigger change-stream processing (default 0).
- scheduling.detection_config.from (ISO 8601 string): Optional detection start timestamp.
- bucket_profile_id (string): References a document in `bucket_profiles` to enable time-context bucketing. Null disables the resolver.
- algorithm.parameters[].metadata (list): Algorithm-specific key/value metadata pairs.
- anomaly_config (object): Optional notification settings. Structure:
  - user_emails (list of strings): Email addresses to notify when anomalies are detected. Example: `{"user_emails": ["user@example.com"]}`

**Derived Fields**:
- scheduling.training_config and scheduling.detection_config are constructed automatically from the individual inputs above.
- Dimensions listed inside algorithm.parameters must exactly match column aliases returned by the unified SQL query.
"""


def generate_kb_config_description() -> str:
    """
    Generate a dynamic description for KBConfig based on the actual model structure.

    This function inspects the KBConfig Pydantic model and all its nested models
    to create a comprehensive description that stays in sync with code changes.
    """
    try:
        from models import KBConfig

        def describe_model(model_class: type, indent: str = "") -> str:
            """Recursively describe a Pydantic model and its fields."""
            if not (inspect.isclass(model_class) and issubclass(model_class, BaseModel)):
                return f"{indent}{model_class}"

            lines = []
            lines.append(f"{indent}**{model_class.__name__}**:")

            for field_name, field_info in model_class.model_fields.items():
                field_type = field_info.annotation
                field_desc = field_info.description or f"Field: {field_name}"

                # Handle field aliases (like 'from_' -> 'from')
                display_name = field_info.alias or field_name

                # Handle complex types
                if hasattr(field_type, '__origin__'):
                    # List, Dict, etc.
                    if field_type.__origin__ == list:
                        inner_type = field_type.__args__[0] if field_type.__args__ else Any
                        if inspect.isclass(inner_type) and issubclass(inner_type, BaseModel):
                            lines.append(f"{indent}  - {display_name}: List of {inner_type.__name__}")
                            lines.append(describe_model(inner_type, indent + "    "))
                        else:
                            lines.append(f"{indent}  - {display_name}: {field_desc}")
                    elif field_type.__origin__ == dict:
                        lines.append(f"{indent}  - {display_name}: {field_desc}")
                    else:
                        lines.append(f"{indent}  - {display_name}: {field_desc}")
                elif inspect.isclass(field_type) and issubclass(field_type, BaseModel):
                    # Nested model
                    lines.append(f"{indent}  - {display_name}: {field_desc}")
                    lines.append(describe_model(field_type, indent + "    "))
                else:
                    # Simple field
                    lines.append(f"{indent}  - {display_name}: {field_desc}")

            return "\n".join(lines)

        return describe_model(KBConfig)

    except Exception as e:
        return f"Error generating KBConfig description: {e}"


def generate_kb_config_example() -> str:
    """
    Generate an example JSON structure based on the KBConfig model.
    """
    try:
        from models import (
            AlgorithmConfig,
            AlgorithmParameter,
            DetectionConfig,
            KBConfig,
            QueryMode,
            SchedulingConfig,
            TrainingConfig,
        )
        import json

        example = KBConfig(
            name="Example Configuration",
            description="Example anomaly detection configuration",
            change_flag=0,
            elasticsearch_sql_query="SELECT DATE_TRUNC('HOUR', \"@timestamp\") AS es_timestamp, AVG(latency) AS avg_latency, COUNT(*) AS es_event_count FROM logs WHERE \"@timestamp\" >= '$from' AND \"@timestamp\" < '$to' GROUP BY es_timestamp ORDER BY es_timestamp",
            query_mode=QueryMode(type="aggregated", timestamp_field="es_timestamp"),
            bucket_profile_id="business_hours_v1",
            scheduling=SchedulingConfig(
                training_config=TrainingConfig(
                    **{"from": "2025-01-01T00:00:00Z"},
                    to="2025-01-14T23:59:59Z",
                    is_active=True,
                ),
                detection_config=DetectionConfig(
                    **{"from": "2025-01-15T00:00:00Z"},
                    frequency="*/5 * * * *",
                    detection_window=3600,
                    is_active=True,
                ),
            ),
            algorithm=AlgorithmConfig(
                name="zscore",
                parameters=[
                    AlgorithmParameter(dimension="avg_latency", is_active=True),
                    AlgorithmParameter(
                        dimension="es_event_count",
                        is_active=False,
                        metadata=[{"key": "threshold", "value": "99.5"}],
                    ),
                ],
            ),
        )

        return json.dumps(example.model_dump(by_alias=True), indent=2)

    except Exception as e:
        return f"Error generating KBConfig example: {e}"


def generate_tool_list_for_describe_mcp() -> str:
    """
    Generate a list of all available MCP tools for the describe_mcp_server tool.

    Returns a formatted string with numbered tool names.
    """
    # Hardcoded list of tools to avoid circular import issues
    tools = [
        "1) create_da_config",
        "2) modify_kb_config",
        "3) list_kb_configurations",
        "4) describe_mcp_server",
        "5) list_available_algorithms",
        "6) ping_elasticsearch",
        "7) elasticsearch_sql",
        "8) create_bucket_profile",
        "9) list_bucket_profiles",
        "10) delete_bucket_profile"
    ]
    return "\n".join(tools)


def get_tool_count() -> int:
    """
    Get the current number of registered MCP tools.
    """
    # Hardcoded count to avoid circular import issues
    return 10


def generate_algorithm_config_example() -> str:
    """
    Generate example JSON for AlgorithmConfig based on the actual class structure.
    """
    try:
        from models import AlgorithmConfig, AlgorithmParameter
        import json

        # Create an example instance that mirrors the canonical schema
        example = AlgorithmConfig(
            name="zscore",
            parameters=[
                AlgorithmParameter(dimension="status_code_200_counter", is_active=True),
                AlgorithmParameter(
                    dimension="status_code_5xx_counter",
                    is_active=True,
                    metadata=[{"key": "percentile", "value": "99.5"}],
                ),
            ]
        )

        # Convert to dict and then to JSON string
        example_dict = example.model_dump(by_alias=True)
        return json.dumps(example_dict, indent=2)

    except Exception:
        # Fallback example that still uses the canonical schema
        return '''{
  "name": "zscore",
  "parameters": [
    {"dimension": "status_code_200_counter", "is_active": true},
    {"dimension": "status_code_5xx_counter", "is_active": true}
  ]
}'''


# ============================================================================
# MODULE-LEVEL CONSTANTS
# These are generated at module import time for use in docstrings and Field()
# ============================================================================

# Pre-generate descriptions to avoid runtime overhead
ALGORITHM_CONFIG_DESCRIPTION = generate_algorithm_config_description()
AVAILABLE_ALGORITHMS_DESCRIPTION = generate_available_algorithms_description()

# Get supported algorithms list
try:
    from models import SUPPORTED_ALGORITHMS as _SUPPORTED_ALGORITHMS
    SUPPORTED_ALGORITHMS = _SUPPORTED_ALGORITHMS
except ImportError:
    SUPPORTED_ALGORITHMS = {"zscore"}

# Formatted versions for different contexts
SUPPORTED_ALGORITHMS_LIST = get_supported_algorithms_list()
SUPPORTED_ALGORITHMS_INLINE = ", ".join(SUPPORTED_ALGORITHMS_LIST)
SUPPORTED_ALGORITHMS_QUOTED = ", ".join(f"'{alg}'" for alg in SUPPORTED_ALGORITHMS_LIST)