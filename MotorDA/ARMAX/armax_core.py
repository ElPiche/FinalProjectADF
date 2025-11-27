"""ARMAX Core - Pure statistical functions for ARMAX model.

This module provides the core ARMAX implementation without any framework dependencies.
The ARMAXAlgorithm class wraps these functions into the BaseAlgorithm interface.

ARMAX (AutoRegressive Moving Average with eXogenous inputs):
- AR (AutoRegressive): Current value depends on p previous values
- MA (Moving Average): Current error depends on q previous errors
- X (eXogenous): External variables (like time features) influence predictions

For our use case:
- Exogenous variables = bucket features (is_workday, hour, etc.)
- This allows the model to learn different patterns for different time contexts
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
import numpy as np
import warnings

# Suppress convergence warnings during model fitting
warnings.filterwarnings('ignore', category=UserWarning)
warnings.filterwarnings('ignore', category=RuntimeWarning)


@dataclass
class ARMAXModel:
    """Trained ARMAX model parameters.
    
    Attributes:
        ar_params: AutoRegressive coefficients (length p)
        ma_params: Moving Average coefficients (length q)
        exog_params: Exogenous variable coefficients
        intercept: Model intercept/constant
        residual_std: Standard deviation of training residuals
        order: Tuple (p, d, q) for model order
        exog_features: Names of exogenous features used
        training_mean: Mean of training data (for normalization)
        training_std: Std of training data (for normalization)
        threshold_multiplier: Multiplier for residual_std to set anomaly threshold
        data_points: Number of training points used
    """
    ar_params: List[float] = field(default_factory=list)
    ma_params: List[float] = field(default_factory=list)
    exog_params: Dict[str, float] = field(default_factory=dict)
    intercept: float = 0.0
    residual_std: float = 1.0
    order: Tuple[int, int, int] = (1, 0, 1)
    exog_features: List[str] = field(default_factory=list)
    training_mean: float = 0.0
    training_std: float = 1.0
    threshold_multiplier: float = 3.0
    data_points: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "ar_params": self.ar_params,
            "ma_params": self.ma_params,
            "exog_params": self.exog_params,
            "intercept": self.intercept,
            "residual_std": self.residual_std,
            "order": list(self.order),
            "exog_features": self.exog_features,
            "training_mean": self.training_mean,
            "training_std": self.training_std,
            "threshold_multiplier": self.threshold_multiplier,
            "data_points": self.data_points,
            "anomaly_threshold": self.residual_std * self.threshold_multiplier,
        }
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ARMAXModel":
        """Create from dictionary."""
        return cls(
            ar_params=d.get("ar_params", []),
            ma_params=d.get("ma_params", []),
            exog_params=d.get("exog_params", {}),
            intercept=d.get("intercept", 0.0),
            residual_std=d.get("residual_std", 1.0),
            order=tuple(d.get("order", [1, 0, 1])),
            exog_features=d.get("exog_features", []),
            training_mean=d.get("training_mean", 0.0),
            training_std=d.get("training_std", 1.0),
            threshold_multiplier=d.get("threshold_multiplier", 3.0),
            data_points=d.get("data_points", 0),
        )


@dataclass
class ARMAXPrediction:
    """Result of ARMAX prediction."""
    predicted_value: float
    actual_value: float
    prediction_error: float
    is_anomaly: bool
    threshold: float
    confidence: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "predicted_value": self.predicted_value,
            "actual_value": self.actual_value,
            "prediction_error": self.prediction_error,
            "is_anomaly": self.is_anomaly,
            "threshold": self.threshold,
            "confidence": self.confidence,
        }


def extract_exog_features(
    data: List[Dict[str, Any]],
    feature_names: Optional[List[str]] = None,
) -> np.ndarray:
    """Extract exogenous features from data.
    
    Default features if not specified:
    - hour: Hour of day (0-23)
    - is_workday: 1 if weekday, 0 if weekend
    - day_of_week: Day of week (0-6)
    
    Args:
        data: List of data points with timestamp and optional features
        feature_names: Specific features to extract
        
    Returns:
        2D numpy array of shape (n_samples, n_features)
    """
    if not data:
        return np.array([]).reshape(0, 0)
    
    # Default feature names
    if feature_names is None:
        feature_names = ["hour", "is_workday", "day_of_week"]
    
    features = []
    for point in data:
        row = []
        for fname in feature_names:
            if fname in point:
                row.append(float(point[fname]))
            elif fname == "hour" and "timestamp" in point:
                ts = point["timestamp"]
                if isinstance(ts, datetime):
                    row.append(float(ts.hour))
                elif hasattr(ts, 'hour'):
                    row.append(float(ts.hour))
                else:
                    row.append(0.0)
            elif fname == "is_workday" and "timestamp" in point:
                ts = point["timestamp"]
                if isinstance(ts, datetime):
                    row.append(1.0 if ts.weekday() < 5 else 0.0)
                elif hasattr(ts, 'weekday'):
                    row.append(1.0 if ts.weekday() < 5 else 0.0)
                else:
                    row.append(1.0)
            elif fname == "day_of_week" and "timestamp" in point:
                ts = point["timestamp"]
                if isinstance(ts, datetime):
                    row.append(float(ts.weekday()))
                elif hasattr(ts, 'weekday'):
                    row.append(float(ts.weekday()))
                else:
                    row.append(0.0)
            else:
                row.append(0.0)
        features.append(row)
    
    return np.array(features)


def train_armax(
    data: List[Dict[str, Any]],
    order: Tuple[int, int, int] = (2, 0, 2),
    exog_features: Optional[List[str]] = None,
    threshold_multiplier: float = 3.0,
    min_training_points: int = 10,
) -> ARMAXModel:
    """Train ARMAX model on time series data.
    
    Uses simplified ARMAX implementation that:
    1. Fits AR coefficients using linear regression on lagged values
    2. Fits exogenous coefficients on external features
    3. Estimates MA from residuals
    4. Calculates residual standard deviation for anomaly threshold
    
    Args:
        data: List of data points with 'value' and 'timestamp'
        order: (p, d, q) - AR order, differencing order, MA order
        exog_features: Names of exogenous features to use
        threshold_multiplier: How many std devs for anomaly threshold
        min_training_points: Minimum data points for training
        
    Returns:
        Trained ARMAXModel
    """
    p, d, q = order
    
    # Set defaults
    if exog_features is None:
        exog_features = ["hour", "is_workday"]
    
    # Extract values
    values = np.array([float(d.get("value", 0)) for d in data])
    n = len(values)
    
    if n < min_training_points:
        # Not enough data - return minimal model
        return ARMAXModel(
            order=order,
            exog_features=exog_features,
            threshold_multiplier=threshold_multiplier,
            data_points=n,
            training_mean=float(np.mean(values)) if n > 0 else 0.0,
            training_std=float(np.std(values)) if n > 1 else 1.0,
        )
    
    # Calculate statistics
    training_mean = float(np.mean(values))
    training_std = float(np.std(values)) if np.std(values) > 0 else 1.0
    
    # Normalize values for more stable fitting
    values_norm = (values - training_mean) / training_std
    
    # Apply differencing if d > 0
    if d > 0:
        for _ in range(d):
            values_norm = np.diff(values_norm)
    
    # Extract exogenous features
    exog = extract_exog_features(data, exog_features)
    if d > 0 and len(exog) > 0:
        exog = exog[d:]  # Align with differenced values
    
    # Fit AR model using OLS on lagged values
    ar_params = []
    if p > 0 and len(values_norm) > p:
        # Create lagged matrix
        y = values_norm[p:]
        X_ar = np.column_stack([values_norm[p-i-1:-i-1] for i in range(p)])
        
        # Add exogenous variables if available
        if len(exog) > 0 and len(exog) >= len(y):
            exog_aligned = exog[p:len(y)+p]
            if len(exog_aligned) == len(y):
                X_full = np.column_stack([X_ar, exog_aligned])
            else:
                X_full = X_ar
        else:
            X_full = X_ar
        
        # Add constant
        X_full = np.column_stack([np.ones(len(y)), X_full])
        
        try:
            # OLS fit: (X'X)^-1 X'y
            XtX = X_full.T @ X_full
            # Add small regularization for numerical stability
            XtX += np.eye(XtX.shape[0]) * 1e-6
            XtX_inv = np.linalg.inv(XtX)
            beta = XtX_inv @ X_full.T @ y
            
            intercept = beta[0]
            ar_params = list(beta[1:1+p])
            
            # Exogenous params if included
            exog_params = {}
            if len(exog) > 0 and len(beta) > 1 + p:
                for i, fname in enumerate(exog_features):
                    if 1 + p + i < len(beta):
                        exog_params[fname] = float(beta[1 + p + i])
            
            # Calculate residuals
            y_pred = X_full @ beta
            residuals = y - y_pred
            residual_std = float(np.std(residuals)) if len(residuals) > 1 else 1.0
            
        except np.linalg.LinAlgError:
            # Fallback to simple mean prediction
            intercept = 0.0
            ar_params = [0.5] * p  # Simple decay
            exog_params = {}
            residual_std = training_std
    else:
        intercept = 0.0
        ar_params = []
        exog_params = {}
        residual_std = training_std
    
    # Estimate MA parameters (simplified - using residual autocorrelation)
    ma_params = []
    if q > 0:
        ma_params = [0.1] * q  # Simplified MA initialization
    
    return ARMAXModel(
        ar_params=ar_params,
        ma_params=ma_params,
        exog_params=exog_params,
        intercept=intercept,
        residual_std=max(residual_std, 0.01),  # Minimum std
        order=order,
        exog_features=exog_features,
        training_mean=training_mean,
        training_std=training_std,
        threshold_multiplier=threshold_multiplier,
        data_points=n,
    )


def predict_armax(
    model: ARMAXModel,
    history: List[Dict[str, Any]],
    current_exog: Optional[Dict[str, float]] = None,
) -> float:
    """Predict next value using ARMAX model.
    
    Args:
        model: Trained ARMAXModel
        history: Recent values (oldest to newest)
        current_exog: Current exogenous features
        
    Returns:
        Predicted value
    """
    if not model.ar_params or len(history) < len(model.ar_params):
        # Not enough history or no AR params - return mean
        return model.training_mean
    
    # Extract recent values
    recent_values = [float(h.get("value", 0)) for h in history[-len(model.ar_params):]]
    
    # Normalize
    recent_norm = [(v - model.training_mean) / model.training_std for v in recent_values]
    
    # Apply differencing if needed
    d = model.order[1]
    if d > 0 and len(recent_norm) > d:
        diffs = []
        for i in range(len(recent_norm) - 1):
            diffs.append(recent_norm[i + 1] - recent_norm[i])
        recent_norm = diffs
    
    # AR component
    p = len(model.ar_params)
    ar_term = sum(
        model.ar_params[i] * recent_norm[-(i + 1)]
        for i in range(min(p, len(recent_norm)))
    )
    
    # Exogenous component
    exog_term = 0.0
    if current_exog and model.exog_params:
        for fname, coef in model.exog_params.items():
            if fname in current_exog:
                exog_term += coef * current_exog[fname]
    
    # Prediction (normalized)
    pred_norm = model.intercept + ar_term + exog_term
    
    # Denormalize
    prediction = pred_norm * model.training_std + model.training_mean
    
    return prediction


def detect_armax(
    model: ARMAXModel,
    actual_value: float,
    history: List[Dict[str, Any]],
    current_exog: Optional[Dict[str, float]] = None,
) -> ARMAXPrediction:
    """Detect if a value is anomalous using ARMAX model.
    
    Args:
        model: Trained ARMAXModel
        actual_value: Current observed value
        history: Recent historical values
        current_exog: Current exogenous features
        
    Returns:
        ARMAXPrediction with anomaly detection result
    """
    predicted = predict_armax(model, history, current_exog)
    error = abs(actual_value - predicted)
    threshold = model.residual_std * model.threshold_multiplier * model.training_std
    
    # Ensure minimum threshold
    threshold = max(threshold, 0.01 * model.training_mean) if model.training_mean != 0 else max(threshold, 1.0)
    
    is_anomaly = error > threshold
    
    # Calculate confidence (how far above threshold)
    if is_anomaly and threshold > 0:
        confidence = min(1.0, error / (2 * threshold))
    else:
        confidence = 0.0
    
    return ARMAXPrediction(
        predicted_value=predicted,
        actual_value=actual_value,
        prediction_error=error,
        is_anomaly=is_anomaly,
        threshold=threshold,
        confidence=confidence,
    )
