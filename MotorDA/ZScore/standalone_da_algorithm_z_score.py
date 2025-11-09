import json
from datetime import timedelta

import numpy as np
import pandas as pd
from pymongo import MongoClient

# === UTILS ===================================================================
def add_workday_flag(df: pd.DataFrame) -> pd.DataFrame:
    # Add a boolean column 'is_workday' based on the weekday of each timestamp.
    # Monday–Friday = True, Saturday–Sunday = False.

    df["is_workday"] = df["timestamp"].dt.dayofweek < 5
    return df

# TODO: this might get resource intensive if time_window is small and df_train is too big.
# === TRAIN BASELINE ==========================================================
def train_baseline(kb_id: str, dimension: str, df_train: pd.DataFrame, field: str, time_window: int = 3600, percentile: float = 99.5):
    """Compute mean, std, and dynamic threshold from training data."""



    """
    #--------------------------DEBUG PRINTS---------------------------------------------------------------------
    # 1. Show how many rows per bucket
    print(df_train["train_window"].value_counts().sort_index())

    # 2. Inspect bucket 0 specifically
    b0 = df_train[df_train["train_window"] == 0]
    print("bucket 0 size:", len(b0))
    print(b0[field].head(20))  # see example values
    print(b0[field].describe())  # count, mean, std, min, max

    # 3. Check for non-numeric / NaN / inf values in bucket 0
    print("isnull:", b0[field].isnull().sum())
    print("nunique:", b0[field].nunique())
    print("unique samples (first 20):", b0[field].unique()[:20])

    # 4. Global check: are values mostly constant?
    print(df_train[field].value_counts().head(10))
    # --------------------------DEBUG PRINTS---------------------------------------------------------------------
    """
    df_train = add_workday_flag(df_train)

    print("Days of week present:", df_train["is_workday"].unique())
    print("Workday counts:", df_train["is_workday"].value_counts())
    print("Timestamps sample:")
    print(df_train.index[:10])

    # Ensure timestamp is datetime
    df_train["timestamp"] = pd.to_datetime(df_train["timestamp"])

    # Use full hour-minute-second conversion to seconds, not just seconds
    df_train["train_window"] = (
                                       (df_train["timestamp"].dt.hour * 3600)
                                       + (df_train["timestamp"].dt.minute * 60)
                                       + df_train["timestamp"].dt.second
                               ) // time_window

    # Initialize buckets for both workday types
    buckets = {"workday": {}, "non_workday": {}}

    # Global fallback
    global_mean = np.mean(df_train[field])
    global_std = np.std(df_train[field]) if np.std(df_train[field]) > 0 else 1e-6

    # Group by is_workday (True/False)
    grouped_by_workday = df_train.groupby("is_workday")

    for is_workday, data in grouped_by_workday:
        grouped_by_time_window = data.groupby("train_window")

        for window_time_window, data_time_window in grouped_by_time_window:
            vals_time_window = data_time_window[field].astype(float).values

            # Calculate mean/std logic
            if len(vals_time_window) < 3:
                mean = global_mean
                std = global_std
            else:
                mean = np.mean(vals_time_window)
                std = np.std(vals_time_window) if np.std(vals_time_window) > 0 else 1e-6

            z_scores = np.abs((vals_time_window - mean) / std)
            threshold = np.percentile(z_scores, percentile)

            label = "workday" if is_workday else "non_workday"
            window_key = str(int(window_time_window))  # force string key for MongoDB

            buckets[label][window_key] = {
                "mean": mean,
                "std": std,
                "threshold": threshold,
                #"timestamp_mean": data_time_window["timestamp"].isoformat(),
                "is_workday": bool(is_workday),
                "data_points": len(vals_time_window),
                "sufficient_data": len(vals_time_window) >= 3
            }

    # Convert all keys to strings (for MongoDB safety)
    def stringify_keys(d):
        if isinstance(d, dict):
            return {str(k): stringify_keys(v) for k, v in d.items()}
        elif isinstance(d, list):
            return [stringify_keys(i) for i in d]
        return d

    baselines_str_keys = stringify_keys(buckets)

    return {
        "kb_id": kb_id,
        "dimension": dimension,
        "time_window": time_window,
        "buckets": baselines_str_keys,
    }


# === ANOMALY DETECTION ======================================================
def detectar_anomalias_df(df: pd.DataFrame, baseline: dict, ventana_minutos: int):
    """Detect anomalies using statistical baseline."""
    if df.empty:
        return []

    field = "value"  # this is harcoded as all the dataframe's have "value" as the name of the observed_value
    mean = baseline["mean"]
    std = baseline["std"]
    threshold = baseline["threshold"]

    # all this sorting thingamabober is just so we can eliminate duplicates and put the timestamp in order
    # print("I am inside standalone z score, and I am printing df: ")
    # print(df)

    df = df.sort_values("timestamp").set_index("timestamp")
    df_resample = df.resample(f"{ventana_minutos}min").sum()

    #  print("I am inside standalone z score, and I am printing RESAMPLED df: ")
    #  print(df_resample)

    anomalies = []
    for ts, fila in df_resample.iterrows():
        val = fila.get(field, 0)

        # acá ocurre la magia, comparamos el valor del df, con el promedio y dividimos por el estándar de los datos pre-entrenados
        z_score = (val - mean) / std
        is_anomaly = abs(z_score) > threshold
        anomalies.append({
            "timestamp": ts.isoformat(),
            "value": float(val),
            "z_score": float(z_score),
            "is_anomaly": bool(is_anomaly),
        })
    return anomalies



def train_baseline_advanced(
    kb_id: str,
    dimension: str,
    df_train: pd.DataFrame,
    field: str,
    time_window: int,
    percentile: float = 99.5,
    min_points: int = 10
):
    """
    Train statistical baselines per (is_workday, time_bucket) pair.
    """

    # Ensure datetime index
    df_train = df_train.copy()
    df_train["timestamp"] = pd.to_datetime(df_train["timestamp"])
    df_train.set_index("timestamp", inplace=True)
    df_train[field] = df_train[field].astype(float)

    # Derive temporal features
    df_train["is_workday"] = df_train.index.dayofweek < 5
    df_train["bucket_index"] = (df_train.index.hour * 3600 + df_train.index.second) // time_window

    buckets = {"workday": {}, "non_workday": {}}

    # Group by (is_workday, bucket)
    for (is_workday, bucket_idx), group in df_train.groupby(["is_workday", "bucket_index"]):
        vals = group[field].values
        n = len(vals)

        if n < min_points:
            buckets["workday" if is_workday else "non_workday"][f"bucket_{bucket_idx}"] = {
                "sufficient_data": False,
                "data_points": n,
            }
            continue

        mean = np.mean(vals)
        std = np.std(vals) if np.std(vals) > 0 else 1e-6
        z_scores = np.abs((vals - mean) / std)
        threshold = np.percentile(z_scores, percentile)
        timestamp_mean = group.index.mean()

        buckets["workday" if is_workday else "non_workday"][f"bucket_{bucket_idx}"] = {
            "mean": float(mean),
            "std": float(std),
            "threshold": float(threshold),
            "timestamp_mean": timestamp_mean.isoformat(),
            "is_workday": bool(is_workday),
            "data_points": int(n),
            "sufficient_data": True,
        }

    return {
        "kb_id": kb_id,
        "dimension": dimension,
        "time_window": time_window,
        "buckets": buckets,
    }