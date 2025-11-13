import json
import threading
import time
import traceback
import requests
from datetime import datetime, timezone
from bson import json_util
from pymongo import MongoClient
import pandas as pd
from typing import Dict, Any, List, Optional
from elasticsearch import Elasticsearch, helpers
from dataclasses import dataclass

from pymongo.errors import PyMongoError

#from pydantic import BaseModel


from ZScore.standalone_da_algorithm_z_score import (
    train_baseline,
    train_baseline_workdayless,
    anomaly_detection_workdayless,
    anomaly_detection_workdayful,
    get_closest_bucket
)


@dataclass
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

# conexión a MongoDB
MONGO_KB_URL = "mongodb://admin:1q2w3E%2A@mongodb:27017/?authSource=admin"
MONGO_DB_NAME = "anomaly_detection"
TRAINING_COLLECTION_NAME = "training_config"
SERIES_COLLECTION_NAME = "series"
SERIES_RESULT_COLLECTION_NAME = "series_result"
MONGO_TIMEOUT_MS = 2000

# beaware it has a trailing slash
ANOMALIES_INSIGHT_URL = "http://anomalies-insights:8081/api/"

# conexión a elasticSearch
ES_HOST = "http://elasticsearch-anomalies:9200"
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
                results = run_zscore_batch_training(config, observed_values, self.parameters.train_window)
                # ----------------------------ENDING OF TRAINING ZSCORE----------------------------------------------------------------------------

                # --------------------------- START OF DETECTION ZSCORE----------------------------------------------------------------------------
                # anomalies_dict: Dict[str, List] = {}
                # for key, value in observed_values.items():

                #    anomalies = detectar_anomalias_df(
                #        value, results, self.parameters.train_window)
                #    anomalies_dict[key] = anomalies

                # --------------------------- ENDING OF DETECTION ZSCORE----------------------------------------------------------------------------
                # send_anomalies_elastic(anomalies_dict)

            case _:
                print(f"TRAINING {self.name} NOT IMPLEMENTED YET.")
        delete_series(config)



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


def parse_iso(date_str: str) -> datetime:
    """
    Parses ISO 8601 timestamps that may include:
      - a 'Z' suffix (UTC)
      - a timezone offset like '+00:00'
      - no timezone info (assumed UTC)
      - missing milliseconds
    """
    if not date_str:
        raise ValueError("Empty or None date string provided")

    date_str = date_str.strip()

    # Normalize 'Z' to '+00:00' for fromisoformat
    if date_str.endswith("Z"):
        date_str = date_str[:-1] + "+00:00"

    try:
        dt = datetime.fromisoformat(date_str)
    except ValueError:
        # Fallback for cases missing milliseconds
        try:
            dt = datetime.fromisoformat(date_str.split(".")[0] + "+00:00")
        except Exception as e:
            raise ValueError(f"Unrecognized date format: {date_str}") from e

    # If no timezone info, assume UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt


def parse_config(data: dict) -> Config:
    return Config(
        _id=data["_id"],
        kb_id=data["kb_id"],
        kb_description=data["kb_description"],
        created_at=data["created_at"],
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
                    from_=a["parameters"]["from"],
                    to=a["parameters"]["to"],
                ),
            )
            for a in data["algorithms"]
        ],
    )


def CreateConnectionToKB() -> MongoClient:
    # we establish the connection to the kb mongo db
    mongo_kb_client = client = MongoClient(
        MONGO_KB_URL,
        serverSelectionTimeoutMS=MONGO_TIMEOUT_MS,
        connectTimeoutMS=MONGO_TIMEOUT_MS,
        socketTimeoutMS=MONGO_TIMEOUT_MS,
        retryWrites=True,
        retryReads=True,
        # Allow reads from secondary if primary unavailable
        readPreference='primaryPreferred'
    )

    kb_database = mongo_kb_client[MONGO_DB_NAME]
    kb_collection = kb_database[TRAINING_COLLECTION_NAME]
    mongo_kb_client.admin.command("ping")
    print("Nos conectamos al Mongo de entrenamiento")
    return mongo_kb_client


def CreateConnectionToDA() -> MongoClient:
    # we establish the connection to the da mongo db
    mongo_da_client = client = MongoClient(
        MONGO_KB_URL,
        serverSelectionTimeoutMS=MONGO_TIMEOUT_MS,
        connectTimeoutMS=MONGO_TIMEOUT_MS,
        socketTimeoutMS=MONGO_TIMEOUT_MS,
        retryWrites=True,
        retryReads=True,
        # Allow reads from secondary if primary unavailable
        readPreference='primaryPreferred'
    )
    da_database = mongo_da_client[MONGO_DB_NAME]
    da_collection = da_database[SERIES_COLLECTION_NAME]
    mongo_da_client.admin.command("ping")
    print("Nos conectamos a la DA")
    return mongo_da_client


def ExtractLatestConfigurationKB(client: MongoClient):

    # as of right now, we get only one document, the idea would be to get the latest one when mongo change stream
    # calls us
    # query = {"metadata.dim": "2xx", "metadata.kbid": "A1"}
    result = client[MONGO_DB_NAME][TRAINING_COLLECTION_NAME].find().sort(
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


def run_zscore_batch_training(config: Config, observed_values, time_window: int = 60):

    # {'train_window': 60, 'dimensions': ['5xx_status_code', '4xx_status_code', '2xx_status_code'], 'from': '2025-10-01T00:00:00.000Z', 'to': '2025-11-10T00:00:00.000Z'}
    #     # query = {"metadata.dim": "2xx", "metadata.kbid": "A1"}
    da_client: MongoClient = CreateConnectionToDA()

    print(f"I am printing kb_id: " + config.kb_id)
    # iterating both key and values
    for key, value in observed_values.items():

        if (not value.empty):
            print(f"printing the key of the observed_values: {key}")
            print(f"printing the key of the observed_values: {value}")

            results = train_baseline(config.kb_id, key, value, "value", time_window, workday_separation=True)
            print("PRINTING RESULTS:-----------------------------------------------------------------------")
            print(results)

            query = {"kb_id": config.kb_id, "dimension": key}
            exists_series_result = da_client[MONGO_DB_NAME][SERIES_RESULT_COLLECTION_NAME].find_one(query)

            if (exists_series_result):
                print( " \033[93m  I FOUND A SERIES RESULT AFTER TRAINING, DELETING BEFORE ADDING NEW SERIES RESULT \033[0m " )

                da_client[MONGO_DB_NAME][SERIES_RESULT_COLLECTION_NAME].delete_one(query)

            da_client[MONGO_DB_NAME][SERIES_RESULT_COLLECTION_NAME].insert_one(
                results)

    kb_id: str = config.kb_id

    query_filter = {'kb_id': kb_id}
    update_operation = {'$set':
                        {'is_trained': 'true'}
                        }

    da_client[MONGO_DB_NAME][TRAINING_COLLECTION_NAME].update_one(
        query_filter, update_operation)

def delete_series( config: Config):

    da_client: MongoClient = CreateConnectionToDA()

    query =  {'metadata.kbId': config.kb_id,
            'metadata.mode': int(config.mode) } # Use mode as-is (integer)

    print("WE'RE DELETING SERIES AFTER TRAINING")
    # we delete the data we used to train
    result =da_client[MONGO_DB_NAME][SERIES_COLLECTION_NAME].delete_many(query)
    print(result)

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

    da_client: MongoClient = CreateConnectionToDA()

    series_collection = da_client[MONGO_DB_NAME][SERIES_COLLECTION_NAME]

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

    while True:
        try:
            with kb_client[MONGO_DB_NAME][TRAINING_COLLECTION_NAME].watch() as stream:

                for change in stream:
                    print(f"something happened on: {TRAINING_COLLECTION_NAME}")

                    if change.get("operationType") == "insert" or change.get("operationType") == "update":
                        print(
                            f"\033[31m Someone inserted data into: {TRAINING_COLLECTION_NAME} \033[0m")

                        # TODO: add delete if exists for the series result

                        # de aquí extraemos los datos de las operativas que vayamos a llamar en formato de JSON
                        latest_series_config = ExtractLatestConfigurationKB(kb_client)

                        # we turn the JSON with the config data into a class
                        config: Config = parse_config(latest_series_config)

                        # now we go thru each algorithm call we extracted, and try to execute training on them
                        config.execute_algos()
                        # TODO: delete series once they are trained

        except PyMongoError as e:
            print(f"[watch_kb_changes] Mongo error: {e}, reconnecting in 5s...")
            time.sleep(5)
        except Exception as e:
            print(f"[watch_kb_changes] Unexpected error: {e}")
            traceback.print_exc()
            time.sleep(5)




def watch_detection_changes(kb_client):

    while True:
        try:
            with kb_client[MONGO_DB_NAME][SERIES_COLLECTION_NAME].watch([
                {"$match": {"fullDocument.metadata.mode": 1}}
            ]) as stream:

                for change in stream:
                    print(f"something happened on: {SERIES_COLLECTION_NAME}")

                    if change.get("operationType") == "insert":
                        print(
                            f"\033[31m Someone inserted data into: {SERIES_COLLECTION_NAME} \033[0m")

                        serie_to_detect = change.get("fullDocument")

                        print(f"I am printing serie_to_detect: {serie_to_detect}")

                        pipeline = [{'$match':
                                    {'kb_id': serie_to_detect["metadata"]["kbId"],
                                     'dimension': serie_to_detect["metadata"]["dim"]}
                                     }]

                        result = kb_client[MONGO_DB_NAME][SERIES_RESULT_COLLECTION_NAME].aggregate(
                            pipeline)

                        training_result = next(result, None)
                        #print(f"I am priting the result of training:  {training_result}")

                        # 2) flatten nested fields (metadata -> metadata.kbId etc.)
                        df = pd.json_normalize(serie_to_detect)

                        # optional: rename for convenience
                        df = df.rename(columns={
                            "metadata.kbId": "kbId",
                            "metadata.dim": "dim",
                            "metadata.mode": "mode"
                        })
                        # TODO: delete series once they are detected

                        # 3) make _id string (pandas doesn't like ObjectId)
                        if "_id" in df.columns:
                            df["_id"] = df["_id"].astype(str)

                        # 4) ensure timestamp is datetime dtype
                        if "timestamp" in df.columns:
                            df["timestamp"] = pd.to_datetime(df["timestamp"])

                        if training_result["work_day_enabled?"]:

                            #we add a boolean to know if it's a workday or not
                            df["is_workday"] = df["timestamp"].dt.dayofweek < 5

                            print("I am detecting Z score with work day enabled")
                            bucket_value = get_closest_bucket(df, training_result, training_result["time_window"])

                            anomalies = anomaly_detection_workdayful(
                                df, training_result, training_result["time_window"], bucket_value)

                        else:

                            bucket_value = get_closest_bucket(df, training_result, training_result["time_window"])
                            print("I am detecting Z score with work day disabled")

                            anomalies = anomaly_detection_workdayless(
                                df, training_result, training_result["time_window"], bucket_value)

                        if anomalies[0].get("is_anomaly"):
                            print("=========================================================================================================================")
                            print(f"\033[31m anomaly detected: {anomalies} \033[0m")
                            print(
                                "=========================================================================================================================")

                            url_post = ANOMALIES_INSIGHT_URL + "insights/insertDocument/" + serie_to_detect["metadata"]["kbId"]
                            headers = {'Accept': 'application/json', "Content-Type": "application/json"}

                            # convert values that might be datetimes into ISO strings
                            ts = anomalies[0].get("timestamp")

                            if isinstance(ts, datetime):
                                # send UTC ISO 8601 string (add 'Z' or include tzinfo)
                                ts = ts.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

                            processed_data = {
                                'algorithm': 'Z Score',
                                'metric': serie_to_detect["metadata"]["dim"],
                                'text': "Anomaly detected",
                                'timestamp': ts,
                                'value': anomalies[0].get("value"),
                                'created_at': datetime.now(timezone.utc).replace(tzinfo=timezone.utc).isoformat().replace(
                                    "+00:00", "Z")
                            }

                            r = requests.post(url_post, json=processed_data, headers=headers)

                            print(r.status_code, r.text)
                            # for debugging, you can inspect what was actually sent:
                            print("REQUEST BODY:", r.request.body)  # will be a JSON string

        except PyMongoError as e:
            print(f"[watch_detection_changes] Mongo error: {e}, reconnecting in 5s...")
            time.sleep(5)
        except Exception as e:
            print(f"[watch_detection_changes] Unexpected error: {e}")
            traceback.print_exc()
            time.sleep(5)

def restartable_thread(target, *args, delay=5):
    """Runs the given target in a loop, restarting if it crashes."""
    while True:
        try:
            target(*args)
        except Exception as e:
            print(f"[{target.__name__}] crashed with {e}, restarting in {delay}s...")
            traceback.print_exc()
            time.sleep(delay)

def main():

    # Esto arma la conexión a MongoDB
    kb_client = CreateConnectionToKB()

    # aquí llamariamos a nuestra lógica para checkear la metadata para corroborar si ya hemos hechos
    # esta operativa antes

    # Start watcher in its own thread
    training_watcher = threading.Thread(
        target=restartable_thread, args=(watch_kb_changes,kb_client), daemon=True)

    detection_watcher = threading.Thread(
        target=restartable_thread,
        args=(watch_detection_changes,kb_client,),
        daemon=True
    )

    training_watcher.start()
    detection_watcher.start()

    try:
        while training_watcher.is_alive() or detection_watcher.is_alive():
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping watcher...")
        # Let it end naturally when Mongo closes or you implement a stop condition
        pass



if __name__ == "__main__":
    main()
