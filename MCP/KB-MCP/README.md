# KB-MCP Server

The KB-MCP (Knowledge Base Model Context Protocol) server provides a set of tools for managing Data Analytics (DA) algorithm configurations in the Knowledge Base system.

## Overview

This MCP server enables AI assistants to:
- Create new DA algorithm configurations
- List available algorithms and existing configurations
- Modify existing configurations
- Validate algorithm requests against supported options

## Installation & Setup

### Prerequisites

#### System Requirements
- **Operating System**: Windows 10/11, Linux (Ubuntu/Debian), or macOS
- **Python Version**: Python 3.8+ (Python 3.11 recommended)
- **External Services**:
  - **Elasticsearch**: Version 8.x with SQL API enabled
  - **MongoDB**: Version 4.0+ (5.0+ recommended)

#### Required Python Packages
```bash
pip install fastmcp pydantic pymongo jsonschema croniter elasticsearch==8.15.0
```

**Package Details:**
- `fastmcp`: MCP server framework
- `pydantic`: Data validation and models
- `pymongo`: MongoDB connectivity
- `jsonschema`: JSON schema validation
- `croniter`: CRON expression validation
- `elasticsearch==8.15.0`: Elasticsearch client (specific version for compatibility)

### Installation Options

#### Option 1: Direct Python Installation
```bash
# 1. Navigate to project directory
cd /path/to/FinalProjectADF

# 2. Install Python dependencies
pip install fastmcp pydantic pymongo jsonschema croniter elasticsearch==8.15.0

# 3. Start external services (Elasticsearch + MongoDB)
docker-compose up -d elasticsearch-dataset mongodb

# 4. Run the MCP server
python MCP/KB-MCP/kb-mcp.py
```

#### Option 2: Docker Installation
```bash
# 1. Build the Docker image
docker build -t kb-mcp -f MCP/KB-MCP/Dockerfile .

# 2. Run with external services
docker run --network host kb-mcp
```

#### Option 3: Development Setup
```bash
# 1. Install all dependencies
pip install fastmcp pydantic pymongo jsonschema croniter elasticsearch==8.15.0

# 2. Start full stack
docker-compose up -d

# 3. Run server in development mode
python MCP/KB-MCP/kb-mcp.py --server
```

### Running the Server
```bash
python MCP/KB-MCP/kb-mcp.py
```

The server will start and listen for MCP protocol messages.

### Claude Desktop Integration
The server is configured in `claude_desktop_config.json` to run automatically when Claude starts.

#### Portable Configuration
For portability across different environments, use environment variables instead of hard-coded paths:

```json
{
  "mcpServers": {
    "KB-MCP": {
      "command": "python",
      "args": ["${KB_MCP_PROJECT_ROOT}/MCP/KB-MCP/kb-mcp.py"],
      "env": {
        "KB_MCP_PROJECT_ROOT": "path/to/your/project/FinalProjectADF"
      }
    }
  }
}
```

Replace `"path/to/your/project/FinalProjectADF"` with your actual project root path. This allows the configuration to be copied to any machine by only updating the environment variable.

Alternatively, the project includes a sample config at `MCP/claude-config/claude_desktop_config.json` that uses relative paths from the config file location and can be symlinked or copied to your Claude config location.

### Verification Steps

#### Test Installation
```bash
# 1. Check Python version
python --version  # Should be 3.8+

# 2. Test imports
python -c "import fastmcp, pydantic, pymongo, elasticsearch; print('All imports successful')"

# 3. Test Elasticsearch connection
curl http://localhost:9200/_cluster/health

# 4. Test MongoDB connection
docker exec mongodb mongosh --eval "db.runCommand('ping')"

# 5. Test MCP server startup
python MCP/KB-MCP/kb-mcp.py
```

#### Test MCP Tools
```bash
# Test available algorithms (via MCP client)
# Should show ZScore as implemented

# Test SQL query execution (via MCP client)
# Should execute queries against Elasticsearch
```

## Available Tools

### 1. `describe_mcp_server`
Provides a comprehensive overview of the KB-MCP server and usage guide.

**Usage:**
```python
describe_mcp_server()
```

**Returns:** Detailed documentation about the server and all available tools.

### 2. `list_available_algorithms`
Lists all DA algorithms available in the system, loaded from `Templates/DaConfigTemplate.json`.

**Usage:**
```python
list_available_algorithms()
```

**Returns:** JSON object containing available algorithms with their default parameters.

### 3. `create_da_config`
Creates a new DA algorithm configuration and saves it as a UUID-named JSON file in the KB directory.

**Required Parameters:**
- `description` (str): Human-readable description of the configuration

**Optional Parameters:**
- `query` (str): Elasticsearch query string
- `training_from` (str): Training period start date (ISO 8601)
- `training_to` (str): Training period end date (ISO 8601)
- `detection_frequency` (str): Detection check frequency (e.g., "5m", "1h")
- `detection_start` (str): Detection period start date (ISO 8601)
- `one_shot` (bool): Whether detection should run only once (default: False)
- `algorithms` (list[dict]): List of algorithm configurations

**Usage:**
```python
create_da_config(
    description="HTTP monitoring configuration",
    algorithms=[
        {"Algorithm": "ZScore", "Parameters": {"threshold": 3.0, "observed_value": "status_code_200_counter"}}
    ]
)
```

**Returns:** Success message with save path and full JSON configuration.

**Validation:**
- Description is required
- Algorithms must be from the approved list
- Invalid algorithms return error with available options

### 4. `list_kb_configurations`
Lists all KB configurations stored in the KB directory with their details.

**Usage:**
```python
list_kb_configurations()
```

**Returns:** Formatted summary of all configurations including:
- Configuration ID and filename
- Description
- Algorithms used
- Training and detection periods

### 5. `modify_kb_config`
Updates an existing KB configuration by ID.

**Required Parameters:**
- `config_id` (str): UUID of the configuration to modify

**Optional Parameters:**
- `description` (str): New description
- `query` (str): New Elasticsearch query
- `training_from` (str): New training start date
- `training_to` (str): New training end date
- `detection_frequency` (str): New detection frequency
- `detection_start` (str): New detection start date
- `algorithms` (list[dict]): New algorithm configurations

**Usage:**
```python
modify_kb_config(
    config_id="a1b2c3d4-...",
    description="Updated configuration description"
)
```

**Returns:** Success message with updated configuration details.

## Configuration Structure

**⚠️ IMPORTANT UPDATE (October 2025)**: The configuration structure has been updated to support SQL queries and nested scheduling objects. All configurations now use Elasticsearch SQL syntax instead of ES|QL.

### Current Structure (SQL-based)

```json
{
  "kbConfig": {
    "id": "unique-uuid",
    "name": "Short descriptive name",
    "description": "In-depth description for future AI context",
    "changeFlag": 0,
    "scheduling": {
      "trainingConfig": {
        "trainingQuery": "SELECT DATE_TRUNC('hour', \"@timestamp\") AS es_timestamp, COUNT(CASE WHEN response = '200' THEN 1 END) AS status_code_200_counter FROM \".ds-kibana_sample_data_logs-*\" WHERE \"@timestamp\" >= '2025-10-01T00:00:00.000Z' GROUP BY DATE_TRUNC('hour', \"@timestamp\") ORDER BY es_timestamp",
        "from": "2025-09-01T00:00:00Z",
        "to": "2025-09-30T23:59:59Z",
        "mode": "training",
        "trainingWindow": 60,
        "isActive": true
      },
      "detectionConfig": {
        "detectionQuery": "SELECT DATE_TRUNC('hour', \"@timestamp\") AS es_timestamp, COUNT(CASE WHEN response = '200' THEN 1 END) AS status_code_200_counter FROM \".ds-kibana_sample_data_logs-*\" WHERE \"@timestamp\" >= '2025-10-10T00:00:00.000Z' GROUP BY DATE_TRUNC('hour', \"@timestamp\") ORDER BY es_timestamp",
        "from": "2025-10-10T00:00:00Z",
        "frequency": "*/15 * * * *",
        "mode": "detection",
        "detectionWindow": 60,
        "isActive": false
      }
    },
    "daAlgParameters": {
      "zscore": [
        {
          "observedValue": "status_code_200_counter"
        }
      ]
    }
  }
}
```

### Key Changes from Previous Version
- **Root Object**: `KB_Config` → `kbConfig`
- **Fields**: Added `name` and updated `description` for AI context
- **Scheduling**: Flattened structure → Nested `trainingConfig`/`detectionConfig` objects
- **Queries**: ES|QL syntax → SQL syntax with proper field quoting
- **Algorithms**: Array format → Object format grouped by algorithm type
- **ZScore**: Removed `threshold` field, now uses only `observedValue`

## Supported Algorithms

**⚠️ IMPORTANT UPDATE (October 2025)**: Algorithm support has been updated. Currently only ZScore is fully implemented, with framework ready for future algorithms.

### Currently Supported
- **ZScore**: Statistical anomaly detection
  - Parameters: `observedValue` (str) - Field name from SQL query output to monitor
  - Status: ✅ **Implemented**

### Framework Ready (Implementation Pending)
- **ARMA**: Time series forecasting
  - Parameters: `p` (int), `d` (int), `q` (int), `observedValue` (str)
  - Status: 🔄 **Framework ready**

- **KMeans**: Clustering-based anomaly detection
  - Parameters: `nClusters` (int), `observedValue` (str)
  - Status: 🔄 **Framework ready**

- **IForest**: Isolation Forest anomaly detection
  - Parameters: `nEstimators` (int), `contamination` (float), `randomState` (int), `observedValue` (str)
  - Status: 🔄 **Framework ready**

### Algorithm Development
To add new algorithms:
1. Create algorithm class in `kb-mcp.py` (inherit from BaseModel)
2. Implement `to_dict()` method
3. Update `DaAlgParameters.to_dict()` to include new algorithm type
4. No configuration file changes required - algorithms are detected dynamically

## File Locations

- **Server**: `MCP/KB-MCP/server.py`
- **Configurations**: `KB/*.json` (UUID-named files)
- **Templates**: `Templates/DaConfigTemplate.json`
- **Claude Config**: `MCP/claude-config/claude_desktop_config.json`

## Error Handling

The server provides detailed error messages for:
- Invalid SQL syntax (validated using elasticsearch-sql tool)
- Missing or mismatched field names in SQL output
- Invalid CRON expressions for scheduling
- MongoDB connection failures
- Algorithm parameter validation errors
- Cross-validation failures between SQL output and observed values

## Development

### Adding New Algorithms
1. Update algorithm classes in `kb-mcp.py` (e.g., add ARMA, KMeans, IForest classes)
2. Implement `to_dict()` method for each algorithm
3. Update `DaAlgParameters.to_dict()` to include new algorithm types
4. The server will automatically recognize them
5. No configuration file changes required

### Modifying Tools
- Tools are defined as functions decorated with `@mcp.tool()`
- Function docstrings are used for AI understanding
- Parameters are automatically validated based on type hints
- SQL validation uses the `elasticsearch-sql` MCP tool

## Troubleshooting

### Server Won't Start
- Check Python version (3.8+ required)
- Verify all dependencies are installed: `fastmcp`, `pydantic`, `pymongo`, `jsonschema`, `croniter`, `elasticsearch==8.15.0`
- Check file permissions
- Ensure Elasticsearch and MongoDB services are running

### Tools Not Available
- Ensure server is running: `python MCP/KB-MCP/kb-mcp.py`
- Check Claude Desktop configuration in `MCP/claude-config/claude_desktop_config.json`
- Verify MCP connection and environment variables
- Refresh MCP server in Claude Desktop

### Configuration Errors
- Use `list_available_algorithms()` to check supported options
- Use `elasticsearch_sql()` to test and validate SQL queries before configuration
- Validate JSON structure against the updated schema
- Check MongoDB connection: `docker exec mongodb mongosh --eval "db.runCommand('ping')"`
- Verify Elasticsearch SQL API: `curl http://localhost:9200/_sql`

### SQL Query Issues
- Test queries with `elasticsearch_sql()` tool first
- Ensure field names in `observedValue` match SQL SELECT aliases
- Use proper quoting for Elasticsearch field names: `"@timestamp"`
- Check date formats: `'2025-10-01T00:00:00.000Z'`
- Verify index patterns exist: `.ds-kibana_sample_data_logs-*`

### Database Connection Issues
- **Elasticsearch**: Check `http://localhost:9200/_cluster/health`
- **MongoDB**: Check `mongodb://admin:1q2w3E*@localhost:27018/?authSource=admin`
- **Docker Services**: Run `docker-compose up -d` to start all services
- **Network**: Use `--network host` for Docker containers or proper port mapping

## License

This project is part of the Knowledge Base system for data analytics and monitoring.