import json
from datetime import timedelta

import numpy as np
import pandas as pd
from pymongo import MongoClient


# === CONNECTION ==============================================================
def get_mongo_client(connection_string: str):
    """Return a connected MongoDB client."""
    cli = MongoClient(connection_string, serverSelectionTimeoutMS=5000)
    cli.admin.command("ping")
    return cli


# === UTILS ===================================================================
def add_workday_flag(df: pd.DataFrame) -> pd.DataFrame:
    # Add a boolean column 'is_workday' based on the weekday of each timestamp.
    # Monday–Friday = True, Saturday–Sunday = False.
    df["is_workday"] = df["timestamp"].dt.dayofweek < 5
    return df


# === DATA FETCH ==============================================================
def fetch_logs_from_mongo(connection_string: str, database: str, collection: str,
                          start_iso: str, end_iso: str, observed_fields: list[str]):
    """Fetch data from MongoDB within the given ISO date range and fields."""
    start_dt = pd.to_datetime(start_iso, utc=True)
    end_dt = pd.to_datetime(end_iso, utc=True)

    # picks up all the values from the observed_fields and assigns them to 0 if the field value is not found
    projection = {"_id": 0, "timestamp": "$es_timestamp"}
    for field in observed_fields:
        projection[field] = {"$ifNull": [f"${field}", 0]}

    pipeline = [
        {"$match": {"es_timestamp": {
            "$gte": start_dt.to_pydatetime(), "$lt": end_dt.to_pydatetime()}}},
        {"$project": projection},
        {"$sort": {"timestamp": 1}},
    ]

    # returns a MongoClient connected to connection_string
    with get_mongo_client(connection_string) as cli:
        docs = list(cli[database][collection].aggregate(pipeline))

    if not docs:
        return pd.DataFrame(columns=["timestamp"] + observed_fields)

    df = pd.DataFrame(docs)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    for field in observed_fields:
        df[field] = pd.to_numeric(df[field], errors="coerce").fillna(0)
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

    grouped = df_train.groupby("train_window")
    for window, data in grouped:

        vals = data[field].astype(float).values
        mean = np.mean(vals)
        std = np.std(vals) if np.std(vals) > 0 else 1e-6
        z_scores = np.abs((vals - mean) / std)
        threshold = np.percentile(z_scores, percentile)

        baselines[window] = {
            "mean": mean,
            "std": std,
            "threshold": threshold,            
            "timestamp_mean": data["timestamp"].mean().isoformat(),
            "is_workday": bool(data["is_workday"].mode()[0])  # True if mostly weekdays
        }

    baselines_str_keys = {str(k): v for k, v in baselines.items()}
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
