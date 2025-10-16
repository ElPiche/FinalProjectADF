import json
import os
import random
from datetime import datetime, timedelta
from pathlib import Path
import numpy as np
import pandas as pd

from pymongo import MongoClient, errors

# Default connection settings
DEFAULT_CONNECTION_STRING = "mongodb://admin:1q2w3E%2A@localhost:27017/?authSource=admin"
DEFAULT_DATABASE = "logsdb"

# Parámetros de simulación
### Tomando un caso en el que el horario laboral es de 9 a 17
CANTIDAD_REGISTROS = 300        # 300 registros va desde las 8 de la mañana hasta las 13
PROBABILIDAD_ANOMALIA = 0.05

MEDIA_HTTP_200_LABORAL = 100
MEDIA_HTTP_200_NO_LABORAL = 15

BINOMIAL_INTENTOS_HTTP_500 = 5
PROBABILIDAD_HTTP_500_LABORAL = 0.01
PROBABILIDAD_HTTP_500_NO_LABORAL = 0.02

VENTANAS_MINUTOS = [60]     # [5, 15, 60] minutos

# Umbral de detección de anomalías
UMBRAL_Z_SCORE = 3          # |z| > 3 se considera anómalo

# Config directory
CONFIG_DIR = Path(__file__).parent / "MotorDAConfig"

def get_mongo_client():
    print("Establishing connection with MongoDB")
    cli = MongoClient(CONNECTION_STRING, serverSelectionTimeoutMS=5000)
    # valida conexión inmediatamente (si falla, levanta excepción clara)
    cli.admin.command("ping")
    return cli

def get_mongo_client(connection_string=None):
    print("Establishing connection with MongoDB")
    conn_str = connection_string or DEFAULT_CONNECTION_STRING
    cli = MongoClient(conn_str, serverSelectionTimeoutMS=5000)
    # valida conexión inmediatamente (si falla, levanta excepción clara)
    cli.admin.command("ping")
    return cli

def fetch_logs_from_mongo(connection_string: str, database: str, collection: str, start_iso: str, end_iso: str, observed_fields: list = None):

    print(f"Starting data collector from MongoDB for collection {collection}")

    # Parseo robusto de fechas (si traen 'Z' las dejamos en UTC)
    start_dt = pd.to_datetime(start_iso, utc=True)
    end_dt   = pd.to_datetime(end_iso, utc=True)

    # Build projection based on observed fields or use defaults
    if observed_fields:
        projection = {"_id": 0, "timestamp": "$es_timestamp"}
        for field in observed_fields:
            projection[field] = {"$ifNull": [f"${field}", 0]}
    else:
        # Default projection for backward compatibility
        projection = {
            "_id": 0,
            "timestamp": "$es_timestamp",
            "status_code_200": {"$ifNull": ["$status_code_200_counter", 0]},
            "status_code_500": {"$ifNull": ["$status_code_5xx_counter", 0]}
        }

    pipeline = [
        {
            "$match": {
                "es_timestamp": {"$gte": start_dt.to_pydatetime(), "$lt": end_dt.to_pydatetime()}
            }
        },
        {"$project": projection},
        {"$sort": {"timestamp": 1}}
    ]

    print("Attempting connection")

    with get_mongo_client(connection_string) as cli:
        col = cli[database][collection]
        docs = list(col.aggregate(pipeline))

    print("Connection established")

    if not docs:
        print(f"Warning: No documents found in the given range for collection {collection}.")
        columns = ["timestamp"] + (observed_fields or ["status_code_200", "status_code_500"])
        return pd.DataFrame(columns=columns)

    df = pd.DataFrame(docs)
    # Garantizamos dtype correcto
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

    # Convert observed fields to numeric
    fields_to_convert = observed_fields or ["status_code_200", "status_code_500"]
    for field in fields_to_convert:
        if field in df.columns:
            df[field] = pd.to_numeric(df[field], errors="coerce").fillna(0).astype(int)

    return df

def detectar_anomalias_df(df: pd.DataFrame, observed_fields: list = None, threshold: float = UMBRAL_Z_SCORE):

    print("Iniciando detector de anomalias")

    if df.empty:
        print("No data to analyze.")
        return

    df = df.copy()
    df = df.sort_values("timestamp")
    df = df.set_index("timestamp")

    # Determine which fields to analyze
    fields_to_analyze = observed_fields or ["status_code_200", "status_code_500"]
    available_fields = [f for f in fields_to_analyze if f in df.columns]

    if not available_fields:
        print(f"Warning: None of the observed fields {fields_to_analyze} are available in the data.")
        return

    # Si los datos ya vienen agregados por hora, resample no debería cambiar nada para 60min,
    # pero igual lo dejamos por si querés ventanas distintas (p.ej. 15min)
    for ventana_minutos in VENTANAS_MINUTOS:
        print(f"\n[*] Analyzing window of {ventana_minutos} minutes...")
        # sum = agregamos por ventana
        df_resample = df.resample(f"{ventana_minutos}min").sum()

        # Estadísticos globales de referencia
        medias = df_resample[available_fields].mean()
        desvios = df_resample[available_fields].std().replace(0, 1)  # evitar 0

        for ts, fila in df_resample.iterrows():
            ts_fin = ts + timedelta(minutes=ventana_minutos - 1)

            print(f"\n[*] {ts} -> {ts_fin}")

            anomalies_found = False
            for field in available_fields:
                val = fila.get(field, 0)
                media = medias[field]
                desv = desvios[field]
                z_score = (val - media) / desv

                print(f"  {field}: {val} (mean={media:.2f}, std={desv:.2f}, z={z_score:.2f})")

                if abs(z_score) > threshold:
                    print(f"  [!] Anomaly in {field} (z={z_score:.2f})")
                    anomalies_found = True

            if not anomalies_found:
                print("  [+] No anomalies detected in this window")


def load_da_configs():
    """Load all DA configuration files"""
    configs = []
    if CONFIG_DIR.exists():
        for file in CONFIG_DIR.iterdir():
            if file.suffix.lower() == ".json" and file.name != "motorDAConfigTest.json":
                try:
                    with open(file, "r", encoding="utf-8") as f:
                        config = json.load(f)
                    configs.append(config)
                    print(f"Loaded DA config: {file.name}")
                except Exception as e:
                    print(f"Error loading DA config {file.name}: {e}")
    else:
        print(f"Config directory {CONFIG_DIR} does not exist")
    return configs

def process_da_config(config: dict):
    """Process a single DA configuration"""
    try:
        # Extract connection info
        conn_config = config.get("Connection_Config", {})
        connection_string = conn_config.get("Url", DEFAULT_CONNECTION_STRING)
        database = conn_config.get("Database", DEFAULT_DATABASE)
        collection = conn_config.get("Collection", "")

        if not collection:
            print("⚠️ No collection specified in config, skipping")
            return

        # Extract scheduling info
        scheduling = config.get("Scheduling", {})
        training_period = scheduling.get("TrainingPeriod", {})
        detection = scheduling.get("Detection", {})

        start_iso = training_period.get("from", "")
        end_iso = training_period.get("to", "")

        if not start_iso or not end_iso:
            print(f"⚠️ Missing training period dates for collection {collection}, skipping")
            return

        # Extract DA algorithm parameters
        da_config = config.get("DA_Config", {})
        algorithms = da_config.get("DA_Alg_Parameters", [])

        if not algorithms:
            print(f"⚠️ No algorithms specified for collection {collection}, skipping")
            return

        # For now, process the first ZScore algorithm
        zscore_alg = None
        for alg in algorithms:
            if alg.get("Algorithm") == "ZScore":
                zscore_alg = alg
                break

        if not zscore_alg:
            print(f"⚠️ No ZScore algorithm found for collection {collection}, skipping")
            return

        # Extract observed field and threshold
        params = zscore_alg.get("Parameters", {})
        observed_value = params.get("observed_value", "")
        threshold = params.get("threshold", UMBRAL_Z_SCORE)

        if not observed_value:
            print(f"⚠️ No observed_value specified for collection {collection}, using defaults")
            observed_fields = None
        else:
            observed_fields = [observed_value]

        print(f"\n[*] Processing KB: {config.get('Meta', {}).get('Description', collection)}")
        print(f"Collection: {collection}")
        print(f"Training period: {start_iso} to {end_iso}")
        print(f"Observed fields: {observed_fields or ['status_code_200', 'status_code_500']}")

        # Fetch data
        df = fetch_logs_from_mongo(connection_string, database, collection, start_iso, end_iso, observed_fields)

        # Detect anomalies
        detectar_anomalias_df(df, observed_fields, threshold)

    except Exception as e:
        print(f"Error processing DA config: {e}")

if __name__ == "__main__":
    print("[+] Starting MotorDA Anomaly Detection")
    configs = load_da_configs()

    if not configs:
        print("No DA configurations found. Using legacy mode...")
        # Fallback to legacy behavior
        df = fetch_logs_from_mongo(DEFAULT_CONNECTION_STRING, DEFAULT_DATABASE, "grouped_response_code_v2", "2025-10-25T00:00:00Z", "2025-11-01T00:00:00Z")
        detectar_anomalias_df(df)
    else:
        print(f"Found {len(configs)} DA configurations")
        for config in configs:
            process_da_config(config)

    print("[+] MotorDA processing completed")
