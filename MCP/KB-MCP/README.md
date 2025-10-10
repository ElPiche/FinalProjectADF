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
- Python 3.8+
- Required packages: `mcp`, `fastmcp`

### Running the Server
```bash
python server.py
```

### Claude Desktop Integration
The server is configured in `claude_desktop_config.json` to run automatically when Claude starts.

#### Portable Configuration
For portability across different environments, use environment variables instead of hard-coded paths:

```json
{
  "mcpServers": {
    "KB-MCP": {
      "command": "python",
      "args": ["${KB_MCP_PROJECT_ROOT}/MCP/KB-MCP/server.py"],
      "env": {
        "KB_MCP_PROJECT_ROOT": "path/to/your/project/FinalProjectADF"
      }
    }
  }
}
```

Replace `"path/to/your/project/FinalProjectADF"` with your actual project root path. This allows the configuration to be copied to any machine by only updating the environment variable.

Alternatively, the project includes a sample config at `MCP/claude-config/claude_desktop_config.json` that uses relative paths from the config file location and can be symlinked or copied to your Claude config location.

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

All configurations follow this JSON structure:

```json
{
  "KB_Config": {
    "Id": "uuid-string",
    "Description": "Human-readable description",
    "Query_Elastic": {
      "query": "Elasticsearch query"
    },
    "Scheduling": {
      "TrainingPeriod": {
        "from": "2025-09-01T00:00:00Z",
        "to": "2025-09-30T23:59:59Z"
      },
      "Detection": {
        "frequency": "5m",
        "start": "2025-10-01T00:00:00Z"
      }
    },
    "DA_Alg_Parameters": [
      {
        "Algorithm": "AlgorithmName",
        "Parameters": {
          "param1": "value1",
          "param2": "value2"
        }
      }
    ]
  }
}
```

## Supported Algorithms

Currently supported algorithms (defined in `Templates/DaConfigTemplate.json`):

- **ZScore**: Statistical anomaly detection
  - Parameters: `threshold` (float), `observed_value` (str)

- **ARMA**: Time series forecasting
  - Parameters: `n_estimators` (int), `contamination` (float)

- **K-means**: Clustering-based anomaly detection
  - Parameters: `n_estimators` (int), `contamination` (float)

## File Locations

- **Server**: `MCP/KB-MCP/server.py`
- **Configurations**: `KB/*.json` (UUID-named files)
- **Templates**: `Templates/DaConfigTemplate.json`
- **Claude Config**: `MCP/claude-config/claude_desktop_config.json`

## Error Handling

The server provides clear error messages for:
- Invalid algorithm requests
- Missing configuration files
- Malformed JSON data
- Template loading failures

## Development

### Adding New Algorithms
1. Update `Templates/DaConfigTemplate.json` with new algorithm definitions
2. The server will automatically recognize them
3. No code changes required

### Modifying Tools
- Tools are defined as functions decorated with `@mcp.tool()`
- Function docstrings are used for AI understanding
- Parameters are automatically validated based on type hints

## Troubleshooting

### Server Won't Start
- Check Python version (3.8+ required)
- Verify all dependencies are installed
- Check file permissions

### Tools Not Available
- Ensure server is running
- Check Claude Desktop configuration
- Verify MCP connection

### Configuration Errors
- Use `list_available_algorithms()` to check supported options
- Validate JSON structure against the schema
- Check file permissions in KB directory

## License

This project is part of the Knowledge Base system for data analytics and monitoring.