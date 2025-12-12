# Missing KB-MCP Tools Implementation Guide

## Overview

This document outlines the implementation of missing tools from the deprecated `server.py` that should be added to the current `kb-mcp.py` system. These tools provide essential management and informational capabilities for the KB-MCP server.

## 1. modify_kb_config Tool

### Purpose
Allows modifying existing KB configurations stored in MongoDB by ID, enabling updates without full recreation.

### Implementation

```python
@mcp.tool()
def modify_kb_config(
    config_id: str,
    description: str = None,
    training_query: str = None,
    detection_query: str = None,
    training_from: str = None,
    training_to: str = None,
    detection_frequency: str = None,
    detection_start: str = None,
    da_alg_parameters: dict = None
) -> str:
    """
    Modify an existing KB configuration by ID.

    This tool allows updating specific fields of an existing KB configuration stored in MongoDB.
    Only the provided parameters will be updated; others remain unchanged.

    Args:
        config_id (str): UUID of the configuration to modify (required)
        description (str): New description (optional)
        training_query (str): New SQL training query (optional)
        detection_query (str): New SQL detection query (optional)
        training_from (str): New training start date (ISO format, optional)
        training_to (str): New training end date (ISO format, optional)
        detection_frequency (str): New detection frequency (CRON format, optional)
        detection_start (str): New detection start date (ISO format, optional)
        da_alg_parameters (dict): New algorithm parameters (optional)

    Returns:
        Success message with updated configuration details, or error message
    """
    client = connect_mongodb()
    if client is None:
        return "ERROR: Failed to connect to MongoDB"

    try:
        db = client["kb_configs"]
        collection = db["configurations"]

        # Find the configuration
        config_doc = collection.find_one({"KB_Config.Id": config_id})
        if not config_doc:
            return f"ERROR: Configuration with ID '{config_id}' not found"

        # Prepare updates
        updates = {}

        if description is not None:
            updates["KB_Config.Description"] = description

        if training_query is not None:
            # Validate SQL query
            try:
                sql_obj = SQL(training_query)
                updates["KB_Config.Scheduling.TrainingConfig.TrainingQuery"] = training_query
            except ValueError as e:
                return f"ERROR: Invalid training query: {str(e)}"

        if detection_query is not None:
            # Validate SQL query
            try:
                sql_obj = SQL(detection_query)
                updates["KB_Config.Scheduling.DetectionConfig.DetectionQuery"] = detection_query
            except ValueError as e:
                return f"ERROR: Invalid detection query: {str(e)}"

        if training_from is not None:
            updates["KB_Config.Scheduling.TrainingConfig.From"] = training_from

        if training_to is not None:
            updates["KB_Config.Scheduling.TrainingConfig.To"] = training_to

        if detection_frequency is not None:
            # Validate CRON
            try:
                CRON(detection_frequency)
                updates["KB_Config.Scheduling.DetectionConfig.Frequency"] = detection_frequency
            except ValueError as e:
                return f"ERROR: Invalid detection frequency: {str(e)}"

        if detection_start is not None:
            updates["KB_Config.Scheduling.DetectionConfig.From"] = detection_start

        if da_alg_parameters is not None:
            # Validate algorithm parameters
            try:
                # Extract zscore algorithms
                zscore_algs = []
                if "zscore" in da_alg_parameters:
                    for alg_dict in da_alg_parameters["zscore"]:
                        if isinstance(alg_dict, dict) and "observedValue" in alg_dict:
                            zscore_algs.append(ZScore(observed_value=alg_dict["observedValue"]))

                if zscore_algs:
                    da_params = DaAlgParameters(algorithms=zscore_algs)
                    updates["KB_Config.DaAlgParameters"] = da_alg_parameters
                else:
                    return "ERROR: No valid ZScore algorithms found in da_alg_parameters"
            except Exception as e:
                return f"ERROR: Invalid algorithm parameters: {str(e)}"

        if not updates:
            return "WARNING: No valid updates provided"

        # Apply updates
        result = collection.update_one(
            {"KB_Config.Id": config_id},
            {"$set": updates}
        )

        if result.modified_count == 0:
            return "WARNING: No changes were made to the configuration"

        # Retrieve and return updated configuration
        updated_doc = collection.find_one({"KB_Config.Id": config_id})
        return f"SUCCESS: Configuration '{config_id}' updated successfully.\n\nUpdated configuration:\n{json.dumps(updated_doc, indent=2)}"

    except Exception as e:
        log_message(f"Error modifying configuration {config_id}: {str(e)}", "error")
        return f"ERROR: Failed to modify configuration: {str(e)}"
    finally:
        try:
            client.close()
        except:
            pass
```

### Usage Example
```python
# Update description and detection frequency
result = modify_kb_config(
    config_id="12345678-1234-1234-1234-123456789abc",
    description="Updated HTTP monitoring configuration",
    detection_frequency="*/10 * * * *"
)
```

## 2. list_kb_configurations Tool

### Purpose
Lists all KB configurations stored in MongoDB with their details.

### Implementation

```python
@mcp.tool()
def list_kb_configurations() -> str:
    """
    List all KB configurations stored in MongoDB.

    This tool retrieves all KB configurations from the database and returns
    a formatted summary including IDs, descriptions, algorithms, and scheduling.

    Returns:
        Formatted string listing all KB configurations with their details
    """
    client = connect_mongodb()
    if client is None:
        return "ERROR: Failed to connect to MongoDB"

    try:
        db = client["kb_configs"]
        collection = db["configurations"]

        # Retrieve all configurations
        configs = list(collection.find({}, {"_id": 0}))

        if not configs:
            return "No KB configurations found in the database."

        # Format output
        output = "# KB Configurations Summary\n\n"
        output += f"Found {len(configs)} configuration(s):\n\n"

        for config_doc in configs:
            kb_config = config_doc.get("KB_Config", {})

            config_id = kb_config.get("Id", "Unknown")
            description = kb_config.get("Description", "No description")

            # Extract algorithm info
            da_params = kb_config.get("DaAlgParameters", {})
            algorithms = []
            if "zscore" in da_params:
                algorithms.extend([f"ZScore({alg.get('observedValue', 'unknown')})" for alg in da_params["zscore"]])

            # Extract scheduling info
            scheduling = kb_config.get("Scheduling", {})
            training_config = scheduling.get("TrainingConfig", {})
            detection_config = scheduling.get("DetectionConfig", {})

            training_from = training_config.get("From", "Unknown")
            training_to = training_config.get("To", "Unknown")
            detection_freq = detection_config.get("Frequency", "Unknown")
            detection_from = detection_config.get("From", "Unknown")

            output += f"## Configuration: {config_id}\n"
            output += f"- **Description**: {description}\n"
            output += f"- **Algorithms**: {', '.join(algorithms) if algorithms else 'None'}\n"
            output += f"- **Training Period**: {training_from} to {training_to}\n"
            output += f"- **Detection**: Every {detection_freq} starting {detection_from}\n\n"

        return output

    except Exception as e:
        log_message(f"Error listing configurations: {str(e)}", "error")
        return f"ERROR: Failed to list configurations: {str(e)}"
    finally:
        try:
            client.close()
        except:
            pass
```

### Usage Example
```python
# List all configurations
result = list_kb_configurations()
print(result)
# Output:
# # KB Configurations Summary
#
# Found 2 configuration(s):
#
# ## Configuration: 12345678-1234-1234-1234-123456789abc
# - **Description**: HTTP monitoring configuration
# - **Algorithms**: ZScore(status_code_200_counter), ZScore(status_code_5xx_counter)
# - **Training Period**: 2025-09-01T00:00:00Z to 2025-09-30T23:59:59Z
# - **Detection**: Every */15 * * * * starting 2025-10-10T00:00:00Z
```

## 3. describe_mcp_server Tool

### Purpose
Provides a comprehensive overview of the KB-MCP server and its capabilities.

### Implementation

```python
@mcp.tool()
def describe_mcp_server() -> str:
    """
    Get a comprehensive description of the KB-MCP server and how to use it.

    This tool provides an overview of the MCP server's purpose, available tools,
    and usage guidelines for the SQL-based Knowledge Base configuration system.
    """
    description = """
# KB-MCP Server Overview

**IMPORTANT UPDATE (October 2025)**: The KB-MCP server has been migrated from ES|QL to SQL queries to overcome ES|QL's 10,000 entry limitation. All configurations now use Elasticsearch SQL syntax with full pagination support.

## Purpose
The KB-MCP (Knowledge Base Model Context Protocol) server provides tools for creating, managing, and querying Data Analytics (DA) algorithm configurations for the Knowledge Base system.

## Key Features
- **SQL Query Support**: Uses Elasticsearch SQL instead of ES|QL for unlimited result sets
- **MongoDB Storage**: Configurations stored in MongoDB for reliability and scalability
- **Algorithm Validation**: Ensures algorithm parameters match SQL query outputs
- **Comprehensive Management**: Create, modify, list, and query configurations

## Available Tools

### 1. create_da_config
Creates and validates new anomaly detection configurations.
- **Input**: Complete KB configuration object with SQL queries and algorithm parameters
- **Output**: Validation results and MongoDB storage confirmation
- **Use Case**: Setting up new monitoring configurations

### 2. modify_kb_config
Updates existing KB configurations in MongoDB.
- **Input**: Configuration ID and fields to update
- **Output**: Update confirmation with modified configuration
- **Use Case**: Adjusting existing monitoring parameters

### 3. list_kb_configurations
Lists all KB configurations stored in MongoDB.
- **Input**: None
- **Output**: Formatted summary of all configurations
- **Use Case**: Administrative overview of deployed configurations

### 4. elasticsearch_sql
Executes SQL queries directly against Elasticsearch.
- **Input**: SQL query string
- **Output**: Query results with columns, rows, and metadata
- **Use Case**: Testing queries and data exploration

### 5. describe_mcp_server (this tool)
Provides server overview and usage guidance.
- **Input**: None
- **Output**: Comprehensive documentation
- **Use Case**: Learning about the system capabilities

## How to Use

### 1. Data Exploration First
Before creating configurations, use the `elasticsearch_sql` tool to explore your data and craft appropriate SQL queries.

### 2. Configuration Creation
Use `create_da_config` with a complete configuration object containing:
- Unique ID (auto-generated if not provided)
- Descriptive name
- SQL queries for training and detection
- Scheduling parameters
- Algorithm specifications

### 3. Configuration Management
- Use `list_kb_configurations` to see all deployed configs
- Use `modify_kb_config` to update existing configurations
- Use `elasticsearch_sql` to test and validate queries

## Configuration Structure

```json
{
  "kbConfig": {
    "id": "unique-uuid",
    "description": "Human-readable description",
    "changeFlag": 0,
    "scheduling": {
      "trainingConfig": {
        "trainingQuery": "SELECT ... FROM ... WHERE ... GROUP BY ...",
        "from": "2025-09-01T00:00:00Z",
        "to": "2025-09-30T23:59:59Z",
        "mode": "training",
        "trainingWindow": 60,
        "isActive": false
      },
      "detectionConfig": {
        "detectionQuery": "SELECT ... FROM ... WHERE ... GROUP BY ...",
        "from": "2025-10-10T00:00:00Z",
        "frequency": "*/15 * * * *",
        "mode": "detection",
        "detectionWindow": 60,
        "isActive": false
      }
    },
    "daAlgParameters": {
      "zscore": [
        {"observedValue": "field_name"}
      ]
    }
  }
}
```

## SQL Query Guidelines

### Supported Syntax
- Standard SQL SELECT statements
- Aggregation functions (COUNT, SUM, AVG, etc.)
- Date/time functions (DATE_TRUNC, etc.)
- Conditional expressions (CASE WHEN)
- GROUP BY and ORDER BY clauses

### Field Naming
- Use descriptive aliases for aggregated fields
- Ensure `observedValue` fields in algorithms match SQL output column names
- Example: `COUNT(*) AS request_count` → `observedValue: "request_count"`

### Best Practices
1. Test queries with `elasticsearch_sql` before configuration
2. Use appropriate date ranges for training data
3. Ensure aggregation fields align with anomaly detection needs
4. Validate CRON expressions for scheduling

## Algorithm Support

### Currently Supported
- **ZScore**: Statistical anomaly detection
  - Parameter: `observedValue` (field to monitor)

### Future Support (Framework Ready)
- **ARMA**: Time series forecasting
- **KMeans**: Clustering-based detection
- **IForest**: Isolation forest anomaly detection

## Error Handling

The system provides detailed error messages for:
- Invalid SQL syntax
- Missing or mismatched field names
- Invalid CRON expressions
- MongoDB connection failures
- Algorithm parameter validation errors

## Migration Notes

### From ES|QL to SQL
- **Query Language**: `FROM index | STATS ...` → `SELECT ... FROM index GROUP BY ...`
- **Date Functions**: `DATE_TRUNC(1 hour, @timestamp)` → `DATE_TRUNC('hour', "@timestamp")`
- **Conditional Counts**: `COUNT(*) WHERE condition` → `COUNT(CASE WHEN condition THEN 1 END)`
- **Field References**: `@timestamp` → `"@timestamp"` (quoted for SQL)

### Configuration Updates
- **Storage**: File-based → MongoDB
- **Structure**: Flattened → Nested scheduling objects
- **Algorithms**: Threshold-based → Field-based only

This migration provides unlimited scalability while maintaining all core anomaly detection functionality.
"""
    return description
```

### Usage Example
```python
# Get server description
result = describe_mcp_server()
print(result)
# Output: Comprehensive server documentation
```

## 4. list_available_algorithms Tool

### Purpose
Lists all available DA algorithms with their supported parameters.

### Implementation

```python
@mcp.tool()
def list_available_algorithms() -> str:
    """
    List all available DA algorithms and their parameters.

    This tool returns information about supported anomaly detection algorithms
    by examining the available algorithm classes and their specifications.

    Returns:
        JSON string containing algorithm specifications
    """
    # Define all possible algorithms with their specifications
    algorithm_specs = {
        "ZScore": {
            "name": "ZScore",
            "description": "Statistical anomaly detection using standard deviation thresholds",
            "class_name": "ZScore",
            "parameters": [
                {
                    "name": "observedValue",
                    "type": "string",
                    "required": True,
                    "description": "Field name from SQL query output to monitor for anomalies"
                }
            ],
            "example": {
                "observedValue": "request_count"
            }
        },
        "ARMA": {
            "name": "ARMA",
            "description": "Time series forecasting using AutoRegressive Moving Average",
            "class_name": "ARMA",
            "parameters": [
                {"name": "p", "type": "integer", "description": "AR order"},
                {"name": "d", "type": "integer", "description": "Differencing order"},
                {"name": "q", "type": "integer", "description": "MA order"},
                {"name": "observedValue", "type": "string", "description": "Time series field"}
            ]
        },
        "KMeans": {
            "name": "KMeans",
            "description": "Clustering-based anomaly detection",
            "class_name": "KMeans",
            "parameters": [
                {"name": "nClusters", "type": "integer", "description": "Number of clusters"},
                {"name": "observedValue", "type": "string", "description": "Field to cluster"}
            ]
        },
        "IForest": {
            "name": "IForest",
            "description": "Isolation Forest anomaly detection",
            "class_name": "IForest",
            "parameters": [
                {"name": "nEstimators", "type": "integer", "description": "Number of trees"},
                {"name": "contamination", "type": "float", "description": "Expected anomaly ratio"},
                {"name": "randomState", "type": "integer", "description": "Random seed"},
                {"name": "observedValue", "type": "string", "description": "Field to analyze"}
            ]
        }
    }

    # Check which algorithms are available in the current system
    available_algorithms = []
    future_algorithms = []

    for alg_key, alg_spec in algorithm_specs.items():
        try:
            # Try to get the class from globals
            alg_class = globals().get(alg_spec["class_name"])
            if alg_class:
                # Check if it's a proper algorithm class (has to_dict method)
                if hasattr(alg_class, 'to_dict'):
                    alg_info = alg_spec.copy()
                    alg_info["status"] = "Implemented"
                    available_algorithms.append(alg_info)
                else:
                    # Framework exists but not fully implemented
                    alg_info = alg_spec.copy()
                    alg_info["status"] = "Framework ready - implementation pending"
                    future_algorithms.append(alg_info)
            else:
                # Class doesn't exist yet
                alg_info = alg_spec.copy()
                alg_info["status"] = "Framework ready - implementation pending"
                future_algorithms.append(alg_info)
        except Exception as e:
            # Any error means the algorithm isn't available
            alg_info = alg_spec.copy()
            alg_info["status"] = "Framework ready - implementation pending"
            future_algorithms.append(alg_info)

    algorithms_info = {
        "available_algorithms": available_algorithms,
        "future_algorithms": future_algorithms,
        "usage_notes": [
            "Currently only ZScore is fully implemented",
            "All algorithms require observedValue to match SQL query output fields",
            "Framework is designed for easy addition of new algorithms",
            "Algorithm parameters are validated during configuration creation"
        ]
    }

    return json.dumps(algorithms_info, indent=2)
```

### Usage Example
```python
# List available algorithms
result = list_available_algorithms()
print(result)
# Output: JSON with algorithm specifications
```

## Implementation Notes

### Common Patterns
1. **MongoDB Connection**: All tools follow the same connection pattern with proper error handling
2. **Validation**: SQL queries and CRON expressions are validated before use
3. **Logging**: All operations are logged with appropriate levels
4. **Error Handling**: Comprehensive error messages for debugging

### Integration Points
- **SQL Validation**: Uses the `SQL` class for query validation
- **Algorithm Validation**: Uses `DaAlgParameters` and `ZScore` classes
- **MongoDB Storage**: Consistent document structure and querying
- **Logging**: Centralized logging with `log_message()` function

### Testing Considerations
- **Unit Tests**: Each tool should have validation tests
- **Integration Tests**: End-to-end testing with MongoDB
- **Error Scenarios**: Test invalid inputs and edge cases
- **Performance**: Monitor query execution times

These implementations provide a complete management interface for the KB-MCP system while maintaining consistency with the existing SQL-based architecture.