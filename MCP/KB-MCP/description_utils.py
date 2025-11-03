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

        main_desc = f"List of algorithm configurations. Currently supports: {', '.join(supported_algorithms)}."

        format_details = []
        for alg in supported_algorithms:
            format_details.append(
                f"**{alg}** algorithm format:\n- alg_parameters: List of parameter objects. "
                "Each parameter requires a 'dimension' key and may include optional 'alg_metadata'."
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
        template_path = os.path.join(os.path.dirname(__file__), '..', '..', 'Templates', 'KBConfigTemplate.json')

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
                                description_parts.append(f"        - {meta.get('key', 'N/A')}: {meta.get('values', 'N/A')}")

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
- name (string): Unique configuration name
- description (string): Human-readable description of what this monitors
- training_query (string): 
    SQL query for training data.
    This query should return historical data used to train the anomaly detection models.
    Timestamp values in the query should be filtered using placeholders `$from` and `$to` to define the training period.
    The query result must always include countable integer numeric columns for the algorithms to monitor which going to be the dimensions.
- detection_query (string):
    SQL query for detection
    This query should return recent or real-time data used for anomaly detection.
    Timestamp values in the query should be filtered using placeholders `$from` and `$to` and the extractor process will be the one to set these values based on the detection schedule.
- training_from (string): 
    Training start timestamp (ISO format),
    Defines the beginning of the historical data period used for training the models.
    Will be substituted for `$from` in the training_query during model training.
- training_to (string): 
    Training end timestamp (ISO format).
    Defines the end of the historical data period used for training the models.
    Will be substituted for `$to` in the training_query during model training.
- training_is_active (boolean):
    Flag to indicate if training is active.
    If training is not active, the extractor process will skip the training phase.
- detection_is_active (boolean):
    Flag to indicate if detection is active.
    If detection is not active, the extractor process will skip the detection phase.
- training_window (integer):
    Training window in seconds.
    Defines the time window size for training data aggregation.
    This value helps the algorithms to process data points within the specified window.
- detection_window (integer):
    Detection window in seconds.
    Defines the time window size for detection data aggregation.
    The extractor process will take this value to extract the last N seconds of data for anomaly detection.
- detection_frequency (string): 
    Detection frequency (CRON format)
    Defines how often the anomaly detection process should run.
    The extractor process will use this CRON expression to schedule detection runs.
    Make sure to provide a valid CRON expression to ensure proper scheduling.
- detection_start (string):
    Detection start timestamp (ISO format).
    Is a configurable value that defines the beginning of the time range for training data.
    Extractor process will not start training if this value is greater than the current time.
    This field depends on user input and should be set according to the desired training period.
    If the value is not provided, the system will start training from the earliest available data.
- algorithms (List[AlgorithmConfig]): Algorithm configurations

**Optional Fields**:
- change_flag (integer): Change flag for triggering change streams (default: 0)

**Scheduling Fields** (automatically derived from the above):
- scheduling.training_config: Training configuration section
- scheduling.detection_config: Detection configuration section
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
        from models import KBConfig, TrainingConfig, DetectionConfig, SchedulingConfig, AlgorithmConfigItem, AlgorithmParameter

        example = KBConfig(
            name="Example Configuration",
            description="Example anomaly detection configuration",
            change_flag=0,
            scheduling=SchedulingConfig(
                training_config=TrainingConfig(
                    training_query="SELECT * FROM index WHERE timestamp >= '$from' AND timestamp < '$to'",
                    **{"from": "2025-01-01T00:00:00Z"},
                    to="2025-01-07T23:59:59Z",
                    training_window=3600,
                    is_active=True
                ),
                detection_config=DetectionConfig(
                    detection_query="SELECT * FROM index WHERE timestamp >= '$from'",
                    **{"from": "2025-01-08T00:00:00Z"},
                    frequency="*/15 * * * *",
                    detectaon_window=3600,
                    is_active=True
                )
            ),
            algorithms=[
                AlgorithmConfigItem(
                    alg_name="zscore",
                    alg_parameters=[
                        AlgorithmParameter(dimension="response_time"),
                        AlgorithmParameter(dimension="error_count")
                    ]
                )
            ]
        )

        # Convert to dict and handle aliases
        example_dict = example.model_dump(by_alias=True)

        # Pretty print as JSON
        import json
        return json.dumps(example_dict, indent=2)

    except Exception as e:
        return f"Error generating example: {e}"


# Pre-computed descriptions for performance
ALGORITHM_CONFIG_DESCRIPTION = generate_algorithm_config_description()
AVAILABLE_ALGORITHMS_DESCRIPTION = generate_available_algorithms_description()
SUPPORTED_ALGORITHMS = get_supported_algorithms_list()

# Formatted strings for inline docstring usage
SUPPORTED_ALGORITHMS_INLINE = ', '.join(SUPPORTED_ALGORITHMS)
SUPPORTED_ALGORITHMS_QUOTED = ', '.join(f'"{alg}"' for alg in SUPPORTED_ALGORITHMS)


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
        "7) elasticsearch_sql"
    ]
    return "\n".join(tools)


def get_tool_count() -> int:
    """
    Get the current number of registered MCP tools.
    """
    # Hardcoded count to avoid circular import issues
    return 7


def generate_algorithm_config_example() -> str:
    """
    Generate example JSON for AlgorithmConfig based on the actual class structure.
    """
    try:
        from models import AlgorithmConfig, AlgorithmParameter
        import json

        # Create an example instance that mirrors the canonical schema
        example = AlgorithmConfig(
            alg_name="zscore",
            alg_parameters=[
                AlgorithmParameter(dimension="status_code_200_counter"),
                AlgorithmParameter(dimension="status_code_5xx_counter")
            ]
        )

        # Convert to dict and then to JSON string
        example_dict = example.model_dump()
        return json.dumps(example_dict, indent=2)

    except Exception:
        # Fallback example that still uses the canonical schema
        return '''{
  "alg_name": "zscore",
  "alg_parameters": [
    {"dimension": "status_code_200_counter"},
    {"dimension": "status_code_5xx_counter"}
  ]
}'''