#!/usr/bin/env python3
import json
import os
import uuid
from enum import Enum
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("KB-MCP")

class DAAlgorithm(Enum):
    ZSCORE = "ZScore"
    ARMA = "ARMA"
    K_MEANS = "K-means"

@mcp.tool()
def modify_kb_config(
    config_id: str,
    description: str = None,
    query: str = None,
    training_from: str = None,
    training_to: str = None,
    detection_frequency: str = None,
    detection_start: str = None,
    algorithms: list[dict] = None
) -> str:
    """
    Modify an existing KB configuration by ID.

    This tool allows updating specific fields of an existing KB configuration.
    Only the provided parameters will be updated; others remain unchanged.
    The configuration must exist and algorithms (if provided) must be valid.

    Args:
        config_id (str): UUID of the configuration to modify (required)
        description (str): New description (optional)
        query (str): New Elasticsearch query (optional)
        training_from (str): New training start date (ISO format, optional)
        training_to (str): New training end date (ISO format, optional)
        detection_frequency (str): New detection frequency (optional)
        detection_start (str): New detection start date (ISO format, optional)
        algorithms (list[dict]): New algorithm configurations (optional)

    Returns:
        Success message with updated configuration details, or error message
    """
    # Load available algorithms for validation
    template_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../Templates/DaConfigTemplate.json"))
    try:
        with open(template_path, "r") as f:
            template = json.load(f)
        available_algorithms = template.get("DA_Config", {}).get("DA_Alg_Parameters", [])
        valid_algorithm_names = {alg["Algorithm"] for alg in available_algorithms}
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return "Error: Cannot load algorithm template for validation"

    # Validate algorithms if provided
    if algorithms is not None:
        for alg in algorithms:
            if alg.get("Algorithm") not in valid_algorithm_names:
                return f"Error: Invalid algorithm '{alg.get('Algorithm')}'. Available algorithms: {', '.join(sorted(valid_algorithm_names))}"

    # Find and load the configuration file
    kb_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../KB"))
    config_filename = f"{config_id}.json"
    config_path = os.path.join(kb_dir, config_filename)

    if not os.path.exists(config_path):
        return f"Error: Configuration with ID '{config_id}' not found"

    try:
        with open(config_path, "r") as f:
            data = json.load(f)

        if 'KB_Config' not in data:
            return f"Error: Invalid configuration format in {config_filename}"

        config = data['KB_Config']

        # Update provided fields
        if description is not None:
            config['Description'] = description
        if query is not None:
            config['Query_Elastic']['query'] = query
        if training_from is not None:
            config['Scheduling']['TrainingPeriod']['from'] = training_from
        if training_to is not None:
            config['Scheduling']['TrainingPeriod']['to'] = training_to
        if detection_frequency is not None:
            config['Scheduling']['Detection']['frequency'] = detection_frequency
        if detection_start is not None:
            config['Scheduling']['Detection']['start'] = detection_start
        if algorithms is not None:
            config['DA_Alg_Parameters'] = algorithms

        # Save the updated configuration
        with open(config_path, "w") as f:
            json.dump(data, f, indent=2)

        return f"Configuration '{config_id}' updated successfully.\n\nUpdated configuration:\n{json.dumps(data, indent=2)}"

    except (json.JSONDecodeError, KeyError, IOError) as e:
        return f"Error updating configuration: {str(e)}"

@mcp.tool()
def list_kb_configurations() -> str:
    """
    List all KB configurations stored in the KB directory.

    This tool scans the KB folder for configuration files, parses each valid
    JSON configuration, and returns a summary of all defined KB series including
    their IDs, descriptions, algorithms, and scheduling information.

    Returns:
        Formatted string listing all KB configurations with their details
    """
    kb_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../KB"))
    configurations = []

    if not os.path.exists(kb_dir):
        return "Error: KB directory not found"

    for filename in os.listdir(kb_dir):
        if filename.endswith('.json') and filename not in ['TestKB.json', 'da-config.json']:
            filepath = os.path.join(kb_dir, filename)
            try:
                with open(filepath, 'r') as f:
                    data = json.load(f)

                if 'KB_Config' in data:
                    config = data['KB_Config']
                    config_id = config.get('Id', 'Unknown')
                    description = config.get('Description', 'No description')
                    algorithms = [alg.get('Algorithm', 'Unknown') for alg in config.get('DA_Alg_Parameters', [])]
                    scheduling = config.get('Scheduling', {})
                    training = scheduling.get('TrainingPeriod', {})
                    detection = scheduling.get('Detection', {})

                    configurations.append({
                        'id': config_id,
                        'filename': filename,
                        'description': description,
                        'algorithms': algorithms,
                        'training_from': training.get('from', 'Unknown'),
                        'training_to': training.get('to', 'Unknown'),
                        'detection_frequency': detection.get('frequency', 'Unknown'),
                        'detection_start': detection.get('start', 'Unknown')
                    })
            except (json.JSONDecodeError, KeyError, IOError) as e:
                configurations.append({
                    'id': 'Error',
                    'filename': filename,
                    'description': f'Error reading file: {str(e)}',
                    'algorithms': [],
                    'training_from': 'Unknown',
                    'training_to': 'Unknown',
                    'detection_frequency': 'Unknown',
                    'detection_start': 'Unknown'
                })

    if not configurations:
        return "No KB configurations found in the KB directory."

    # Format the output
    output = "# KB Configurations Summary\n\n"
    output += f"Found {len(configurations)} configuration(s):\n\n"

    for config in configurations:
        output += f"## Configuration: {config['id']}\n"
        output += f"- **File**: {config['filename']}\n"
        output += f"- **Description**: {config['description']}\n"
        output += f"- **Algorithms**: {', '.join(config['algorithms'])}\n"
        output += f"- **Training Period**: {config['training_from']} to {config['training_to']}\n"
        output += f"- **Detection**: Every {config['detection_frequency']} starting {config['detection_start']}\n\n"

    return output

@mcp.tool()
def describe_mcp_server() -> str:
    """
    Get a general description of the KB-MCP server and how to use it.

    This tool provides an overview of the MCP server's purpose and available tools,
    helping users understand how to interact with the Knowledge Base configuration system.
    """
    description = """
    # KB-MCP Server Overview

    The KB-MCP (Knowledge Base Model Context Protocol) server provides tools for creating and managing Data Analytics (DA) algorithm configurations for the Knowledge Base system.

    ## Purpose
    - Create structured JSON configurations for DA algorithms
    - Validate algorithm requests against available templates
    - Save configurations to the KB directory with unique UUID-based filenames
    - Provide information about available algorithms and their parameters

    ## Available Tools
    1. **describe_mcp_server**: Get this overview and usage guide
    2. **list_available_algorithms**: List all supported DA algorithms with their default parameters
    3. **create_da_config**: Create a new DA configuration with specified parameters

    ## How to Use
    1. First, call `list_available_algorithms` to see what DA algorithms are supported
    2. Then, call `create_da_config` with your desired parameters
    3. The configuration will be saved as a UUID-named JSON file in the KB directory
    4. Only algorithms from the template are accepted - invalid algorithms will be rejected

    ## Configuration Structure
    Configurations include:
    - Auto-generated UUID as ID
    - Description
    - Elastic query for data retrieval
    - Training and detection scheduling periods
    - Array of DA algorithms with their parameters

    ## Example Usage
    To create a configuration with ZScore algorithm:
    ```
    create_da_config(
        description="HTTP monitoring config",
        algorithms=[{"Algorithm": "ZScore", "Parameters": {"threshold": 3.0, "observed_value": "status_code_200_counter"}}]
    )
    ```
    """
    return description

@mcp.tool()
def list_available_algorithms() -> str:
    """
    List all available DA algorithms from the configuration template.

    This tool reads the DaConfigTemplate.json file and returns a list of
    available algorithms with their default parameters.

    Returns:
        JSON string containing the list of available algorithms
    """
    template_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../Templates/DaConfigTemplate.json"))
    try:
        with open(template_path, "r") as f:
            template = json.load(f)
        algorithms = template.get("DA_Config", {}).get("DA_Alg_Parameters", [])
        return json.dumps({"available_algorithms": algorithms}, indent=2)
    except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
        return f"Error loading algorithms: {str(e)}"

@mcp.tool()
def create_da_config(
    description: str,
    query: str = "FROM .ds-kibana_sample_data_logs-* | WHERE @timestamp >= '2025-10-01T00:00:00.000Z' AND @timestamp < '2025-11-01T00:00:00.000Z' | EVAL es_timestamp = DATE_TRUNC(1 hour, @timestamp) | STATS status_code_200_counter = COUNT(*) WHERE response == '200', status_code_5xx_counter = COUNT(*) WHERE response >= '500' AND response < '600' BY es_timestamp | SORT es_timestamp",
    training_from: str = "2025-09-01T00:00:00Z",
    training_to: str = "2025-09-30T23:59:59Z",
    detection_frequency: str = "5m",
    detection_start: str = "2025-10-01T00:00:00Z",
    one_shot: bool = False,
    algorithms: list[dict] = None
) -> str:
    """
    Create a Data Analytics (DA) algorithm configuration for the Knowledge Base system.

    This tool generates a complete KB_Config JSON structure with auto-generated UUID,
    saves it as a UUID-named file in the KB directory, and returns the configuration details.

    ## What it creates:
    - Unique configuration ID (UUID)
    - Structured JSON with KB_Config wrapper
    - Elastic query for data retrieval
    - Training and detection scheduling periods
    - Array of validated DA algorithms with parameters

    ## Available Algorithms (dynamically loaded from template):
    - ZScore: Statistical anomaly detection with threshold and observed_value
    - ARMA: Time series forecasting with n_estimators and contamination
    - K-means: Clustering-based anomaly detection with n_estimators and contamination

    ## Usage Examples:

    **Basic usage (loads all available algorithms):**
    create_da_config()

    **Custom description and algorithms:**
    create_da_config(
        description="HTTP monitoring configuration",
        algorithms=[
            {"Algorithm": "ZScore", "Parameters": {"threshold": 3.0, "observed_value": "status_code_200_counter"}},
            {"Algorithm": "ARMA", "Parameters": {"n_estimators": 200, "contamination": 0.05}}
        ]
    )

    **Custom scheduling:**
    create_da_config(
        training_from="2025-09-01T00:00:00Z",
        training_to="2025-09-30T23:59:59Z",
        detection_frequency="10m",
        detection_start="2025-10-01T00:00:00Z"
    )

    ## Validation:
    - Only algorithms from DaConfigTemplate.json are accepted
    - Invalid algorithms return error with available options
    - Configuration saved to KB/{uuid}.json

    Args:
        description (str): Human-readable description (REQUIRED)
        query (str): Elasticsearch query string for data retrieval
        training_from (str): Training period start date (ISO 8601 format)
        training_to (str): Training period end date (ISO 8601 format)
        detection_frequency (str): Detection check frequency (e.g., "5m", "1h")
        detection_start (str): Detection period start date (ISO 8601 format)
        one_shot (bool): Whether detection should run only once (default: False)
        algorithms (list[dict]): List of algorithm configs. Each dict must have:
            - "Algorithm": str (must be in available algorithms)
            - "Parameters": dict (algorithm-specific parameters)

    Returns:
        str: Success message with save path + full JSON configuration, or error message
    """
    # Load available algorithms for validation
    template_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../Templates/DaConfigTemplate.json"))
    try:
        with open(template_path, "r") as f:
            template = json.load(f)
        available_algorithms = template.get("DA_Config", {}).get("DA_Alg_Parameters", [])
        valid_algorithm_names = {alg["Algorithm"] for alg in available_algorithms}
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return "Error: Cannot load algorithm template for validation"

    if algorithms is not None:
        for alg in algorithms:
            if alg.get("Algorithm") not in valid_algorithm_names:
                return f"Error: Invalid algorithm '{alg.get('Algorithm')}'. Available algorithms: {', '.join(sorted(valid_algorithm_names))}"

    if algorithms is None:
        # Load algorithms from template
        template_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../Templates/DaConfigTemplate.json"))
        try:
            with open(template_path, "r") as f:
                template = json.load(f)
            algorithms = template.get("DA_Config", {}).get("DA_Alg_Parameters", [])
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            # Fallback to default algorithms if template loading fails
            algorithms = [
                {
                    "Algorithm": DAAlgorithm.ZSCORE.value,
                    "Parameters": {
                        "threshold": 3.0,
                        "observed_value": "status_code_200_counter"
                    }
                },
                {
                    "Algorithm": DAAlgorithm.ARMA.value,
                    "Parameters": {
                        "n_estimators": 200,
                        "contamination": 0.05
                    }
                },
                {
                    "Algorithm": DAAlgorithm.K_MEANS.value,
                    "Parameters": {
                        "n_estimators": 200,
                        "contamination": 0.05
                    }
                }
            ]
    
    try:
        config_id = str(uuid.uuid4())
        config = {
            "KB_Config": {
                "Id": config_id,
                "Description": description,
                "Query_Elastic": {
                    "query": query
                },
                "Scheduling": {
                    "TrainingPeriod": {
                        "from": training_from,
                        "to": training_to
                    },
                    "Detection": {
                        "frequency": detection_frequency,
                        "start": detection_start,
                        "one_shot": one_shot
                    }
                },
                "DA_Alg_Parameters": algorithms
            }
        }

        # Save to file
        config_filename = f"{config_id}.json"
        config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../KB", config_filename))
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)

        return f"Configuration saved to {config_path}\n\n{json.dumps(config, indent=2)}"
    except Exception as e:
        return f"Error creating DA configuration: {str(e)}"

if __name__ == "__main__":
    mcp.run()