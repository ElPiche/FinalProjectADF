# How to Add a New Algorithm

**Last Updated:** December 1, 2025

Adding a new anomaly detection algorithm requires **ONE STEP**:

**Add your class with `@register_algorithm` in `MotorDA/Dispatcher/algorithm_interface.py`**

That's it. The decorator auto-registers it everywhere.

---

## The One Step

Open `MotorDA/Dispatcher/algorithm_interface.py` and add your class:

```python
@register_algorithm
@dataclass
class MyNewAlgorithm:
    """My new algorithm description."""
    
    # Optional: metadata for discovery tools
    __algorithm_meta__ = {
        "description": "What this algorithm does",
        "parameters": ["my_param"],
    }
    
    @property
    def name(self) -> str:
        return "my_algo"  # This is the name used in KB configs
    
    def train(self, values: List[float], percentile: float = 99.5, **kwargs) -> Dict[str, Any]:
        """Train baseline from values. Return JSON-serializable dict."""
        # Your training logic here
        # kwargs contains any custom parameters from KB config metadata
        return {"mean": sum(values)/len(values), "threshold": ...}
    
    def detect(self, value: float, baseline: Dict[str, Any]) -> Dict[str, Any]:
        """Check if value is anomalous. Must return dict with 'is_anomaly' key."""
        return {"is_anomaly": True/False, "score": ...}
    
    def detect_batch(self, values: List[float], baseline: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Detect for multiple values."""
        return [self.detect(v, baseline) for v in values]
```

The `@register_algorithm` decorator automatically:
- Validates your class implements the required methods
- Registers it in `ALGORITHM_REGISTRY`
- Makes it available via `get_algorithm("my_algo")`

## Step 2: Add to KB-MCP Validation

Open `MCP/KB-MCP/models.py` and add your algorithm name:

```python
SUPPORTED_ALGORITHMS: FrozenSet[str] = frozenset({
    "zscore",
    "mock",
    "my_algo",  # Add here
})
```

This allows KB-MCP to validate configs that use your algorithm.

---

## Complete Example: IQR Algorithm

```python
@register_algorithm
@dataclass
class IQRAlgorithm:
    """Interquartile Range anomaly detection."""
    
    __algorithm_meta__ = {
        "description": "IQR-based outlier detection using quartiles",
        "parameters": ["multiplier"],
    }
    
    @property
    def name(self) -> str:
        return "iqr"
    
    def train(self, values: List[float], multiplier: float = 1.5, **_) -> Dict[str, Any]:
        """Compute Q1, Q3, and IQR bounds."""
        sorted_vals = sorted(values)
        n = len(sorted_vals)
        q1 = sorted_vals[n // 4]
        q3 = sorted_vals[3 * n // 4]
        iqr = q3 - q1
        return {
            "q1": q1,
            "q3": q3,
            "lower_bound": q1 - multiplier * iqr,
            "upper_bound": q3 + multiplier * iqr,
        }
    
    def detect(self, value: float, baseline: Dict[str, Any]) -> Dict[str, Any]:
        """Value outside bounds is anomaly."""
        lower = baseline["lower_bound"]
        upper = baseline["upper_bound"]
        is_anomaly = value < lower or value > upper
        return {"is_anomaly": is_anomaly, "value": value}
    
    def detect_batch(self, values: List[float], baseline: Dict[str, Any]) -> List[Dict[str, Any]]:
        return [self.detect(v, baseline) for v in values]
```

Then add `"iqr"` to `SUPPORTED_ALGORITHMS` in `models.py`.

---

## Using Custom Parameters in KB Configs

Parameters from KB config metadata are passed to `train()` as kwargs:

```json
{
  "algorithm": {
    "name": "iqr",
    "parameters": [
      {
        "dimension": "request_count",
        "is_active": true,
        "metadata": [
          {"key": "multiplier", "value": "2.0"}
        ]
      }
    ]
  }
}
```

The `multiplier: 2.0` will be passed to `train(..., multiplier=2.0)`.

---

## Testing Your Algorithm

```python
# Quick test
from MotorDA.Dispatcher.algorithm_interface import get_algorithm

algo = get_algorithm("my_algo")
baseline = algo.train([10, 20, 30, 40, 50])
result = algo.detect(100, baseline)
print(f"Is anomaly: {result['is_anomaly']}")
```

---

## Multi-Dimension Support (Optional)

For algorithms that need to train/detect across multiple dimensions (like Z-Score does), you can add:

```python
def train_multi_dimension(self, observed_values, parameters, percentile=99.5):
    """Train baselines for each dimension in parameters."""
    ...

def detect_multi_dimension(self, observation, baselines, parameters):
    """Detect across all dimensions."""
    ...
```

These are optional - the orchestrator can use the basic `train()`/`detect()` methods with per-dimension calls.

---

## Files Changed

| File | Change |
|------|--------|
| `MotorDA/Dispatcher/algorithm_interface.py` | Add your class with `@register_algorithm` |
| `MCP/KB-MCP/models.py` | Add name to `SUPPORTED_ALGORITHMS` |

**That's all!** The Docker containers will pick up changes on restart.
