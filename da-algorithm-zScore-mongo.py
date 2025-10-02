import json
import random
from datetime import datetime, timedelta
import numpy as np
import pandas as pd

from pymongo import MongoClient, errors

CONNECTION_STRING = "mongodb://admin:1q2w3E%2A@localhost:27017/?authSource=admin"
DATABASE = "logsdb"
COLLECTION = "grouped_response_code_v2"

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

START_ISO = "2025-10-25T00:00:00Z"
END_ISO   = "2025-11-01T00:00:00Z"

def get_mongo_client():
    print("Estableciendo conexión con MongoDb")
    cli = MongoClient(CONNECTION_STRING, serverSelectionTimeoutMS=5000)
    # valida conexión inmediatamente (si falla, levanta excepción clara)
    cli.admin.command("ping")
    return cli

def fetch_logs_from_mongo(start_iso: str, end_iso: str):
    
    print("Iniciando recolector de datos de mongoDB")
    
    # Parseo robusto de fechas (si traen 'Z' las dejamos en UTC)
    start_dt = pd.to_datetime(start_iso, utc=True)
    end_dt   = pd.to_datetime(end_iso, utc=True)

    pipeline = [
        {
            "$match": {
                "es_timestamp": {"$gte": start_dt.to_pydatetime(), "$lt": end_dt.to_pydatetime()}
            }
        },
        {
            # Aseguramos valores numéricos aunque el campo no exista en algún doc
            "$project": {
                "_id": 0,
                "timestamp": "$es_timestamp",
                "status_code_200": {"$ifNull": ["$status_code_200_counter", 0]},
                "status_code_500": {"$ifNull": ["$status_code_5xx_counter", 0]}
            }
        },
        {"$sort": {"timestamp": 1}}
    ]

    print("Intentando conexión")

    with get_mongo_client() as cli:
        col = cli[DATABASE][COLLECTION]
        docs = list(col.aggregate(pipeline))
    
    print("Conexión establecida")

    if not docs:
        print("⚠️ No se encontraron documentos en el rango dado.")
        return pd.DataFrame(columns=["timestamp", "status_code_200", "status_code_500"])

    df = pd.DataFrame(docs)
    # Garantizamos dtype correcto
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["status_code_200"] = pd.to_numeric(df["status_code_200"], errors="coerce").fillna(0).astype(int)
    df["status_code_500"] = pd.to_numeric(df["status_code_500"], errors="coerce").fillna(0).astype(int)

    return df

def detectar_anomalias_df(df: pd.DataFrame):
    
    print("Iniciando detector de anomalias")

    if df.empty:
        print("No hay datos para analizar.")
        return

    df = df.copy()
    df = df.sort_values("timestamp")
    df = df.set_index("timestamp")

    # Si los datos ya vienen agregados por hora, resample no debería cambiar nada para 60min,
    # pero igual lo dejamos por si querés ventanas distintas (p.ej. 15min)
    for ventana_minutos in VENTANAS_MINUTOS:
        print(f"\n🔎 Analizando ventana de {ventana_minutos} minutos...")
        # sum = agregamos por ventana
        df_resample = df.resample(f"{ventana_minutos}min").sum()

        # Estadísticos globales de referencia
        medias = df_resample[["status_code_200", "status_code_500"]].mean()
        desvios = df_resample[["status_code_200", "status_code_500"]].std().replace(0, 1)  # evitar 0

        for ts, fila in df_resample.iterrows():
            ts_fin = ts + timedelta(minutes=ventana_minutos - 1)

            val_200 = fila.get("status_code_200", 0)
            val_500 = fila.get("status_code_500", 0)

            z200 = (val_200 - medias["status_code_200"]) / desvios["status_code_200"]
            z500 = (val_500 - medias["status_code_500"]) / desvios["status_code_500"]

            print(f"\n📌 {ts} → {ts_fin}")
            print(f"  status_code_200: {val_200} (media={medias['status_code_200']:.2f}, "
                  f"desv={desvios['status_code_200']:.2f}, z={z200:.2f})")
            print(f"  status_code_500: {val_500} (media={medias['status_code_500']:.2f}, "
                  f"desv={desvios['status_code_500']:.2f}, z={z500:.2f})")

            if abs(z200) > UMBRAL_Z_SCORE:
                print(f"  ⚠️ Anomalía en status_code_200 (z={z200:.2f})")
            if abs(z500) > UMBRAL_Z_SCORE:
                print(f"  ⚠️ Anomalía en status_code_500 (z={z500:.2f})")


if __name__ == "__main__":
    df = fetch_logs_from_mongo(START_ISO, END_ISO)
    detectar_anomalias_df(df)
