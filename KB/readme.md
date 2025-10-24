

# KB Directory - Knowledge Base Configurations

This directory stores the generated Knowledge Base (KB) configuration files created by the KB-MCP (Model Context Protocol) server.

## Purpose

The KB directory serves as the central repository for Data Analytics (DA) algorithm configurations used by the Knowledge Base system. These configurations define how the system monitors, analyzes, and detects anomalies in data streams.

## File Structure

- **UUID-named JSON files** (e.g., `a1b2c3d4-...json`): Individual DA configuration files
  - Each file contains a complete `KB_Config` structure
  - Named with unique UUIDs for identification
  - Generated automatically by the KB-MCP server

- **TestKB.json**: Test/example configuration file
- **da-config.json**: Legacy configuration file (may be deprecated)

## Configuration Content

Each configuration file contains:

```json
{
  "KB_Config": {
    "Id": "unique-uuid",
    "Description": "Human-readable description",
    "Query_Elastic": {
      "query": "Elasticsearch query string"
    },
    "Scheduling": {
      "TrainingPeriod": {
        "from": "start-date",
        "to": "end-date"
      },
      "Detection": {
        "frequency": "check-interval",
        "start": "detection-start-date"
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

## Generation Process

Configurations are created through the KB-MCP server using the `create_da_config` tool, which:

1. Validates algorithm requests against available templates
2. Generates unique UUIDs for each configuration
3. Saves configurations as JSON files in this directory
4. Returns confirmation with file path and content

## Available Algorithms

Currently supported algorithms (loaded from `Templates/DaConfigTemplate.json`):
- **ZScore**: Statistical anomaly detection
- **ARMA**: Time series forecasting
- **K-means**: Clustering-based anomaly detection

## Usage

- Configurations are automatically generated and stored here
- Files should not be manually edited (use KB-MCP tools instead)
- Each configuration represents a unique monitoring setup
- UUID filenames ensure uniqueness and prevent conflicts

## Maintenance

- Old/unused configurations can be archived or removed
- Template updates in `Templates/DaConfigTemplate.json` affect future configurations
- Monitor disk usage as configuration files accumulate over time