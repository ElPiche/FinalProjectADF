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

    # Add workday flag
    df_train = add_workday_flag(df_train)

    # this picks up the hours of the timestamp, turns it into minutes, sum the current minute and divide by time_window
    # which creates a lil logical division exactly the way we want to bucket
    df_train["train_window"] = (
            (df_train["timestamp"].dt.hour * 3600 + df_train["timestamp"].dt.second)
            // time_window
    )

    baselines = {}

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
    # Global statistics for fallback
    global_mean = np.mean(df_train[field])
    global_std = np.std(df_train[field]) if np.std(df_train[field]) > 0 else 1e-6

    # Group by both time bucket and workday/weekend
    grouped = df_train.groupby(["train_window", "is_workday"])

    for (window, is_workday), data in grouped:
        vals = data[field].astype(float).values

        if len(vals) < 3:
            # ---- INSUFFICIENT DATA ----
            color = "\033[95m" if is_workday else "\033[96m"
            label = "WORKDAY" if is_workday else "WEEKEND"
            print(f"{color} -----------------------------------------------------------------  \033[0m")
            print(f"{color} TRAINING Z_SCORE WITH GLOBAL DISTRIBUTION DUE TO LOW DATA AMOUNT ({label}) \033[0m")

            mean = global_mean
            std = global_std
            z_scores = np.abs((vals - mean) / std)
            threshold = np.percentile(z_scores, percentile)

            print(f"{color} -----------------------------------------------------------------  \033[0m")
        else:
            # ---- SUFFICIENT DATA ----
            color = "\033[92m" if is_workday else "\033[94m"
            label = "WORKDAY" if is_workday else "WEEKEND"
            print(f"{color} -----------------------------------------------------------------  \033[0m")
            print(f"{color} TRAINING Z_SCORE WITH ENOUGH BUCKETED DATA ({label}) \033[0m")

            mean = np.mean(vals)
            std = np.std(vals) if np.std(vals) > 0 else 1e-6
            z_scores = np.abs((vals - mean) / std)
            threshold = np.percentile(z_scores, percentile)

            print(f"{color} -----------------------------------------------------------------  \033[0m")

        # Store using composite key: "workday:window"
        key = f"{is_workday}:{window}"
        baselines[key] = {
            "mean": mean,
            "std": std,
            "threshold": threshold,
            "timestamp_mean": data["timestamp"].mean().isoformat(),
            "is_workday": bool(is_workday),
            "data_points": len(vals),
            "sufficient_data": len(vals) >= 3
        }

    return {
        "kb_id": kb_id,
        "dimension": dimension,
        "time_window": time_window,
        "buckets": baselines,
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
