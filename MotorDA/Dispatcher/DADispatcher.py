import json
from bson import json_util
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


class TrainingAlgorithm:
    def __init__(self,  mode: str):

        self.mode = mode

    def __repr__(self):
        return f"TrainingAlgorithm(mode={self.mode})"


class ZScore:
    def __init__(self, train_window: int, train_from: str, train_to: str, threshold: float, observed_values: Dict[str, pd.DataFrame]):
        self.train_window = train_window  # in minutes
        self.threshold = threshold
        self.train_from = train_from
        self.train_to = train_to
        self.observed_values = observed_values

    def __repr__(self):
        return f"ZScore(window={self.train_window}min, threshold={self.threshold}, metrics={list(self.observed_values.keys())})"


# Dispatcher: Tiene como objetivo recibir el documento de configuración desde MongoDB y despachar la ejecución del algoritmo correspondiente.
# Tiene que en base al documento de configuración, identificar qué algoritmo se debe ejecutar y llamar a la función correspondiente,
# pasándole los parámetros necesarios. Y guardar los resultados en ElasticSearch.
# En la versión actual también consultaría el mongoDB que contiene la data de documentación para leer la metadata y saber si esta entrenando o no jeje.

# conexión a MongoDB KB
MONGO_KB_URL = "mongodb://admin:1q2w3E%2A@localhost:27017/?authSource=admin"
KB_DB_NAME = "logsdb"
KB_COLLECTION_NAME = "testingConfig"

# conexión a MongoDB MotorDA pendiente
DB_NAME_MOTOR_DA = "logsdb"
DA_COLLECTION_NAME = "series"

DA_RESULT_COLLECTION_NAME = "seriesResult"

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

# returns


def ExtractLatestConfigurationKB(client: MongoClient):

    # as of right now, we get only one document, the idea would be to get the latest one when mongo change stream
    # calls us
    # query = {"metadata.dim": "2xx", "metadata.kbid": "A1"}
    result = client[DB_NAME_MOTOR_DA][KB_COLLECTION_NAME].find().sort(
        '_id', -1).limit(1).next()

    print(result)

    # we parse with BSON cuz mongo brings some binary data inside, and we want to serialize it into JSON
    with open("Series_Mongo_Result.json", "w", encoding="utf-8") as f:
        f.write(json_util.dumps(result, indent=2))
        """
        latest_document = collection.find().sort('created_at', -1).limit(1).next()print(latest_document)
        """
    return result

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


def run_zscore(config_block: Dict[str, Any]):
    params = (config_block.get("daAlgParameters") or {}).get("zscore", [])
    for p in params:
        print(
            f"▶ ZSCORE threshold={p.get('threshold')} observedValue={p.get('observedValue')}")
    # acá va tu implementación real...


def run_zscore_batch_training(zScore: ZScore, data_to_train: TrainingAlgorithm, da_client: MongoClient):

    # iterating both key and values
    for key, value in zScore.observed_values.items():
        print(key)
        results = train_baseline(value, "value")
        da_client[KB_DB_NAME][DA_RESULT_COLLECTION_NAME].insert_one(results)

    return train_baseline(zScore.observed_values["5xx_status_codes"], "value")


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


def parse_json_to_classes(json_data: dict) -> tuple[TrainingAlgorithm, ZScore]:
    """
    Parse JSON data into TrainingAlgorithm and ZScore classes.

    Args:
        json_data: Dictionary containing training_data and trained_data

    Returns:
        Tuple of (TrainingAlgorithm, ZScore) instances
    """

    # Extract training_data

    algorithm = json_data.get("algorithm", {})
    # print(algorithm)

    algorithm_parameters = algorithm.get("parameters", {})
    print(algorithm.get("name"))

    if (algorithm.get("name") == "zscore"):
        print("soy EL zscore uwu")

    parameters = algorithm_config.get("parameters", {})

    # Create TrainingAlgorithm instance
    training_algo = TrainingAlgorithm(
        #
        #
        mode=training_data.get("mode")
    )

    # Extract trained_data for ZScore metrics
    trained_data = json_data.get("trained_data", {})
    trained_list = trained_data.get("trained_list", [])

    # Build observed_values dictionary with DataFrames
    # Each metric gets its own DataFrame with timestamp and value columns
    observed_values = {}
    observed_values_data = training_data.get("observed_values", {})

    for metric_name, data_points in observed_values_data.items():
        if data_points:  # If there are data points
            # Create DataFrame from the list of dictionaries
            df = pd.DataFrame(data_points)
            # Convert timestamp to datetime if needed
            if 'timestamp' in df.columns:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
            observed_values[metric_name] = df

    # Create ZScore instance
    z_score = ZScore(
        train_window=training_data.get("algorithm").get(
            "parameters").get("train_window"),
        threshold=10,
        observed_values=observed_values,
        train_from=parameters.get("from"),
        train_to=parameters.get("to"),
    )

    return training_algo, z_score


def main():

    # Esto arma la conexión a MongoDB
    kb_client = CreateConnectionToKB()

    # aquí llamariamos a nuestra lógica para checkear la metadata para corroborar si ya hemos hechos
    # esta operativa antes

    # nos conectamos a la DB donde está la data que nos interesa
    da_client = CreateConnectionToDA()

    # TODO: add a watch on the connection to the KBConfig one

    # de aquí extraemos los datos de las operativas que vayamos a llamar
    latest_series_config = ExtractLatestConfigurationKB(kb_client)

    # latest_series_config_json = json.loads(latest_series_config)

    training_algo, z_score = parse_json_to_classes(latest_series_config)

    print("I am printing the training algo data:")
    print(training_algo)

    print("--------------------------------------------------------------------")

    print("I am printing the z score DATAFRAMIOS data:")
    print(z_score.observed_values["2xx_status_codes"])

    print("--------------------------------------------------------------------")

    print("I am printing the z score data:")
    print(z_score)

    result = run_zscore_batch_training(z_score, training_algo, da_client)

    anomalies = detectar_anomalias_df(
        z_score.observed_values["5xx_status_codes"], result, z_score.train_window)

    save_anomalies_json(anomalies, result, 'Anomalies_Detected_ZScore.json')

    # por ahora dejaremos el change para despues

    # CENTRARSE EN PARSEAR CONFIG -> ENTRENAR -> DETECTAR

    observed_fields = ["status_code_5xx"]

    # df = run_zscore_batch("2025-10-01T00:00:00Z",
    #                      "2025-10-09T23:59:59Z", observed_fields, da_client)

# doc = dispatcher.get_record_by_id("8fbb07a4-f8f0-46ed-9eae-b8d4789c570c")

# aca iria un switch o map para llamar al algoritmo correspondiente


if __name__ == "__main__":
    main()
