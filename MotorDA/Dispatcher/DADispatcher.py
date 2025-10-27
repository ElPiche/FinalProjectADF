from datetime import datetime
from typing import Dict, List
import json
from bson import json_util
from pymongo import MongoClient
import pandas as pd
# from MongoClass import MongoKBConnection
from typing import Dict, Any, List, Optional, Tuple
from elasticsearch import Elasticsearch, helpers


from ..ZScore.standalone_da_algorithm_z_score import (
    fetch_logs_from_mongo,
    train_baseline,
    detectar_anomalias_df,
    save_anomalies_json
)


class TrainingAlgorithm:
    def __init__(self,  mode: int):

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
KB_COLLECTION_NAME = "trainingconfig"

# conexión a MongoDB MotorDA pendiente
DB_NAME_MOTOR_DA = "logsdb"
DA_COLLECTION_NAME = "series"

DA_RESULT_COLLECTION_NAME = "seriesResult"

# conexión a elasticSearch
ES_HOST = "http://localhost:9201"
ES_INDEX = "test_logs"


elastic_client = Elasticsearch(ES_HOST)


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

    # {'train_window': 60, 'dimensions': ['5xx_status_code', '4xx_status_code', '2xx_status_code'], 'from': '2025-10-01T00:00:00.000Z', 'to': '2025-11-10T00:00:00.000Z'}
    #     # query = {"metadata.dim": "2xx", "metadata.kbid": "A1"}

    # iterating both key and values
    for key, value in zScore.observed_values.items():
        print(key)

        if (not value.empty):
            results = train_baseline(value, "value")
            da_client[KB_DB_NAME][DA_RESULT_COLLECTION_NAME].insert_one(
                results)

    return results


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


def fetch_series_data_with_aggregation(
    config_doc: Dict,
    da_client: MongoClient,
    db_name: str = "logsdb",
    series_collection_name: str = "series"
) -> Dict[str, pd.DataFrame]:
    """
    Fetch series data for all dimensions using MongoDB aggregation pipeline.

    Args:
        config_doc: Configuration document from trainingconfig collection
        da_client: MongoDB client connected to the DA database
        db_name: Database name
        series_collection_name: Series collection name

    Returns:
        Dictionary mapping dimension names to their respective DataFrames
    """

    # Extract parameters from config
    algorithm_params = config_doc.get('algorithm', {}).get('parameters', {})
    dimensions = algorithm_params.get('dimensions', [])
    kb_id = config_doc.get('kb_id')
    # Don't convert - keep as is (it's an integer!)
    mode = config_doc.get('mode')
    date_from = algorithm_params.get('from')
    date_to = algorithm_params.get('to')

    # Get series collection
    series_collection = da_client[db_name][series_collection_name]

    print(f"\n{'='*60}")
    print(f"Fetching data for {len(dimensions)} dimensions")
    print(f"KB ID: {kb_id}")
    print(f"Mode: {mode} (type: {type(mode).__name__})")
    print(f"Date range: {date_from} to {date_to}")
    print(f"Dimensions: {dimensions}")
    print(f"{'='*60}\n")

    # Debug: Check what's actually in the series collection
    print("DEBUG: Checking series collection...")
    sample_doc = series_collection.find_one()
    if sample_doc:
        print(f"Sample document structure:")
        print(
            f"  metadata.kbId: {sample_doc.get('metadata', {}).get('kbId')} (type: {type(sample_doc.get('metadata', {}).get('kbId')).__name__})")
        print(f"  metadata.dim: {sample_doc.get('metadata', {}).get('dim')}")
        print(
            f"  metadata.mode: {sample_doc.get('metadata', {}).get('mode')} (type: {type(sample_doc.get('metadata', {}).get('mode')).__name__})")
        print(
            f"  timestamp: {sample_doc.get('timestamp')} (type: {type(sample_doc.get('timestamp')).__name__})")
    else:
        print("  ✗ Collection is empty!")
    print()

    observed_values = {}

    for dimension in dimensions:
        # Convert ISO string dates to datetime objects for MongoDB query
        date_from_dt = datetime.fromisoformat(
            date_from.replace('Z', '+00:00')) if date_from else None
        date_to_dt = datetime.fromisoformat(
            date_to.replace('Z', '+00:00')) if date_to else None

        # Build aggregation pipeline
        match_query = {
            'metadata.kbId': kb_id,
            'metadata.dim': dimension,
            'metadata.mode': mode  # Use mode as-is (integer)
        }

        # Add timestamp filter if dates are provided
        if date_from_dt and date_to_dt:
            match_query['timestamp'] = {
                '$gte': date_from_dt,
                '$lte': date_to_dt
            }

        pipeline = [
            {
                '$match': match_query
            },
            {
                '$project': {
                    '_id': 0,
                    'timestamp': 1,
                    'value': 1
                }
            },
            {
                '$sort': {'timestamp': 1}
            }
        ]

        print(f"Processing dimension: {dimension}")
        print(f"  Match query: {match_query}")

        # Debug: Try to find at least one document with this dimension
        test_query = {'metadata.dim': dimension}
        count_with_dim = series_collection.count_documents(test_query)
        print(f"  DEBUG: Documents with dim='{dimension}': {count_with_dim}")

        if count_with_dim > 0:
            # Check kb_id match
            test_query['metadata.kbId'] = kb_id
            count_with_kb = series_collection.count_documents(test_query)
            print(
                f"  DEBUG: Documents with dim='{dimension}' AND kbId='{kb_id}': {count_with_kb}")

            # Check mode match
            test_query['metadata.mode'] = mode
            count_with_mode = series_collection.count_documents(test_query)
            print(
                f"  DEBUG: Documents with all filters (no timestamp): {count_with_mode}")

            # Check with timestamp
            if date_from_dt and date_to_dt:
                test_query['timestamp'] = {
                    '$gte': date_from_dt, '$lte': date_to_dt}
                count_with_timestamp = series_collection.count_documents(
                    test_query)
                print(
                    f"  DEBUG: Documents with all filters (WITH timestamp): {count_with_timestamp}")

        try:
            # Execute aggregation pipeline
            cursor = series_collection.aggregate(pipeline)
            results = list(cursor)

            print(f"  Aggregation returned {len(results)} results")

            if results:
                # Create DataFrame
                df = pd.DataFrame(results)

                # Convert timestamp to datetime
                df['timestamp'] = pd.to_datetime(df['timestamp'])

                # Convert value to numeric (handle MongoDB numberLong)
                if 'value' in df.columns:
                    # Handle nested value structure from MongoDB
                    df['value'] = df['value'].apply(
                        lambda x: float(x) if isinstance(x, (int, float))
                        else float(x.get('$numberLong', 0)) if isinstance(x, dict)
                        else 0
                    )

                observed_values[dimension] = df
                print(f"  ✓ Fetched {len(df)} records")
                print(
                    f"  → Date range in data: {df['timestamp'].min()} to {df['timestamp'].max()}")
            else:
                print(f"  ✗ No data found")
                # Create empty DataFrame with proper structure
                observed_values[dimension] = pd.DataFrame(
                    columns=['timestamp', 'value'])

        except Exception as e:
            print(f"  ✗ Error fetching data: {str(e)}")
            import traceback
            traceback.print_exc()
            observed_values[dimension] = pd.DataFrame(
                columns=['timestamp', 'value'])

    print(f"\n{'='*60}")
    print(
        f"Summary: Successfully fetched data for {len([df for df in observed_values.values() if not df.empty])}/{len(dimensions)} dimensions")
    print(f"{'='*60}\n")

    return observed_values


def fetch_series_data_batch(
    dimensions: List[str],
    kb_id: str,
    mode: str,
    date_from: str,
    date_to: str,
    da_client: MongoClient,
    db_name: str = "logsdb",
    series_collection_name: str = "series"
) -> Dict[str, pd.DataFrame]:
    """
    Alternative function to fetch series data when you have individual parameters
    instead of a config document.
    """

    series_collection = da_client[db_name][series_collection_name]

    print(f"\nFetching batch data for {len(dimensions)} dimensions...")

    observed_values = {}

    for dimension in dimensions:
        pipeline = [
            {
                '$match': {
                    'metadata.kbId': kb_id,
                    'metadata.dim': dimension,
                    'metadata.mode': mode.upper(),
                    'timestamp': {
                        '$gte': {'$date': date_from},
                        '$lte': {'$date': date_to}
                    }
                }
            },
            {
                '$project': {
                    '_id': 0,
                    'timestamp': 1,
                    'value': 1
                }
            },
            {
                '$sort': {'timestamp': 1}
            }
        ]

        try:
            cursor = series_collection.aggregate(pipeline)
            results = list(cursor)

            if results:
                df = pd.DataFrame(results)
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                df['value'] = df['value'].apply(
                    lambda x: float(x) if isinstance(x, (int, float))
                    else float(x.get('$numberLong', 0)) if isinstance(x, dict)
                    else 0
                )
                observed_values[dimension] = df
                print(f"  ✓ {dimension}: {len(df)} records")
            else:
                observed_values[dimension] = pd.DataFrame(
                    columns=['timestamp', 'value'])
                print(f"  ✗ {dimension}: No data")

        except Exception as e:
            print(f"  ✗ {dimension}: Error - {str(e)}")
            observed_values[dimension] = pd.DataFrame(
                columns=['timestamp', 'value'])

    return observed_values


# Updated parse_json_to_classes to use the new fetcher
def parse_json_to_classes(json_data: dict, da_client: MongoClient) -> tuple:
    """
    Parse JSON data into TrainingAlgorithm and ZScore classes.
    Now fetches actual data from MongoDB series collection.

    Args:
        json_data: Dictionary containing training configuration
        da_client: MongoDB client for fetching series data

    Returns:
        Tuple of (TrainingAlgorithm, ZScore) instances
    """

    # Extract algorithm info
    algorithm = json_data.get("algorithm", {})
    algorithm_name = algorithm.get("name")
    algorithm_parameters = algorithm.get("parameters", {})

    # Extract mode
    mode = json_data.get("mode", 0)

    # Create TrainingAlgorithm instance
    training_algo = TrainingAlgorithm(mode=mode)

    if algorithm_name == "zscore":
        print("Processing Z-Score algorithm configuration...")

        # Fetch data from MongoDB using aggregation pipeline
        observed_values = fetch_series_data_with_aggregation(
            config_doc=json_data,
            da_client=da_client
        )

        # Create ZScore instance
        z_score = ZScore(
            train_window=algorithm_parameters.get("train_window", 60),
            threshold=0,  # You might want to extract this from config
            observed_values=observed_values,
            train_from=algorithm_parameters.get("from"),
            train_to=algorithm_parameters.get("to")
        )

        return training_algo, z_score

    # Add other algorithm handlers here
    else:
        raise ValueError(f"Unsupported algorithm: {algorithm_name}")


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

    training_algo, z_score = parse_json_to_classes(
        latest_series_config, kb_client)

    results = run_zscore_batch_training(z_score, training_algo, kb_client)

    anomalies = detectar_anomalias_df(
        z_score.observed_values["status_code_5xx_counter"], results, 60)

    only_anomalies = [
        item for item in anomalies if item.get('is_anomaly') == True]

    # save_anomalies_json(anomalies, results, "detección.json")
    print(only_anomalies)
    anomalies_for_elastic = []

    for item in only_anomalies:

        doc = {
            'algorithm': 'ZScore',
            'text': 'Anomaly detected',
            'timestamp': item["timestamp"],
            'value': item["value"],
            '_index': "anomaly"
        }
        anomalies_for_elastic.append(doc)

    helpers.bulk(elastic_client, anomalies_for_elastic)
    # resp = client.index(index="anomaly", id=1, document=doc)
    # print(resp['result'])


if __name__ == "__main__":
    main()
