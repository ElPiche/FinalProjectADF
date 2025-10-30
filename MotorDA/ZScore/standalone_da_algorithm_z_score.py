import json
import numpy as np
import pandas as pd
from pymongo import MongoClient


# === CONNECTION ==============================================================
def get_mongo_client(connection_string: str):
    """Return a connected MongoDB client."""
    cli = MongoClient(connection_string, serverSelectionTimeoutMS=5000)
    cli.admin.command("ping")
    return cli


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


# === TRAIN BASELINE ==========================================================
def train_baseline(kb_id: str, dimension: str, df_train: pd.DataFrame, field: str, percentile: float = 99.5):
    """Compute mean, std, and dynamic threshold from training data."""
    vals = df_train[field].astype(float).values
    mean = np.mean(vals)
    std = np.std(vals) if np.std(vals) > 0 else 1e-6
    z_scores = np.abs((vals - mean) / std)
    threshold = np.percentile(z_scores, percentile)
    return {"kb_id": kb_id, "field": dimension, "mean": mean, "std": std, "threshold": threshold}


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


# === SAVE OUTPUT =============================================================
def save_anomalies_json(anomalies: list, baseline: dict, output_path: str):
    """Save anomalies and baseline metadata to a JSON file."""
    output = {
        "metadata": {
            "field": baseline["field"],
            "mean": baseline["mean"],
            "std": baseline["std"],
            "threshold": baseline["threshold"]
        },
        "anomalies": anomalies
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
