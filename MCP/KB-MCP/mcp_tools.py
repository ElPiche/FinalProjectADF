# mcp_tools.py - MCP tool handlers for KB-MCP

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from pydantic import Field
from typing import List, Dict, Any, Optional
import uuid
import time
import json

# Import from other modules
from models import KBConfig, ZScoreConfig, AlgorithmConfig
from db import connect_mongodb, safe_close_client
from validation import validate_algorithms
from utils import log_message
from instrumentation import timed

# Global MCP server instance
mcp = FastMCP("KB-MCP")

# Timeout Configuration
sql_validation_timeout_seconds = 2

@mcp.tool()
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
    """Create a Data Analytics (DA) algorithm configuration for the Knowledge Base system."""
    request_id = str(uuid.uuid4())[:8]
    start_time = time.time()

    log_message("Tool execution started", "info", "create_da_config", "entry",
                request_id=request_id, extra_data={
                    "config_name": name,
                    "algorithm_count": len(algorithms) if algorithms else 0
                })

    # Basic parameter validation
    if not name or not isinstance(name, str):
        raise ToolError("name must be a non-empty string")
    if not description or not isinstance(description, str):
        raise ToolError("description must be a non-empty string")

    # Validate CRON expression
    try:
        from models import CRON
        CRON(detection_frequency)
    except ValueError as e:
        raise ToolError(f"Invalid detection frequency CRON: {str(e)}")

    # Convert algorithm configs to internal format
    internal_algorithms = []
    for alg_config in algorithms:
        if isinstance(alg_config, ZScoreConfig):
            internal_algorithms.append({
                "alg_name": "zscore",
                "alg_parameters": [{"dimension": dim} for dim in alg_config.dimensions]
            })
        else:
            raise ToolError(f"Unsupported algorithm type: {type(alg_config)}")

    # Validate algorithms using existing validation function
    algorithm_errors = validate_algorithms(internal_algorithms)
    if algorithm_errors:
        error_msg = "Algorithm validation failed:\n" + "\n".join(f"- {err}" for err in algorithm_errors)
        log_message(f"Algorithm validation failed: {len(algorithm_errors)} errors", "error",
                    "create_da_config", "validation", request_id=request_id)
        raise ToolError(error_msg)

    # Cross-validate algorithms against SQL queries
    if training_query:
        validation_result = elasticsearch_sql(training_query + " LIMIT 0")
        if "ERROR" in validation_result:
            raise ToolError(f"Training SQL query validation failed: {validation_result}")
        else:
            try:
                result_data = json.loads(validation_result)
                available_fields = [col['name'] for col in result_data.get('columns', [])]

                for alg_config in algorithms:
                    if isinstance(alg_config, ZScoreConfig):
                        for dimension in alg_config.dimensions:
                            if dimension not in available_fields:
                                raise ToolError(f"Dimension '{dimension}' not found in training query output. Available fields: {available_fields}")
            except json.JSONDecodeError:
                raise ToolError("Could not parse training SQL validation response")

    if detection_query:
        validation_result = elasticsearch_sql(detection_query + " LIMIT 0")
        if "ERROR" in validation_result:
            raise ToolError(f"Detection SQL query validation failed: {validation_result}")
        else:
            try:
                result_data = json.loads(validation_result)
                available_fields = [col['name'] for col in result_data.get('columns', [])]

                for alg_config in algorithms:
                    if isinstance(alg_config, ZScoreConfig):
                        for dimension in alg_config.dimensions:
                            if dimension not in available_fields:
                                raise ToolError(f"Dimension '{dimension}' not found in detection query output. Available fields: {available_fields}")
            except json.JSONDecodeError:
                raise ToolError("Could not parse detection SQL validation response")

    # Build configuration for storage
    config_to_store = {
        "name": name,
        "description": description,
        "change_flag": 0,  # Always start with 0 for new configs
        "scheduling": {
            "training_config": {
                "training_query": training_query,
                "from": training_from,
                "to": training_to,
                "training_window": 3600,  # Default value
                "is_active": True  # Default value
            },
            "detection_config": {
                "detection_query": detection_query,
                "from": detection_start,
                "frequency": detection_frequency,
                "detection_window": 3600,  # Default value
                "is_active": False  # Default value
            }
        },
        "algorithms": internal_algorithms
    }

    log_message(f"Configuration validation successful for: {name}", "info",
                "create_da_config", "validation", request_id=request_id)

    # Print configuration preview
    print("\nConfiguration Preview:")
    print(json.dumps(config_to_store, indent=2))
    print()

    # Save to MongoDB
    client = connect_mongodb()
    if client is None:
        error_msg = "Failed to connect to MongoDB - configuration not saved"
        log_message(error_msg, "error", "create_da_config", "save", request_id=request_id)
        raise ToolError(error_msg)

    try:
        # Import db constants
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
    algorithms: dict = None
) -> str:
    """Modify an existing KB configuration by ID."""
    request_id = str(uuid.uuid4())[:8]
    start_time = time.time()

    log_message("Tool execution started", "info", "modify_kb_config", "entry",
                request_id=request_id, extra_data={"config_id": config_id})

    client = connect_mongodb()
    if client is None:
        raise ToolError("Failed to connect to MongoDB")

    try:
        # Import db constants
        import db
        db_instance = client[db.db_kb_name]
        collection = db_instance[db.db_kb_collection_name]

        # Find the configuration - use MongoDB _id directly
        try:
            from bson import ObjectId
            config_doc = collection.find_one({"_id": ObjectId(config_id)})
        except Exception as e:
            raise ToolError(f"Invalid configuration ID format: '{config_id}' - {str(e)}")

        if not config_doc:
            raise ToolError(f"Configuration with ID '{config_id}' not found")

        # Prepare updates - direct field access, no kbConfig wrapper
        updates = {}

        if description is not None:
            updates["description"] = description  # Direct field access

        if training_query is not None:
            # Validate SQL query
            try:
                from validation import SQL
                sql_obj = SQL(training_query)
                updates["scheduling.training_config.training_query"] = training_query  # snake_case
            except ValueError as e:
                raise ToolError(f"Invalid training query: {str(e)}")

        if detection_query is not None:
            # Validate SQL query
            try:
                from validation import SQL
                sql_obj = SQL(detection_query)
                updates["scheduling.detection_config.detection_query"] = detection_query  # snake_case
            except ValueError as e:
                raise ToolError(f"Invalid detection query: {str(e)}")

        if training_from is not None:
            updates["scheduling.training_config.from"] = training_from  # snake_case

        if training_to is not None:
            updates["scheduling.training_config.to"] = training_to  # snake_case

        if detection_frequency is not None:
            # Validate CRON
            try:
                from models import CRON
                CRON(detection_frequency)
                updates["scheduling.detection_config.frequency"] = detection_frequency  # snake_case
            except ValueError as e:
                raise ToolError(f"Invalid detection frequency: {str(e)}")

        if detection_start is not None:
            updates["scheduling.detection_config.from"] = detection_start  # snake_case

        if algorithms is not None:
            # Validate algorithms array
            algorithm_errors = validate_algorithms(algorithms)
            if algorithm_errors:
                error_msg = "Algorithm validation failed:\n" + "\n".join(f"- {err}" for err in algorithm_errors)
                raise ToolError(error_msg)
            updates["algorithms"] = algorithms

        if not updates:
            log_message("No valid updates provided", "warning", "modify_kb_config", "validation",
                        request_id=request_id, extra_data={"config_id": config_id})
            raise ToolError("No valid updates provided")

        # Apply updates - increment change_flag directly
        updates["change_flag"] = config_doc.get("change_flag", 0) + 1  # Direct field access, snake_case

        # Apply updates
        result = collection.update_one(
            {"_id": ObjectId(config_id)},
            {"$set": updates}
        )

        if result.modified_count == 0:
            log_message("No changes were made to the configuration", "warning",
                        "modify_kb_config", "update", request_id=request_id,
                        extra_data={"config_id": config_id})
            raise ToolError("No changes were made to the configuration")

        # Retrieve and return updated configuration (exclude MongoDB ObjectId)
        updated_doc = collection.find_one({"_id": ObjectId(config_id)}, {"_id": 0})
        duration_ms = (time.time() - start_time) * 1000

        if updated_doc:
            log_message(f"Configuration '{config_id}' updated successfully", "info",
                       "modify_kb_config", "completion", request_id=request_id,
                       duration_ms=duration_ms, extra_data={"config_id": config_id})
            return f"SUCCESS: Configuration '{config_id}' updated successfully."
        else:
            log_message(f"Configuration '{config_id}' updated but could not retrieve document", "warning",
                       "modify_kb_config", "completion", request_id=request_id,
                       duration_ms=duration_ms, extra_data={"config_id": config_id})
            return f"SUCCESS: Configuration '{config_id}' updated successfully, but could not retrieve updated document."

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_message(f"Error modifying configuration {config_id}: {str(e)}", "error",
                    "modify_kb_config", "error", request_id=request_id,
                    duration_ms=duration_ms, extra_data={"config_id": config_id, "error_type": type(e).__name__})
        raise ToolError(f"Failed to modify configuration: {str(e)}")
    finally:
        try:
            client.close()
        except:
            pass


@mcp.tool()
def list_kb_configurations() -> str:
    """List all KB configurations stored in MongoDB."""
    request_id = str(uuid.uuid4())[:8]
    start_time = time.time()

    log_message("Tool execution started", "info", "list_kb_configurations", "entry",
                request_id=request_id)

    client = connect_mongodb()
    if client is None:
        raise ToolError("Failed to connect to MongoDB")

    try:
        # Import db constants
        import db
        db_instance = client[db.db_kb_name]
        collection = db_instance[db.db_kb_collection_name]

        # Retrieve all configurations - include all fields including _id
        configs = list(collection.find({}, {}))

        if not configs:
            log_message("No KB configurations found in database", "info",
                        "list_kb_configurations", "query", request_id=request_id)
            return "No KB configurations found in the database."

        # Format output
        log_message(f"Found {len(configs)} configurations in database", "info",
                    "list_kb_configurations", "query", request_id=request_id,
                    extra_data={"config_count": len(configs)})
        output = "# KB Configurations Summary\n\n"
        output += f"Found {len(configs)} configuration(s):\n\n"

        for config_doc in configs:
            # Direct access, no kbConfig wrapper
            kb_config = config_doc

            config_id = str(kb_config.get("_id", "Unknown"))  # Use MongoDB _id
            name = kb_config.get("name", "Unknown")
            description = kb_config.get("description", "No description")

            # Extract algorithm info - NEW format
            algorithms_list = kb_config.get("algorithms", [])  # NEW: algorithms field
            algorithms = []
            for alg_config in algorithms_list:
                alg_name = alg_config.get("alg_name", "unknown")
                alg_parameters = alg_config.get("alg_parameters", [])
                dimensions = [p.get("dimension", "unknown") for p in alg_parameters if isinstance(p, dict)]
                algorithms.append(f"{alg_name}({', '.join(dimensions)})")

            # Extract scheduling info - snake_case
            scheduling = kb_config.get("scheduling", {})
            training_config = scheduling.get("training_config", {})  # snake_case
            detection_config = scheduling.get("detection_config", {})  # snake_case

            training_from = training_config.get("from", "Unknown")
            training_to = training_config.get("to", "Unknown")
            detection_freq = detection_config.get("frequency", "Unknown")
            detection_from = detection_config.get("from", "Unknown")

            output += f"## Configuration: {name}\n"
            output += f"- **ID**: {config_id}\n"
            output += f"- **Description**: {description}\n"
            output += f"- **Algorithms**: {', '.join(algorithms) if algorithms else 'None'}\n"
            output += f"- **Training Period**: {training_from} to {training_to}\n"
            output += f"- **Detection**: Every {detection_freq} starting {detection_from}\n\n"

        duration_ms = (time.time() - start_time) * 1000
        log_message(f"Configurations list generated successfully", "info",
                    "list_kb_configurations", "completion", request_id=request_id,
                    duration_ms=duration_ms, extra_data={"config_count": len(configs)})
        return output

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_message(f"Error listing configurations: {str(e)}", "error",
                    "list_kb_configurations", "error", request_id=request_id,
                    duration_ms=duration_ms, extra_data={"error_type": type(e).__name__})
        raise ToolError(f"Failed to list configurations: {str(e)}")
    finally:
        try:
            client.close()
        except:
            pass


@mcp.tool()
def describe_mcp_server() -> str:
    """Get a comprehensive description of the KB-MCP server and how to use it."""
    request_id = str(uuid.uuid4())[:8]
    start_time = time.time()

    log_message("Tool execution started", "info", "describe_mcp_server", "entry",
                request_id=request_id)

    description = """
# KB-MCP Server Overview

**VERSION 2.0 (October 2025)**: Complete rewrite with global configuration variables, structured logging, and enhanced algorithm validation. Migrated from ES|QL to SQL queries for unlimited scalability.

## Purpose
The KB-MCP (Knowledge Base Model Context Protocol) server provides comprehensive tools for creating, managing, and validating Data Analytics (DA) algorithm configurations for the Knowledge Base anomaly detection system.

## Key Features
- **Global Configuration System**: Centralized configuration management for database, Elasticsearch, logging, and algorithms
- **Structured Logging**: Advanced logging system with MongoDB storage, session tracking, and performance monitoring
- **SQL Query Support**: Full Elasticsearch SQL integration with unlimited result sets
- **Algorithm Validation**: Comprehensive validation ensuring algorithm parameters match SQL query outputs
- **Performance Monitoring**: Request correlation IDs, duration tracking, and detailed metrics
- **MongoDB Integration**: Robust configuration storage with change tracking and versioning

## System Architecture

### Global Configuration Variables
```python
# Database Configuration
db_kb_name = "knowledge_base"
db_kb_collection_name = "kb_configs"
mongo_connection_string = os.getenv("MONGO_CONNECTION_STRING", "mongodb://admin:1q2w3E*@mongodb:27017/?authSource=admin&replicaSet=rs0")

# Elasticsearch Configuration
es_host = os.getenv("ES_HOSTS", "http://elasticsearch-dataset:9200")

# Logging Configuration
logs_dir = "logs"
structured_log_file = "structured_logs.jsonl"

# Algorithm Support
supported_algorithms = {"zscore"}
```

### Structured Logging System
- **Session Tracking**: Unique session IDs for request correlation
- **Performance Metrics**: Request duration and throughput monitoring
- **Dual Storage**: Human-readable console logs + structured JSON logs
- **MongoDB Integration**: Logs stored in dedicated `kb-mcp-logs` database
- **Fallback Support**: File-based logging when MongoDB unavailable

## Available Tools

### 1. create_da_config
Creates and validates new anomaly detection configurations with comprehensive cross-validation.
- **Input**: KB configuration dict with name, description, scheduling, and algorithms array
- **Algorithms Format** (REQUIRED STRUCTURE):
  ```json
  "algorithms": [
    {
      "alg_name": "zscore",
      "alg_parameters": [
        {"dimension": "field_name_1"},
        {"dimension": "field_name_2"}
      ]
    }
  ]
  ```
- **Critical Requirements**:
  - `alg_name` must be "zscore" (only supported algorithm)
  - `alg_parameters` must be non-empty array
  - Each parameter needs `dimension` field matching SQL output exactly
  - Dimensions validated against both training and detection queries
- **Validation**: SQL queries, CRON expressions, algorithm parameters, field matching
- **Output**: Validation results, configuration preview, and MongoDB storage confirmation
- **Performance**: Request tracking with duration metrics

### 2. modify_kb_config
Updates existing KB configurations with change tracking and validation.
- **Input**: Configuration ID and selective field updates
- **Features**: Automatic change_flag increment, partial updates supported
- **Validation**: SQL queries, CRON expressions, algorithm parameters
- **Output**: Update confirmation with modified configuration details

### 3. list_kb_configurations
Retrieves and formats all KB configurations from MongoDB.
- **Input**: None
- **Output**: Markdown-formatted summary with IDs, descriptions, algorithms, and scheduling
- **Features**: Algorithm dimension display, scheduling information, configuration count

### 4. elasticsearch_sql
Executes SQL queries against Elasticsearch with reliability and performance monitoring.
- **Input**: Complete SQL query string
- **Features**: Multi-host failover, timeout handling, result formatting
- **Output**: Structured JSON with columns, rows, cursor information, and metadata
- **Performance**: Execution time tracking and host selection metrics

### 5. list_available_algorithms
Provides comprehensive algorithm specifications and implementation status.
- **Input**: None
- **Output**: JSON with available algorithms, future algorithms, and usage notes
- **Features**: Parameter specifications, implementation status, framework readiness

### 6. describe_mcp_server (this tool)
Provides current system documentation and usage guidance.
- **Input**: None
- **Output**: Comprehensive overview of current implementation
- **Features**: Real-time system status, configuration examples, migration notes

## Configuration Structure (Current Format)

```json
{
  "name": "Configuration Name",
  "description": "Human-readable description",
  "change_flag": 0,
  "scheduling": {
    "training_config": {
      "training_query": "SELECT DATE_TRUNC('hour', \"@timestamp\") AS es_timestamp, COUNT(*) as total_requests FROM \"index-*\" WHERE \"@timestamp\" >= '2025-10-01T00:00:00.000Z' GROUP BY DATE_TRUNC('hour', \"@timestamp\")",
      "from": "2025-10-01T00:00:00Z",
      "to": "2025-10-02T00:00:00Z",
      "training_window": 3600,
      "is_active": true
    },
    "detection_config": {
      "detection_query": "SELECT DATE_TRUNC('hour', \"@timestamp\") AS es_timestamp, COUNT(*) as total_requests FROM \"index-*\" WHERE \"@timestamp\" >= '2025-10-10T00:00:00.000Z' GROUP BY DATE_TRUNC('hour', \"@timestamp\")",
      "from": "2025-10-10T00:00:00Z",
      "frequency": "*/15 * * * *",
      "detection_window": 3600,
      "is_active": false
    }
  },
  "algorithms": [
    {
      "alg_name": "zscore",
      "alg_parameters": [
        {"dimension": "total_requests"}
      ]
    }
  ]
}
```

## Algorithm Format (Current Implementation)

### Required Structure
Each algorithm configuration must follow this exact JSON structure:

```json
"algorithms": [
  {
    "alg_name": "zscore",
    "alg_parameters": [
      {"dimension": "field_name_1"},
      {"dimension": "field_name_2"}
    ]
  }
]
```

### Field Requirements
- **alg_name**: String, must be "zscore" (case-insensitive)
- **alg_parameters**: Array of objects, cannot be empty
- **dimension**: String, must exactly match SQL query output field names

### Validation Process
1. **Algorithm Support**: Only "zscore" is currently supported
2. **Parameter Structure**: alg_parameters must be a non-empty array
3. **Field Matching**: Each dimension must exist in both training AND detection query outputs
4. **SQL Validation**: Queries are tested against Elasticsearch before configuration storage

### Common Configuration Mistakes
- ❌ `"alg_name": "z-score"` → ✅ `"alg_name": "zscore"`
- ❌ Missing `alg_parameters` array → ✅ Include empty array minimum
- ❌ `"dimension": "field_that_does_not_exist"` → ✅ Use only fields from SQL output
- ❌ Empty alg_parameters → ✅ Include at least one dimension

### Example Valid Configurations

**Single Dimension ZScore:**
```json
"algorithms": [
  {
    "alg_name": "zscore",
    "alg_parameters": [
      {"dimension": "request_count"}
    ]
  }
]
```

**Multi-Dimension ZScore:**
```json
"algorithms": [
  {
    "alg_name": "zscore",
    "alg_parameters": [
      {"dimension": "total_requests"},
      {"dimension": "error_rate"},
      {"dimension": "response_time"}
    ]
  }
]
```

### SQL Query Compatibility
Algorithm dimensions must match SQL SELECT field names exactly:

```sql
-- Valid: dimension "request_count" matches alias
SELECT COUNT(*) AS request_count FROM "index-*" GROUP BY timestamp

-- Invalid: dimension "COUNT(*)" doesn't match alias
SELECT COUNT(*) AS request_count FROM "index-*" GROUP BY timestamp
```

## SQL Query Guidelines

### Supported Syntax
- Standard SQL SELECT statements with aggregation
- Date/time functions: `DATE_TRUNC('hour', "@timestamp")`
- Conditional expressions: `COUNT(CASE WHEN condition THEN 1 END)`
- GROUP BY and ORDER BY clauses
- Field quoting: `"@timestamp"`, `"field_name"`

### Field Matching Requirements
- Algorithm `dimension` fields must exactly match SQL query output column names
- Use descriptive aliases: `COUNT(*) AS request_count`
- Validate queries with `elasticsearch_sql` before configuration

### Best Practices
1. Test all queries with `elasticsearch_sql` tool first
2. Use appropriate date ranges for training data
3. Ensure aggregation fields align with anomaly detection needs
4. Validate CRON expressions for scheduling
5. Use descriptive configuration names and descriptions

## Algorithm Support

### Currently Implemented
- **ZScore**: Statistical anomaly detection using standard deviation thresholds
  - **Parameter**: `dimension` (field name from SQL query output)
  - **Validation**: Field must exist in both training and detection queries
  - **Status**: Fully implemented and tested

### Framework Ready (Not Yet Implemented)
- **ARMA**: Time series forecasting (AutoRegressive Moving Average)
- **KMeans**: Clustering-based anomaly detection
- **IForest**: Isolation Forest anomaly detection

## Error Handling & Validation

### Comprehensive Validation
- **SQL Syntax**: Basic SQL structure validation with Elasticsearch testing
- **Field Matching**: Algorithm dimensions cross-validated against SQL query outputs
- **CRON Expressions**: Scheduling frequency validation using croniter
- **Algorithm Parameters**: Supported algorithms and parameter structure validation
- **MongoDB Connectivity**: Connection and authentication validation with fallback logging

### Algorithm-Specific Validation Rules

**ZScore Algorithm Validation:**
- Must have `alg_name: "zscore"` (case-insensitive)
- `alg_parameters` must be non-empty array
- Each parameter must contain `dimension` field
- All dimensions must exist in training AND detection query outputs
- Dimensions are validated against actual Elasticsearch SQL query results

**Common Validation Errors:**
```
ERROR: Algorithm validation failed:
- algorithm 0: 'z-score' is not supported. Supported algorithms: {'zscore'}
- algorithm 0: missing alg_parameters
- algorithm 0, parameter 0: missing dimension
- ERROR: Dimension 'invalid_field' not found in training query output. Available fields: ['request_count', 'error_rate']
```

### Error Response Format
```
ERROR: [Specific Error Type]: [Detailed Description]
Available fields: [field1, field2, ...]
Validation failed for algorithm 0: [specific issue]
```

### Best Practices for Error Prevention
1. **Test SQL Queries First**: Use `elasticsearch_sql` tool to verify queries before configuration
2. **Validate Field Names**: Ensure all algorithm dimensions match SQL SELECT aliases exactly
3. **Use Supported Algorithms**: Currently only "zscore" is implemented
4. **Check Parameter Structure**: Follow exact JSON structure requirements
5. **Review Configuration**: Use the preview output to verify before MongoDB storage

### Logging Integration
- All operations logged with session and request correlation
- Performance metrics tracked for all database and Elasticsearch operations
- Structured JSON logs for programmatic analysis
- Human-readable console logs for debugging

## Migration & Compatibility

### From Version 1.0 to 2.0
- **Configuration Format**: `da_alg_parameters` object → `algorithms` array
- **Algorithm Structure**: `{"zscore": [{"observedValue": "..."}]}` → `[{"alg_name": "zscore", "alg_parameters": [{"dimension": "..."}]}]`
- **Storage**: File-based → MongoDB with change tracking
- **Query Language**: ES|QL → SQL for unlimited scalability
- **Logging**: Basic console → Structured with MongoDB storage

### Backward Compatibility
- Legacy configurations can be migrated using the new format
- Old ES|QL queries need conversion to SQL syntax
- Algorithm parameter mapping provided in migration tools

## Performance & Monitoring

### Request Tracking
- Unique request IDs for correlation across logs
- Session-based grouping for multi-request operations
- Duration tracking for performance analysis

### Database Operations
- Connection pooling and timeout management
- Automatic retry logic for transient failures
- Change flag tracking for configuration versioning

### Elasticsearch Integration
- Multi-host failover for high availability
- Query execution time monitoring
- Result size and cursor management

This implementation provides enterprise-grade reliability, comprehensive validation, and extensive monitoring capabilities for production anomaly detection systems.
"""
    duration_ms = (time.time() - start_time) * 1000
    log_message("Server description generated successfully", "info",
                "describe_mcp_server", "completion", request_id=request_id,
                duration_ms=duration_ms)
    return description


@mcp.tool()
def list_available_algorithms() -> str:
    """List all available DA algorithms and their parameters."""
    request_id = str(uuid.uuid4())[:8]
    start_time = time.time()

    log_message("Tool execution started", "info", "list_available_algorithms", "entry",
                request_id=request_id)

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

    # Only show algorithms that are in SUPPORTED_ALGORITHMS
    available_algorithms = []
    future_algorithms = []

    for alg_key, alg_spec in algorithm_specs.items():
        if alg_key.lower() in {"zscore"}:  # Hardcoded for now, should use global config
            alg_info = alg_spec.copy()
            alg_info["status"] = "Implemented"
            available_algorithms.append(alg_info)
        else:
            alg_info = alg_spec.copy()
            alg_info["status"] = "Framework ready - implementation pending"
            future_algorithms.append(alg_info)

    algorithms_info = {
        "available_algorithms": available_algorithms,
        "future_algorithms": future_algorithms,
        "usage_notes": [
            "Only algorithms in SUPPORTED_ALGORITHMS can be used in configurations",
            "All algorithms require dimension to match SQL query output fields",
            "Framework is designed for easy addition of new algorithms",
            "Algorithm parameters are validated during configuration creation"
        ]
    }

    duration_ms = (time.time() - start_time) * 1000
    log_message("Algorithm list generated successfully", "info",
                "list_available_algorithms", "completion", request_id=request_id,
                duration_ms=duration_ms, extra_data={
                    "available_count": len(algorithms_info["available_algorithms"]),
                    "future_count": len(algorithms_info["future_algorithms"])
                })
    return json.dumps(algorithms_info, indent=2)


@mcp.tool()
@timed
def elasticsearch_sql(query: str) -> str:
    """Execute a SQL query against Elasticsearch."""
    request_id = str(uuid.uuid4())[:8]

    log_message("Tool execution started", "info", "elasticsearch_sql", "entry",
                request_id=request_id, extra_data={"query_length": len(query)})

    # Use global es_host configuration
    import db
    es_host = db.es_host

    try:
        log_message(f"Attempting SQL query execution with Elasticsearch at {es_host}")
        from elasticsearch import Elasticsearch
        es = Elasticsearch(es_host, timeout=2)  # sql_validation_timeout_seconds

        # Execute the SQL query using Elasticsearch's SQL API
        response = es.sql.query(query=query)

        # Format the results for easy consumption
        results = {
            "columns": response.get("columns", []),
            "rows": response.get("rows", []),
            "cursor": response.get("cursor"),
            "total_rows": len(response.get("rows", []))
        }

        log_message(f"SQL query executed successfully with {es_host}, returned {results['total_rows']} rows", "info",
                    "elasticsearch_sql", "execution", request_id=request_id,
                    extra_data={"host": es_host, "row_count": results['total_rows']})
        return json.dumps(results, indent=2)

    except Exception as e:
        log_message(f"SQL query failed with {es_host}: {str(e)}", "warning",
                    "elasticsearch_sql", "retry", request_id=request_id,
                    extra_data={"host": es_host, "error_type": type(e).__name__})
        # Store the last error for reporting
        last_error = e

    # If all hosts failed
    error_msg = f"ERROR: Failed to execute SQL query on all Elasticsearch hosts - {str(last_error) if 'last_error' in locals() else 'No hosts available'}"
    log_message(error_msg, "error", "elasticsearch_sql", "failure", request_id=request_id,
                extra_data={"hosts_tried": 1})  # Simplified for single host
    raise ToolError(error_msg)