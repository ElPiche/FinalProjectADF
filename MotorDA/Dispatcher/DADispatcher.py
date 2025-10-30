import threading
import time
from datetime import datetime
import json
from bson import json_util
from pymongo import MongoClient
import pandas as pd
from typing import Dict, Any, List, Optional, Tuple
from elasticsearch import Elasticsearch, helpers
from dataclasses import dataclass, field


from ..ZScore.standalone_da_algorithm_z_score import (
    fetch_logs_from_mongo,
    train_baseline,
    detectar_anomalias_df,
    save_anomalies_json
)


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


@dataclass
class Parameters:
    train_window: int
    # dimension → { key → value } key value being for algorithm metadata, might be empty
    observed_values: Dict[str, Dict[str, int]]
    from_: datetime
    to: datetime


@dataclass
class Algorithm:
    name: str
    parameters: Parameters

    def execute(self, config):

        match self.name:

            case "zscore":

                print("I am executing Z Score")
                observed_values = fetch_series_data_with_aggregation(
                    config, self)

                print(observed_values)
                results = run_zscore_batch_training(config, observed_values)
                # ----------------------------ENDING OF TRAINING ZSCORE----------------------------------------------------------------------------

                anomalies_dict: Dict[str, List] = {}
                for key, value in observed_values.items():

                    anomalies = detectar_anomalias_df(
                        value, results, self.parameters.train_window)
                    anomalies_dict[key] = anomalies

                # print(anomalies_dict)

                filtered_anomalies = {
                    key: [item for item in value if item.get('is_anomaly')]
                    for key, value in anomalies_dict.items()
                }

                print(f"Found {len(filtered_anomalies)} anomalies")
                anomalies_for_elastic = []

                for key, anomalies in filtered_anomalies.items():
                    for item in anomalies:
                        doc = {
                            'algorithm': 'ZScore',
                            'metric': key,  # optional — store which metric the anomaly belongs to
                            'text': 'Anomaly detected',
                            'timestamp': item["timestamp"],
                            'value': item["value"],
                            '_index': "anomaly"
                        }
                        anomalies_for_elastic.append(doc)

                helpers.bulk(elastic_client, anomalies_for_elastic)
            case _:
                print(f"TRAINING {self.name} NOT IMPLEMENTED YET.")


@dataclass
class Config:
    _id: str
    kb_id: str
    kb_description: str
    created_at: datetime
    mode: int
    algorithms: List[Algorithm]

    def execute_algos(self):

        if (not self.algorithms):
            print("I have no algorithms to call")
            return None

        for algo in self.algorithms:
            algo.execute(self)


def parse_config(data: dict) -> Config:
    return Config(
        _id=data["_id"],
        kb_id=data["kb_id"],
        kb_description=data["kb_description"],
        created_at=datetime.fromisoformat(
            data["created_at"].replace("Z", "+00:00")),
        mode=data["mode"],

        algorithms=[
            Algorithm(
                name=a["name"].lower(),
                parameters=Parameters(
                    train_window=a["parameters"]["train_window"],
                    observed_values={
                        ov["dimension"]: {am["key"]: am["value"]
                                          for am in ov["algorithm_metadata"]}
                        for ov in a["parameters"]["observed_values"]
                    },
                    from_=datetime.fromisoformat(
                        a["parameters"]["from"].replace("Z", "+00:00")),
                    to=datetime.fromisoformat(
                        a["parameters"]["to"].replace("Z", "+00:00")),
                ),
            )
            for a in data["algorithms"]
        ],
    )


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


def get_kb_block(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Devuelve siempre el bloque kbConfig sin importar si viene en camelCase o PascalCase."""
    return doc.get("kbConfig") or doc.get("KB_Config") or {}


def get_kb_id(doc: Dict[str, Any]) -> Optional[str]:
    kb = get_kb_block(doc)
    return kb.get("id") or kb.get("Id")


def run_zscore_batch_training(config: Config, observed_values):

    # {'train_window': 60, 'dimensions': ['5xx_status_code', '4xx_status_code', '2xx_status_code'], 'from': '2025-10-01T00:00:00.000Z', 'to': '2025-11-10T00:00:00.000Z'}
    #     # query = {"metadata.dim": "2xx", "metadata.kbid": "A1"}
    da_client = CreateConnectionToDA()
    print(f"I am printing kb_id: " + config.kb_id)
    # iterating both key and values
    for key, value in observed_values.items():

        if (not value.empty):
            print(f"printing the key of the observed_values: {key}")
            print(f"printing the key of the observed_values: {value}")

            results = train_baseline(config.kb_id, key, value, "value")
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


def fetch_series_data_with_aggregation(
    config: Config, algorithm_to_execute: Algorithm
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

    da_client = CreateConnectionToDA()

    series_collection = da_client[DB_NAME_MOTOR_DA][DA_COLLECTION_NAME]

    dimensions = list(algorithm_to_execute.parameters.observed_values.keys())
    kb_id = config.kb_id
    mode = config.mode
    date_from = algorithm_to_execute.parameters.from_
    date_to = algorithm_to_execute.parameters.to

    print(f"\033[33m{algorithm_to_execute.parameters}\033[0m")

    print(f"\n{'='*60}")
    print(
        f"Fetching data for {len(dimensions)} dimensions")
    print(f"KB ID: {kb_id}")
    print(f"Mode: {mode}")
    # print(f"Date range: {date_from} to {date_to}")
    print(f"Dimensions: {dimensions}")
    print(f"{'='*60}\n")

    # Debug: Check what's actually in the series collection
    print("DEBUG: Checking series collection...")
    sample_doc = series_collection.find_one()

    if sample_doc:
        print(f"Sample document structure:")
        print(
            f"  metadata.kbId: {sample_doc.get('metadata', {}).get('kbId')} (type: {type(sample_doc.get('metadata', {}).get('kbId')).__name__})")
        print(
            f"  metadata.dim: {sample_doc.get('metadata', {}).get('dim')}")
        print(
            f"  metadata.mode: {sample_doc.get('metadata', {}).get('mode')} (type: {type(sample_doc.get('metadata', {}).get('mode')).__name__})")
        print(
            f"  timestamp: {sample_doc.get('timestamp')} (type: {type(sample_doc.get('timestamp')).__name__})")
    else:
        print("  ✗ Collection is empty!")
    print()

    observed_values = {}

    for dimension in dimensions:

        print(type(date_from))
        """
        # Convert ISO string dates to datetime objects for MongoDB query
        date_from_dt = datetime.fromisoformat(
            date_from.replace('Z', '+00:00')) if date_from else None
        date_to_dt = datetime.fromisoformat(
            date_to.replace('Z', '+00:00')) if date_to else None
        """
        # Build aggregation pipeline
        match_query = {
            'metadata.kbId': kb_id,
            'metadata.dim': dimension,
            'metadata.mode': int(mode)  # Use mode as-is (integer)
        }

        # Add timestamp filter if dates are provided
        if date_from and date_to:
            match_query['timestamp'] = {
                '$gte': date_from,
                '$lte': date_to
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
            test_query['metadata.mode'] = int(mode)
            count_with_mode = series_collection.count_documents(test_query)
            print(
                f"  DEBUG: Documents with all filters (no timestamp): {count_with_mode}")

            # Check with timestamp
            if date_from and date_to:
                test_query['timestamp'] = {
                    '$gte': date_from, '$lte': date_to}
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


def watch_kb_changes(kb_client):
    with kb_client[KB_DB_NAME][KB_COLLECTION_NAME].watch() as stream:
        for change in stream:
            print(f"something happened on: {KB_COLLECTION_NAME}")

            if change.get("operationType") == "insert":
                print(
                    f"\033[31m Someone inserted data into: {KB_COLLECTION_NAME} \033[0m")

                # de aquí extraemos los datos de las operativas que vayamos a llamar en formato de JSON
                latest_series_config = ExtractLatestConfigurationKB(kb_client)

                # we turn the JSON with the config data into a class
                config: Config = parse_config(latest_series_config)

                # now we go thru each algorithm call we extracted, and try to execute training on them
                config.execute_algos()


def watch_detection_changes(kb_client):

    with kb_client[KB_DB_NAME][DA_COLLECTION_NAME].watch([
        {"$match": {"fullDocument.metadata.mode": 1}}
    ]) as stream:

        for change in stream:
            print(f"something happened on: {DA_COLLECTION_NAME}")

            if change.get("operationType") == "insert":
                print(
                    f"\033[31m Someone inserted data into: {DA_COLLECTION_NAME} \033[0m")

                serie_to_detect = change.get("fullDocument")

                query = {
                    'kb_id': serie_to_detect.get("metadata.kbId"),
                    'field': serie_to_detect.get("metadata.dim")
                }

                result = kb_client[KB_DB_NAME][DA_RESULT_COLLECTION_NAME].find_one(
                    query)

                print("I am printing the result of training:", result)
                # training_result = next(result, None)
                """
                anomalies_dict: Dict[str, List] = {}
                for key, value in observed_values.items():

                    anomalies = detectar_anomalias_df(
                        value, results, self.parameters.train_window)
                    anomalies_dict[key] = anomalies

                # print(anomalies_dict)

                filtered_anomalies = {
                    key: [item for item in value if item.get('is_anomaly')]
                    for key, value in anomalies_dict.items()
                }

                print(f"Found {len(filtered_anomalies)} anomalies")
                anomalies_for_elastic = []

                for key, anomalies in filtered_anomalies.items():
                    for item in anomalies:
                        doc = {
                            'algorithm': 'ZScore',
                            'metric': key,  # optional — store which metric the anomaly belongs to
                            'text': 'Anomaly detected',
                            'timestamp': item["timestamp"],
                            'value': item["value"],
                            '_index': "anomaly"
                        }
                        anomalies_for_elastic.append(doc)

                helpers.bulk(elastic_client, anomalies_for_elastic)
                """


def main():

    # Esto arma la conexión a MongoDB
    kb_client = CreateConnectionToKB()

    # aquí llamariamos a nuestra lógica para checkear la metadata para corroborar si ya hemos hechos
    # esta operativa antes
    # TODO: add a watch on the connection to the KBConfig one

    # Start watcher in its own thread
    training_watcher = threading.Thread(
        target=watch_kb_changes, args=(kb_client,), daemon=True)

    detection_watcher = threading.Thread(
        target=watch_detection_changes,
        args=(kb_client,),
        daemon=True
    )

    training_watcher.start()
    # detection_watcher.start()

    try:
        while training_watcher.is_alive():
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping watcher...")
        # Let it end naturally when Mongo closes or you implement a stop condition
        pass


if __name__ == "__main__":
    main()
