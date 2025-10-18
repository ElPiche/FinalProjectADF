import json
import random
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
from pymongo import MongoClient

# --------------------
# Parámetros
# --------------------
CANTIDAD_REGISTROS = 43200 # esto es un mes entero
PROBABILIDAD_ANOMALIA = 0.1

MEDIA_HTTP_200_LABORAL = 100
MEDIA_HTTP_200_NO_LABORAL = 15

BINOMIAL_INTENTOS_HTTP_500 = 5
PROBABILIDAD_HTTP_500_LABORAL = 0.05
PROBABILIDAD_HTTP_500_NO_LABORAL = 0.04
INICIO_DE_SIMULACION = datetime(2025, 9, 1, 0, 0, 0)

# --------------------
# Conexión Mongo
# --------------------
def get_mongo():
    return MongoClient("mongodb://root:example@localhost:27017/")

# --------------------
# 1. Generar colección minuto
# --------------------
def generar_minute_collection():
    logs = []
    timestamp_actual = INICIO_DE_SIMULACION

    for _ in range(CANTIDAD_REGISTROS):
        es_laboral = (9 <= timestamp_actual.hour < 17) and (timestamp_actual.weekday() < 5)

        if es_laboral:
            cantidad_http_200 = np.random.poisson(MEDIA_HTTP_200_LABORAL)
            cantidad_http_500 = np.random.binomial(BINOMIAL_INTENTOS_HTTP_500, PROBABILIDAD_HTTP_500_LABORAL)
        else:
            cantidad_http_200 = np.random.poisson(MEDIA_HTTP_200_NO_LABORAL)
            cantidad_http_500 = np.random.binomial(BINOMIAL_INTENTOS_HTTP_500, PROBABILIDAD_HTTP_500_NO_LABORAL)

        # ruido
        cantidad_http_200 = int(cantidad_http_200 * random.uniform(0.8, 1.2))
        cantidad_http_500 = int(cantidad_http_500 * random.uniform(0.8, 1.5))

        # anomalía
        if random.random() < PROBABILIDAD_ANOMALIA:
            cantidad_http_200 = 0
            cantidad_http_500 += random.randint(10, 50)

        logs.append({
            "timestamp": timestamp_actual.isoformat(),
            "type_of_day": "workable" if es_laboral else "non-workable",
            "status_code_200_counter": cantidad_http_200,
            "status_code_500_counter": cantidad_http_500
        })

        timestamp_actual += timedelta(minutes=1)

    return logs

# --------------------
# 2. Generar colección hora
# --------------------
def generar_hour_collection(minute_logs):
    df = pd.DataFrame(minute_logs)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df.set_index("timestamp", inplace=True)

    hour_data = []
    # resample by hour and aggregate with mean + std at once
    df_resample = df.resample("1h").agg({
        "status_code_200_counter": ["mean", "std"],
        "status_code_500_counter": ["mean", "std"]
    })

    for timestamp, row in df_resample.iterrows():
        avg_200 = float(row[("status_code_200_counter", "mean")]) if not pd.isna(row[("status_code_200_counter", "mean")]) else 0.0
        std_200 = float(row[("status_code_200_counter", "std")]) if not pd.isna(row[("status_code_200_counter", "std")]) else 0.0

        avg_500 = float(row[("status_code_500_counter", "mean")]) if not pd.isna(row[("status_code_500_counter", "mean")]) else 0.0
        std_500 = float(row[("status_code_500_counter", "std")]) if not pd.isna(row[("status_code_500_counter", "std")]) else 0.0

        hour_doc = {
            "timestamp": timestamp.isoformat(),
            "type_of_day": "workable" if (9 <= timestamp.hour < 17) else "non-workable",
            "average_200": avg_200,
            "standard_deviation_200": std_200,
            "average_500": avg_500,
            "standard_deviation_500": std_500
        }

        # Not persisted, but log weekday for debugging
        weekday = timestamp.strftime("%A")
        print(f"Hour {timestamp.isoformat()} → {weekday}")

        hour_data.append(hour_doc)

    return hour_data


# --------------------
# 3. Generar colección día
# --------------------
def generar_day_collection(minute_logs):
    df = pd.DataFrame(minute_logs)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df.set_index("timestamp", inplace=True)

    day_data = []
    df_resample = df.resample("1D").agg({
        "status_code_200_counter": ["mean", "std"],
        "status_code_500_counter": ["mean", "std"]
    })

    for timestamp, row in df_resample.iterrows():
        avg_200 = float(row[("status_code_200_counter", "mean")]) if not pd.isna(row[("status_code_200_counter", "mean")]) else 0.0
        std_200 = float(row[("status_code_200_counter", "std")]) if not pd.isna(row[("status_code_200_counter", "std")]) else 0.0

        avg_500 = float(row[("status_code_500_counter", "mean")]) if not pd.isna(row[("status_code_500_counter", "mean")]) else 0.0
        std_500 = float(row[("status_code_500_counter", "std")]) if not pd.isna(row[("status_code_500_counter", "std")]) else 0.0

        day_doc = {
            "date": timestamp.strftime("%Y-%m-%d"),
            "type_of_day": "workable" if (timestamp.weekday() < 5) else "non-workable",
            "average_200": avg_200,
            "standard_deviation_200": std_200,
            "average_500": avg_500,
            "standard_deviation_500": std_500
        }

        print(f"Day {timestamp.strftime('%Y-%m-%d')} → {timestamp.strftime('%A')}")
        day_data.append(day_doc)

    return day_data


# --------------------
# 4. Generar colección mes
# --------------------
def generar_month_collection(minute_logs):
    df = pd.DataFrame(minute_logs)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df.set_index("timestamp", inplace=True)

    month_data = []
    df_resample = df.resample("1M").agg({
        "status_code_200_counter": ["mean", "std"],
        "status_code_500_counter": ["mean", "std"]
    })

    for timestamp, row in df_resample.iterrows():
        avg_200 = float(row[("status_code_200_counter", "mean")]) if not pd.isna(row[("status_code_200_counter", "mean")]) else 0.0
        std_200 = float(row[("status_code_200_counter", "std")]) if not pd.isna(row[("status_code_200_counter", "std")]) else 0.0

        avg_500 = float(row[("status_code_500_counter", "mean")]) if not pd.isna(row[("status_code_500_counter", "mean")]) else 0.0
        std_500 = float(row[("status_code_500_counter", "std")]) if not pd.isna(row[("status_code_500_counter", "std")]) else 0.0

        month_doc = {
            "month": timestamp.strftime("%Y-%m"),
            "average_200": avg_200,
            "standard_deviation_200": std_200,
            "average_500": avg_500,
            "standard_deviation_500": std_500
        }

        print(f"Month {timestamp.strftime('%Y-%m')} → {timestamp.strftime('%B')}")
        month_data.append(month_doc)

    return month_data

# --------------------
# 5. Guardar en Mongo
# --------------------
def guardar_en_mongo(collection_name, data):
    client = get_mongo()
    db = client["synthetic_db"]
    collection = db[collection_name]
    collection.insert_many(data)
    print(f"✅ Insertados {len(data)} documentos en {collection_name}")

# --------------------
# Main
# --------------------
if __name__ == "__main__":
    minute_logs = generar_minute_collection()
    hour_logs = generar_hour_collection(minute_logs)
    day_logs = generar_day_collection(minute_logs)
    month_logs = generar_month_collection(minute_logs)

    # Save each to its own JSON file
    with open("2025-09_minutes.json", "w") as f:
        json.dump(minute_logs, f, indent=2)

    with open("2025-09_hours.json", "w") as f:
        json.dump(hour_logs, f, indent=2)

    with open("2025-09_days.json", "w") as f:
        json.dump(day_logs, f, indent=2)

    with open("2025-09_months.json", "w") as f:
        json.dump(month_logs, f, indent=2)


    # Guardar en Mongo
    # guardar_en_mongo("minute", minute_logs)
    # guardar_en_mongo("hour", hour_logs)
