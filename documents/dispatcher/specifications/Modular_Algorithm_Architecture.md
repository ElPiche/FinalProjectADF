# Modular Algorithm Architecture

> **Status**: ✅ **Production Ready** - Validated December 2025  
> **Last E2E Test**: December 2, 2025 - All components passing

## Overview

The anomaly detection framework uses a **modular, decorator-based algorithm architecture** that allows adding new algorithms with minimal boilerplate. Algorithms are self-contained in their own files and automatically register across the entire stack.

## End-to-End Validation Summary

| Component | Status | Verified |
|-----------|--------|----------|
| Algorithm Registry | ✅ Working | 3 algorithms (zscore, mock, iqr) |
| KB-MCP Dynamic Discovery | ✅ Working | Reads from shared Docker volume |
| Training Pipeline | ✅ Working | IQR trained 1440 observations |
| Detection Pipeline | ✅ Working | Anomalies detected correctly |
| Insights API Integration | ✅ Working | DocumentDto format with algorithm_details |
| Email Notifications | ✅ Working | Rate-limited delivery confirmed |
| Elasticsearch Storage | ✅ Working | Full algorithm details preserved |
| Kibana Data Views | ✅ Working | Auto-created for anomaly index |

## Key Design Principles

1. **Single Point of Registration**: Use `@register_algorithm` decorator - nothing else needed
2. **Self-Contained Files**: Each algorithm lives in its own file with all logic
3. **Automatic Discovery**: KB-MCP dynamically discovers available algorithms
4. **No Cross-Container Imports**: Uses shared Docker volume for decoupling

## Adding a New Algorithm

### Step 1: Create the Algorithm File

Create a new file in `MotorDA/Dispatcher/algorithms/`:

```python
# algorithms/my_algo.py
from dataclasses import dataclass
from typing import Dict, Any, List
from ..algorithm_interface import register_algorithm

@register_algorithm
@dataclass
class MyAlgorithm:
    """Description of your algorithm."""
    
    __algorithm_meta__ = {
        "description": "Human-readable description",
        "best_for": "When to use this algorithm",
        "parameters": ["param1", "param2"],  # KB-MCP shows these
    }
    
    @property
    def name(self) -> str:
        return "my_algo"  # Must be lowercase
    
    def train(self, values: List[float], **kwargs) -> Dict[str, Any]:
        """Train on a list of values, return baseline dict."""
        # Your training logic here
        return {"baseline": ...}
    
    def train_multi_dimension(
        self,
        observed_values: List[Dict[str, Any]],
        parameters: List[Dict[str, Any]],
        **_  # Accept extra kwargs for compatibility
    ) -> Dict[str, Any]:
        """Train baselines for multiple dimensions."""
        result = {}
        for param in parameters:
            dimension = param.get("dimension")
            values = [obs.get(dimension) for obs in observed_values if obs.get(dimension)]
            result[dimension] = self.train(values)
        return result
    
    def detect(self, value: float, baseline: Dict[str, Any]) -> Dict[str, Any]:
        """Check if a single value is anomalous."""
        return {"is_anomaly": False, "value": value}
    
    def detect_multi_dimension(
        self,
        observation: Dict[str, Any],
        baselines: Dict[str, Any],
        parameters: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Check if observation is anomalous across dimensions."""
        dimension_results = {}
        is_anomaly = False
        for param in parameters:
            dim = param.get("dimension")
            baseline = baselines.get(dim)
            if baseline and observation.get(dim) is not None:
                result = self.detect(float(observation[dim]), baseline)
                dimension_results[dim] = result
                if result.get("is_anomaly"):
                    is_anomaly = True
        return {"is_anomaly": is_anomaly, "dimension_results": dimension_results}
```

### Step 2: Import in `__init__.py`

Add one line to `algorithms/__init__.py`:

```python
from .my_algo import MyAlgorithm
```

### Step 3: Rebuild Containers

```bash
docker-compose build dispatcher
docker-compose up -d dispatcher
```

That's it! The algorithm is now:
- Available in KB-MCP's `list_available_algorithms` tool
- Validated when creating new KB configs
- Usable in training and detection

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                           DA-Dispatcher                              │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │ algorithms/                                                    │  │
│  │   __init__.py  ← imports all algorithms                       │  │
│  │   zscore.py    ← @register_algorithm                          │  │
│  │   iqr.py       ← @register_algorithm                          │  │
│  │   mock.py      ← @register_algorithm                          │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                │                                     │
│                                ▼                                     │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │ algorithm_interface.py                                         │  │
│  │   ALGORITHM_REGISTRY = {}     ← populated by decorator         │  │
│  │   @register_algorithm         ← writes to registry + exports   │  │
│  │   export_registry()           ← writes /app/registry/algorithms.json │
│  └───────────────────────────────────────────────────────────────┘  │
│                                │                                     │
└────────────────────────────────│─────────────────────────────────────┘
                                 │ (write)
                     ┌───────────▼───────────┐
                     │ Shared Docker Volume  │
                     │ algorithm_registry    │
                     │                       │
                     │ /app/registry/        │
                     │   algorithms.json     │
                     └───────────┬───────────┘
                                 │ (read)
┌────────────────────────────────│─────────────────────────────────────┐
│                           KB-MCP                                     │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │ models.py                                                      │  │
│  │   get_supported_algorithms()  ← reads /app/registry/algorithms.json │
│  │   SUPPORTED_ALGORITHMS        ← dynamic set for validation    │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                │                                     │
│                                ▼                                     │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │ mcp_tools.py                                                   │  │
│  │   list_available_algorithms()  ← shows all registered algos   │  │
│  │   create_da_config()           ← validates algorithm name     │  │
│  └───────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
```

## Available Algorithms

### Z-Score (`zscore`)
Statistical anomaly detection based on standard deviations from mean.
- **Best for**: Stationary time series with approximately normal distribution
- **Parameters**: `percentile`, `min_points`

### IQR (`iqr`)
Interquartile Range outlier detection using quartiles.
- **Best for**: Data with outliers, non-normal distributions, or when Z-Score is too sensitive
- **Parameters**: `multiplier` (default 1.5, use 3.0 for extreme outliers only)
- **Bounds**: Q1 - multiplier*IQR to Q3 + multiplier*IQR

### Mock (`mock`)
Simple threshold-based detection for testing.
- **Best for**: Testing and demonstration
- **Parameters**: `percentile`

## Algorithm Registry Format

The shared volume contains `algorithms.json`:

```json
{
  "zscore": {
    "name": "zscore",
    "description": "Z-Score statistical anomaly detection...",
    "best_for": "Stationary time series...",
    "parameters": ["percentile", "min_points"]
  },
  "iqr": {
    "name": "iqr",
    "description": "IQR-based outlier detection...",
    "best_for": "Data with outliers...",
    "parameters": ["multiplier"]
  }
}
```

## Docker Configuration

```yaml
# docker-compose.yml
volumes:
  algorithm_registry:  # Shared volume for algorithm discovery

services:
  dispatcher:
    volumes:
      - algorithm_registry:/app/registry  # Write access
    environment:
      - ALGORITHM_REGISTRY_PATH=/app/registry/algorithms.json

  kb-mcp:
    volumes:
      - algorithm_registry:/app/registry:ro  # Read-only access
    environment:
      - ALGORITHM_REGISTRY_PATH=/app/registry/algorithms.json
```

## Testing a New Algorithm

1. **List available algorithms**:
   Use KB-MCP's `list_available_algorithms` tool

2. **Test SQL query**:
   ```
   elasticsearch_sql: SELECT ... FROM "index" WHERE ...
   ```

3. **Create KB config**:
   ```json
   {
     "algorithm": {
       "name": "my_algo",
       "parameters": [
         {"dimension": "column_name", "is_active": true}
       ]
     }
   }
   ```

4. **Trigger training**:
   Training auto-triggers when `training_config.is_trained` becomes `false`
   Trained models are saved to `trained_models` collection (per spec §3.4)

5. **Check dispatcher logs**:
   ```bash
   docker logs da-dispatcher --tail 50
   ```

## Troubleshooting

### Algorithm not showing in KB-MCP
1. Check dispatcher started: `docker logs da-dispatcher | head`
2. Verify export: `docker exec kb-mcp cat /app/registry/algorithms.json`
3. Restart KB-MCP: `docker-compose restart kb-mcp`

### Training fails with missing method
Ensure your algorithm implements:
- `train_multi_dimension(observed_values, parameters, **kwargs)`
- Accept `**kwargs` to ignore orchestrator-specific parameters

### Detection fails
Ensure your algorithm implements:
- `detect_multi_dimension(observation, baselines, parameters)`
- Return `{"is_anomaly": bool, "dimensions": {...}}` (note: key is `dimensions`, not `dimension_results`)

---

## E2E Test Results (December 2025)

### Test Configuration

```json
{
  "name": "iqr-email-e2e-test",
  "algorithm": {
    "name": "iqr",
    "parameters": [
      {"dimension": "error_5xx_count", "is_active": true},
      {"dimension": "avg_response_time", "is_active": true}
    ]
  },
  "anomaly_config": {
    "user_emails": ["im.elinzar@gmail.com"]
  },
  "detection_frequency": "*/2 * * * *",
  "source_index": "ecommerce-logs"
}
```

### IQR Training Results

| Dimension | Q1 | Q3 | IQR | Lower Bound | Upper Bound |
|-----------|-----|-----|-----|-------------|-------------|
| error_5xx_count | 3.0 | 14.0 | 11.0 | -13.5 | **30.5** |
| avg_response_time | 396.75 | 553.33 | 156.57 | 161.89 | 788.19 |

### Anomalies Detected

Values like `error_5xx_count = 10936` correctly flagged as anomalies (exceeds upper bound of 30.5).

### Elasticsearch Document Structure

```json
{
  "algorithm": "iqr",
  "metric": "error_5xx_count",
  "value": 10936.0,
  "kbName": "iqr-email-e2e-test",
  "email": "im.elinzar@gmail.com",
  "bucket_key": "global_default",
  "algorithm_details": {
    "error_5xx_count": {
      "is_anomaly": true,
      "value": 10936.0,
      "lower_bound": -13.5,
      "upper_bound": 30.5,
      "distance_from_bounds": 10905.5,
      "q1": 3.0,
      "q3": 14.0
    },
    "avg_response_time": {
      "is_anomaly": false,
      "value": 479.38,
      "lower_bound": 161.89,
      "upper_bound": 788.19,
      "distance_from_bounds": 0.0,
      "q1": 396.75,
      "q3": 553.33
    }
  }
}
```

### Email Notification Log

```
SUCCESS: Email sent successfully to im.elinzar@gmail.com
Template variables: kbName=iqr-email-e2e-test, metric=error_5xx_count, value=1174.0
```

Rate limiting confirmed working - subsequent emails blocked by cooldown.
