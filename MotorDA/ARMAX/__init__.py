"""ARMAX Algorithm Package.

ARMAX (AutoRegressive Moving Average with eXogenous inputs) is a time-series
forecasting model that extends ARMA with external variables like time-context
bucket features.

For anomaly detection:
- Train on historical time-series data
- Model learns temporal patterns and relationships
- At detection, predict next value and compare to actual
- Large prediction errors indicate anomalies

This is a SERIES mode algorithm with FEATURE bucket mode.
"""

from .algorithm import ARMAXAlgorithm
from .armax_core import train_armax, predict_armax, ARMAXModel

__all__ = ["ARMAXAlgorithm", "train_armax", "predict_armax", "ARMAXModel"]
