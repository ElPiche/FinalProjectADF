import json
from pymongo import MongoClient
import pandas as pd
# from MongoClass import MongoKBConnection
from typing import Dict, Any, List, Optional, Tuple

from ..ZScore.standalone_da_algorithm_z_score import (
    fetch_logs_from_mongo,
    train_baseline,
    detectar_anomalias_df,
    save_anomalies_json
)


# Dispatcher: Tiene como objetivo recibir el documento de configuración desde MongoDB y despachar la ejecución del algoritmo correspondiente.
# Tiene que en base al documento de configuración, identificar qué algoritmo se debe ejecutar y llamar a la función correspondiente,
# pasándole los parámetros necesarios. Y guardar los resultados en ElasticSearch.
# En la versión actual también consultaría el mongoDB que contiene la data de documentación para leer la metadata y saber si esta entrenando o no jeje.

# conexión a MongoDB KB
MONGO_KB_URL = "mongodb://admin:1q2w3E%2A@localhost:27017/?authSource=admin"
KB_DB_NAME = "logsdb"
KB_COLLECTION_NAME = "testLogsKB"

# conexión a MongoDB MotorDA pendiente
DB_NAME_MOTOR_DA = "logsdb"
DA_COLLECTION_NAME = "grouped_response_code_v2"


# conexión a elasticSearch
ES_HOST = "http://localhost:9200"
ES_INDEX = "test_logs"

KEYS = ("zscore", "arma", "kmeans", "iforest")


def CreateConnectionToKB() -> MongoClient:
    # we establish the connection to the kb mongo db
    mongo_kb_client = MongoClient(MONGO_KB_URL)
    kb_database = mongo_kb_client[KB_DB_NAME]
    kb_collection = kb_database[KB_COLLECTION_NAME]
    mongo_kb_client.admin.command("ping")
    print("Nos conectamos a la KB")
    return mongo_kb_client


def CreateConnectionToDA() -> MongoClient:
    # we establish the connection to the da mongo db
    mongo_da_client = MongoClient(MONGO_KB_URL)
    da_database = mongo_da_client[DB_NAME_MOTOR_DA]
    da_collection = da_database[DA_COLLECTION_NAME]
    mongo_da_client.admin.command("ping")
    print("Nos conectamos a la DA")
    return mongo_da_client


def ExtractConfiguration(client: MongoClient):
    return None

# Lector de json


def get_kb_block(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Devuelve siempre el bloque kbConfig sin importar si viene en camelCase o PascalCase."""
    return doc.get("kbConfig") or doc.get("KB_Config") or {}


def get_kb_id(doc: Dict[str, Any]) -> Optional[str]:
    kb = get_kb_block(doc)
    return kb.get("id") or kb.get("Id")


def get_selected_algorithms(doc: Dict[str, Any]) -> List[str]:
    """
    Devuelve la lista de algoritmos que el usuario 'eligió' (tienen parámetros cargados).
    """
    kb = get_kb_block(doc)
    params = kb.get("daAlgParameters", {}) or kb.get(
        "DA_Alg_Parameters", {}) or {}
    selected = []

    """
    for k in ALGO_KEYS:
        arr = params.get(k)
        if isinstance(arr, list) and len(arr) > 0:
            selected.append(k)
            """
    return selected


"""
def choose_algorithm(doc: Dict[str, Any], priority: Tuple[str, ...] = ALGO_KEYS) -> Optional[str]:
    
    Elige UN algoritmo. Si hay varios definidos, aplica prioridad.
    Si no hay ninguno, devuelve None.
    Si el JSON tuviera kbConfig.selectedAlgorithm, lo respeta si está definido.
    
    kb = get_kb_block(doc)
    explicit = kb.get("selectedAlgorithm")
    if explicit:
        return explicit if explicit in ALGO_KEYS else None

    selected = set(get_selected_algorithms(doc))
    for p in priority:
        if p in selected:
            return p
    return None
"""

# Correr algoritmos (placeholders)


def run_zscore(config_block: Dict[str, Any]):
    params = (config_block.get("daAlgParameters") or {}).get("zscore", [])
    for p in params:
        print(
            f"▶ ZSCORE threshold={p.get('threshold')} observedValue={p.get('observedValue')}")
    # acá va tu implementación real...


def run_zscore_batch(start_iso, end_iso, observed_fields, da_client: MongoClient):
    """
    df_detect = fetch_logs_from_mongo(
        CONNECTION, DEFAULT_DATABASE, COLLECTION, DETECT_FROM, DETECT_TO, [OBSERVED_FIELD])
    """

    # Fetch data from MongoDB within the given ISO date range and fields.
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

    docs = list(da_client[KB_DB_NAME][DA_COLLECTION_NAME].aggregate(pipeline))

    if not docs:
        return pd.DataFrame(columns=["timestamp"] + observed_fields)

    df = pd.DataFrame(docs)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    for field in observed_fields:
        df[field] = pd.to_numeric(df[field], errors="coerce").fillna(0)

    return df


def run_arma(config_block: Dict[str, Any]):
    params = (config_block.get("daAlgParameters") or {}).get("arma", [])
    for p in params:
        print(
            f"▶ ARMA p={p.get('p')} d={p.get('d')} q={p.get('q')} observedValue={p.get('observedValue')}")
    # implementación...


def run_kmeans(config_block: Dict[str, Any]):
    params = (config_block.get("daAlgParameters") or {}).get("kmeans", [])
    for p in params:
        print(
            f"▶ KMEANS nClusters={p.get('nClusters')} observedValue={p.get('observedValue')}")
    # implementación...


def run_iforest(config_block: Dict[str, Any]):
    params = (config_block.get("daAlgParameters") or {}).get("iforest", [])
    for p in params:
        print(
            f"▶ IFOREST nEstimators={p.get('nEstimators')} contamination={p.get('contamination')} observedValue={p.get('observedValue')}")
    # implementación...


# Map por si sirve
ALGORITHM_HANDLERS = {
    "zscore": run_zscore,
    "arma": run_arma,
    "kmeans": run_kmeans,
    "iforest": run_iforest,
}


def main():

    # Esto arma la conexión a MongoDB
    kb_client = CreateConnectionToKB()

    # de aquí extraemos los datos de las operativas que vayamos a llamar
    # nos debería devolver algo como esto:
    # TRAIN_FROM = "2025-10-01T00:00:00Z"
    # TRAIN_TO = "2025-10-09T23:59:59Z"
    # DETECT_FROM = "2025-10-10T00:00:00Z"
    # DETECT_TO = "2025-10-31T23:59:59Z"
    # OBSERVED_FIELD = "status_code_5xx_counter"
    # RANGE_IN_MINUTES = 60
    ExtractConfiguration(kb_client)

    # aquí llamariamos a nuestra lógica para checkear la metadata para corroborar si ya hemos hechos
    # esta operativa antes

    # corroborar que los datos sacados del KB
    print("Documento por id:")

    # nos conectamos a la DB donde está la data que nos interesa
    da_client = CreateConnectionToDA()

    # por ahora dejaremos el change para despues
    da_client[DB_NAME_MOTOR_DA][DA_COLLECTION_NAME].watch()

    # CENTRARSE EN PARSEAR CONFIG -> ENTRENAR -> DETECTAR

    """
    df_train = fetch_logs_from_mongo(
        CONNECTION, DEFAULT_DATABASE, COLLECTION, TRAIN_FROM, TRAIN_TO, [OBSERVED_FIELD])
    baseline = train_baseline(df_train, OBSERVED_FIELD)
    """
    observed_fields = ["status_code_5xx"]
    df = run_zscore_batch("2025-10-01T00:00:00Z",
                          "2025-10-09T23:59:59Z", observed_fields, da_client)

# doc = dispatcher.get_record_by_id("8fbb07a4-f8f0-46ed-9eae-b8d4789c570c")

# aca iria un switch o map para llamar al algoritmo correspondiente


if __name__ == "__main__":
    main()
