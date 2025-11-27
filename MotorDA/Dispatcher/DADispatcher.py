import multiprocessing
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from queue import Queue

import requests
from datetime import datetime, timezone
from bson import json_util, ObjectId
from pymongo import MongoClient
import pandas as pd
from typing import Dict, Any, List, Optional
from elasticsearch import Elasticsearch
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

# Import Training Orchestrator for bucket-aware training
from Dispatcher.training_orchestrator import TrainingOrchestrator

# Import Series Orchestrator for SERIES algorithms (Phase 2)
from Dispatcher.series_orchestrator import SeriesTrainingOrchestrator, SeriesDetectionOrchestrator

# Import History Provider for SERIES algorithm detection (Phase 2)
from Dispatcher.history_provider import HistoryProvider, get_history_provider

# Import algorithm registry for dynamic algorithm lookup
from MotorDA.algorithm_registry import get_algorithm, is_algorithm_supported, list_algorithm_names
from MotorDA.base_algorithm import DetectionMode, BucketMode

# Dispatcher: Tiene como objetivo recibir el documento de configuración desde MongoDB y despachar la ejecución del algoritmo correspondiente.
# Tiene que en base al documento de configuración, identificar qué algoritmo se debe ejecutar y llamar a la función correspondiente,
# pasándole los parámetros necesarios. Y guardar los resultados en ElasticSearch.
# En la versión actual también consultaría el mongoDB que contiene la data de documentación para leer la metadata y saber si esta entrenando o no jeje.


# ----------------------------------- CONSTANT DECLARATION -------------------------------------------------------------------
# conexión a MongoDB
MONGO_KB_URL = "mongodb://admin:1q2w3E%2A@mongodb:27017/?authSource=admin"
MONGO_DB_NAME = "anomaly_detection"
TRAINING_COLLECTION_NAME = "training_config"
SERIES_COLLECTION_NAME = "series"
SERIES_RESULT_COLLECTION_NAME = "series_result"
MONGO_TIMEOUT_MS = 2000

# beaware it has a trailing slash
ANOMALIES_INSIGHT_URL = "http://anomalies-insights:8081/api/insights/"

# conexión a elasticSearch
ES_HOST = "http://elasticsearch-anomalies:9200"
ES_INDEX = "test_logs"

QUEUE_MAX_SIZE = 5000

elastic_client = Elasticsearch(ES_HOST)

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
        """Execute training for this algorithm.
        
        Uses the algorithm registry for both POINT and SERIES algorithms.
        - POINT algorithms: Use TrainingOrchestrator (bucket splitting)
        - SERIES algorithms: Use SeriesTrainingOrchestrator (continuous data)
        """
        algorithm_name = self.name.lower()
        
        # Check if algorithm is in the registry
        if is_algorithm_supported(algorithm_name):
            algorithm = get_algorithm(algorithm_name)
            
            # Fetch series data from MongoDB
            observed_values = fetch_series_data_with_aggregation(config, self)

            if not observed_values:
                print("\033[93m[DISPATCHER] No observed values to train on\033[0m")
                return

            # Route based on detection mode
            if algorithm.detection_mode == DetectionMode.SERIES:
                print(f"\033[92m[DISPATCHER] Executing SERIES algorithm '{algorithm_name}' via SeriesOrchestrator\033[0m")
                results = run_series_algorithm_training(config, algorithm_name, observed_values)
            else:
                print(f"\033[92m[DISPATCHER] Executing POINT algorithm '{algorithm_name}' via TrainingOrchestrator\033[0m")
                results = run_algorithm_bucketed_training(config, algorithm_name, observed_values)
            
            print(f"\033[92m[DISPATCHER] Training complete for {len(results)} dimensions\033[0m")
            delete_series(config)
            return
        
        # Legacy fallback for algorithms not yet in registry
        match algorithm_name:
            case "zscore":
                # This branch is now handled above, but kept for safety
                print("\033[92m[DISPATCHER] Executing Z-Score with bucket-aware training (legacy path)\033[0m")
                
                # Fetch series data from MongoDB
                observed_values = fetch_series_data_with_aggregation(config, self)

                if not observed_values:
                    print("\033[93m[DISPATCHER] No observed values to train on\033[0m")
                    return

                # Run bucket-aware training using TrainingOrchestrator
                results = run_zscore_bucketed_training(config, observed_values)
                
                print(f"\033[92m[DISPATCHER] Training complete for {len(results)} dimensions\033[0m")

            case "arma":
                print(f"\033[93m[DISPATCHER] TRAINING {self.name} - Register as SERIES algorithm in registry\033[0m")

            case _:
                supported = list_algorithm_names()
                print(f"\033[91m[DISPATCHER] Unknown algorithm: '{self.name}'. Supported: {supported}\033[0m")

        delete_series(config)



@dataclass
class Config:
    _id: str
    kb_id: str
    kb_description: str
    created_at: datetime
    mode: int
    algorithms: List[Algorithm]
    bucket_profile_id: Optional[str] = None  # Added for bucket-aware training

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


def parse_config(data: dict, mongo_client: MongoClient = None) -> Config:
    """Parse training_config document into Config object.
    
    Also fetches the KB config to get bucket_profile_id for bucket-aware training.
    """
    kb_id = data["kb_id"]
    bucket_profile_id = None
    
    # Fetch the KB config from knowledge_base.kb_configs to get bucket_profile_id
    if mongo_client:
        try:
            from bson import ObjectId
            kb_config = mongo_client["knowledge_base"]["kb_configs"].find_one({"_id": ObjectId(kb_id)})
            if kb_config:
                bucket_profile_id = kb_config.get("bucket_profile_id")
                print(f"\033[92m[DISPATCHER] KB config found, bucket_profile_id: {bucket_profile_id}\033[0m")
            else:
                print(f"\033[93m[DISPATCHER] KB config not found for kb_id: {kb_id}\033[0m")
        except Exception as e:
            print(f"\033[91m[DISPATCHER] Error fetching KB config: {e}\033[0m")
    
    return Config(
        _id=data["_id"],
        kb_id=kb_id,
        kb_description=data["kb_description"],
        created_at=data["created_at"],
        mode=data["mode"],
        bucket_profile_id=bucket_profile_id,

        algorithms=[
            Algorithm(
                name=a["name"].lower(),
                parameters=Parameters(
                    train_window=a["parameters"]["train_window"],
                    observed_values={
                        ov["dimension"]: {am["key"]: am.get("value", am.get("values", ""))
                                          for am in ov.get("algorithm_metadata", [])}
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


def run_zscore_bucketed_training(config: Config, observed_values: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
    """Run ZScore training with bucket-aware data grouping.
    
    This is the new training flow per the spec:
    1. Create TrainingOrchestrator with bucket profile
    2. For each dimension, group data by bucket key
    3. Train ZScore baseline per bucket
    4. Store results in trained_models (series_result) collection
    
    Args:
        config: The Config object with kb_id, bucket_profile_id, etc.
        observed_values: Dict mapping dimension -> DataFrame with value/timestamp columns
    
    Returns:
        Dict of dimension -> training result
    """
    da_client: MongoClient = CreateConnectionToDA()
    
    print(f"\033[92m[DISPATCHER] Running bucketed training for kb_id: {config.kb_id}\033[0m")
    print(f"\033[92m[DISPATCHER] Bucket profile: {config.bucket_profile_id}\033[0m")
    
    # Create TrainingOrchestrator with bucket profile
    orchestrator = TrainingOrchestrator.create(
        bucket_profile_id=config.bucket_profile_id,
        mongo_client=da_client,
        db_name=MONGO_DB_NAME
    )
    
    all_results: Dict[str, Any] = {}
    
    for dimension, df in observed_values.items():
        if df.empty:
            print(f"\033[93m[DISPATCHER] Skipping empty dimension: {dimension}\033[0m")
            continue
        
        print(f"\033[92m[DISPATCHER] Training dimension '{dimension}' with {len(df)} data points\033[0m")
        
        # Run bucket-aware training via orchestrator
        result = orchestrator.train_dimension(
            kb_id=config.kb_id,
            dimension=dimension,
            df_train=df,
            value_col="value",
            timestamp_col="timestamp",
            percentile=99.5,
            min_points=3
        )
        
        all_results[dimension] = result
        
        # Save to MongoDB (trained_models / series_result)
        query = {"kb_id": config.kb_id, "dimension": dimension}
        existing = da_client[MONGO_DB_NAME][SERIES_RESULT_COLLECTION_NAME].find_one(query)
        
        if existing:
            print(f"\033[93m[DISPATCHER] Updating existing training result for dimension: {dimension}\033[0m")
            da_client[MONGO_DB_NAME][SERIES_RESULT_COLLECTION_NAME].replace_one(query, result)
        else:
            print(f"\033[92m[DISPATCHER] Inserting new training result for dimension: {dimension}\033[0m")
            da_client[MONGO_DB_NAME][SERIES_RESULT_COLLECTION_NAME].insert_one(result)
    
    # Mark training as complete
    da_client[MONGO_DB_NAME][TRAINING_COLLECTION_NAME].update_one(
        {"kb_id": config.kb_id},
        {"$set": {"is_trained": True}}
    )
    
    print(f"\033[92m[DISPATCHER] Training complete for {len(all_results)} dimensions\033[0m")
    return all_results


def run_algorithm_bucketed_training(
    config: Config, 
    algorithm_name: str, 
    observed_values: Dict[str, pd.DataFrame]
) -> Dict[str, Any]:
    """Run any registered algorithm with bucket-aware data grouping.
    
    This is the NEW unified training flow using the algorithm registry:
    1. Create TrainingOrchestrator with bucket profile
    2. For each dimension, train using the specified algorithm
    3. Store results in trained_models (series_result) collection
    
    Args:
        config: The Config object with kb_id, bucket_profile_id, etc.
        algorithm_name: Name of algorithm in registry (e.g., "zscore", "iqr")
        observed_values: Dict mapping dimension -> DataFrame with value/timestamp columns
    
    Returns:
        Dict of dimension -> training result
    """
    da_client: MongoClient = CreateConnectionToDA()
    
    print(f"\033[92m[DISPATCHER] Running '{algorithm_name}' bucketed training for kb_id: {config.kb_id}\033[0m")
    print(f"\033[92m[DISPATCHER] Bucket profile: {config.bucket_profile_id}\033[0m")
    
    # Create TrainingOrchestrator with bucket profile
    orchestrator = TrainingOrchestrator.create(
        bucket_profile_id=config.bucket_profile_id,
        mongo_client=da_client,
        db_name=MONGO_DB_NAME
    )
    
    all_results: Dict[str, Any] = {}
    
    for dimension, df in observed_values.items():
        if df.empty:
            print(f"\033[93m[DISPATCHER] Skipping empty dimension: {dimension}\033[0m")
            continue
        
        print(f"\033[92m[DISPATCHER] Training dimension '{dimension}' with algorithm '{algorithm_name}' and {len(df)} data points\033[0m")
        
        # Run bucket-aware training via orchestrator with specified algorithm
        result = orchestrator.train_dimension_with_algorithm(
            kb_id=config.kb_id,
            dimension=dimension,
            algorithm_name=algorithm_name,
            df_train=df,
            value_col="value",
            timestamp_col="timestamp",
            metadata={"percentile": 99.5, "min_points": 3}  # Default params, could come from config
        )
        
        all_results[dimension] = result
        
        # Save to MongoDB (trained_models / series_result)
        query = {"kb_id": config.kb_id, "dimension": dimension}
        existing = da_client[MONGO_DB_NAME][SERIES_RESULT_COLLECTION_NAME].find_one(query)
        
        if existing:
            print(f"\033[93m[DISPATCHER] Updating existing training result for dimension: {dimension}\033[0m")
            da_client[MONGO_DB_NAME][SERIES_RESULT_COLLECTION_NAME].replace_one(query, result)
        else:
            print(f"\033[92m[DISPATCHER] Inserting new training result for dimension: {dimension}\033[0m")
            da_client[MONGO_DB_NAME][SERIES_RESULT_COLLECTION_NAME].insert_one(result)
    
    # Mark training as complete
    da_client[MONGO_DB_NAME][TRAINING_COLLECTION_NAME].update_one(
        {"kb_id": config.kb_id},
        {"$set": {"is_trained": True, "algorithm": algorithm_name}}
    )
    
    print(f"\033[92m[DISPATCHER] Training complete for {len(all_results)} dimensions using '{algorithm_name}'\033[0m")
    return all_results


def run_series_algorithm_training(
    config: Config,
    algorithm_name: str,
    observed_values: Dict[str, List[float]],
    bucket_profile: Optional[Dict] = None
) -> Dict[str, Any]:
    """
    Train SERIES algorithms (like ARMA/LSTM) that operate on continuous time series.
    
    Unlike POINT algorithms, SERIES algorithms:
    - Train on the full time series without bucket segmentation
    - Learn temporal patterns and dependencies
    - Use bucket info as a FEATURE (input to model) rather than data splitter
    
    Args:
        config: Training configuration with kb_id and parameters
        algorithm_name: Name of the algorithm (e.g., "arma", "lstm")
        observed_values: Dictionary mapping dimension names to their time series values
        bucket_profile: Optional bucket profile for adding bucket features
        
    Returns:
        Dictionary with training results per dimension
    """
    print(f"\033[96m[DISPATCHER] Running SERIES training with algorithm: {algorithm_name}\033[0m")
    
    da_client: MongoClient = CreateConnectionToDA()
    
    # Get algorithm from registry
    algorithm_instance = get_algorithm(algorithm_name)
    if algorithm_instance is None:
        raise ValueError(f"Unknown algorithm: {algorithm_name}")
    
    # Check it's actually a SERIES algorithm
    if algorithm_instance.detection_mode != DetectionMode.SERIES:
        raise ValueError(f"Algorithm '{algorithm_name}' is not a SERIES algorithm (mode: {algorithm_instance.detection_mode})")
    
    # Create the series training orchestrator using factory method
    orchestrator = SeriesTrainingOrchestrator.create(
        bucket_profile_id=bucket_profile,
        mongo_client=da_client,
        db_name=MONGO_DB_NAME
    )
    
    all_results = {}
    
    for dimension, df in observed_values.items():
        print(f"\033[94m[DISPATCHER] Training dimension '{dimension}' with {len(df)} values\033[0m")
        
        # The observed_values already contains DataFrames with 'timestamp' and 'value' columns
        # from fetch_series_data_with_aggregation, so we use them directly
        
        # Run training via series orchestrator
        result = orchestrator.train_dimension(
            kb_id=config.kb_id,
            dimension=dimension,
            algorithm_name=algorithm_name,
            df_train=df,
            value_col="value",
            timestamp_col="timestamp",
            metadata={"percentile": 99.5}  # Default params
        )
        
        all_results[dimension] = result
        
        # Save to MongoDB
        query = {"kb_id": config.kb_id, "dimension": dimension}
        existing = da_client[MONGO_DB_NAME][SERIES_RESULT_COLLECTION_NAME].find_one(query)
        
        if existing:
            print(f"\033[93m[DISPATCHER] Updating SERIES training result for: {dimension}\033[0m")
            da_client[MONGO_DB_NAME][SERIES_RESULT_COLLECTION_NAME].replace_one(query, result)
        else:
            print(f"\033[92m[DISPATCHER] Inserting SERIES training result for: {dimension}\033[0m")
            da_client[MONGO_DB_NAME][SERIES_RESULT_COLLECTION_NAME].insert_one(result)
    
    # Mark training as complete
    da_client[MONGO_DB_NAME][TRAINING_COLLECTION_NAME].update_one(
        {"kb_id": config.kb_id},
        {"$set": {"is_trained": True, "algorithm": algorithm_name, "algorithm_type": "SERIES"}}
    )
    
    print(f"\033[92m[DISPATCHER] SERIES training complete for {len(all_results)} dimensions\033[0m")
    return all_results


def delete_series( config: Config):

    da_client: MongoClient = CreateConnectionToDA()

    query =  {'metadata.kbId': config.kb_id,
            'metadata.mode': int(config.mode) } # Use mode as-is (integer)

    print("WE'RE DELETING SERIES AFTER TRAINING")
    # we delete the data we used to train
    result =da_client[MONGO_DB_NAME][SERIES_COLLECTION_NAME].delete_many(query)
    print(result)

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
    #date_from = algorithm_to_execute.parameters.from_
    #date_to = algorithm_to_execute.parameters.to

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

        # Build aggregation pipeline
        match_query = {
            'metadata.kbId': kb_id,
            'metadata.dim': dimension,
            'metadata.mode': int(mode)  # Use mode as-is (integer)
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
            test_query['metadata.mode'] = "0"
            count_with_mode = series_collection.count_documents(test_query)
            print(
                f"  DEBUG: Documents with all filters (no timestamp): {count_with_mode}")

            # Check with timestamp
            """
            if date_from and date_to:
                test_query['timestamp'] = {
                    '$gte': date_from, '$lte': date_to}
                count_with_timestamp = series_collection.count_documents(
                    test_query)
                print(
                    f"  DEBUG: Documents with all filters (WITH timestamp): {count_with_timestamp}")
            """
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
            # Use fullDocument to get the inserted document directly from the change event
            with kb_client[MONGO_DB_NAME][TRAINING_COLLECTION_NAME].watch(
                full_document='updateLookup'
            ) as stream:

                for change in stream:
                    print(f"something happened on: {TRAINING_COLLECTION_NAME}")

                    op_type = change.get("operationType")
                    
                    # Only process insert operations - skip updates to avoid race condition
                    # Updates occur when we set is_trained=true after training completes
                    if op_type == "insert":
                        print(
                            f"\033[31m Someone inserted data into: {TRAINING_COLLECTION_NAME} \033[0m")

                        # Get the document directly from the change event instead of querying
                        # This ensures we process the exact document that triggered the event
                        full_doc = change.get("fullDocument")
                        if not full_doc:
                            print(f"\033[93m[DISPATCHER] No fullDocument in change event, falling back to query\033[0m")
                            full_doc = ExtractLatestConfigurationKB(kb_client)
                        
                        # Check if already trained to avoid duplicate processing
                        # Handle both boolean True and string "true"
                        is_trained = full_doc.get("is_trained")
                        print(f"\033[90m[DISPATCHER] is_trained value: {is_trained} (type: {type(is_trained).__name__})\033[0m")
                        if is_trained in (True, "true", "True"):
                            print(f"\033[93m[DISPATCHER] Skipping already-trained config: {full_doc.get('kb_id')}\033[0m")
                            continue

                        print(f"\033[92m[DISPATCHER] Processing training_config for kb_id: {full_doc.get('kb_id')}\033[0m")
                        print(full_doc)
                        
                        # Save config to file for debugging
                        with open("Series_Mongo_Result.json", "w", encoding="utf-8") as f:
                            f.write(json_util.dumps(full_doc, indent=2))

                        # we turn the JSON with the config data into a class
                        # Pass mongo_client so parse_config can fetch KB config for bucket_profile_id
                        config: Config = parse_config(full_doc, kb_client)

                        # now we go thru each algorithm call we extracted, and try to execute training on them
                        config.execute_algos()
                    
                    elif op_type == "update":
                        print(f"\033[90m[DISPATCHER] Ignoring update event (likely is_trained flag change)\033[0m")

        except PyMongoError as e:
            print(f"[watch_kb_changes] Mongo error: {e}, reconnecting in 5s...")
            time.sleep(5)

        except Exception as e:
            print(f"[watch_kb_changes] Unexpected error: {e}")
            traceback.print_exc()
            time.sleep(5)



# TODO: test how robust it is this with a lot of different datapoints sent at the same time
# TODO: check how change stream works with threads
def watch_detection_changes(kb_client, workers: ThreadPoolExecutor, data_to_detect: Queue):

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
                        
                        # Route to appropriate detection function based on algorithm type
                        kb_id = serie_to_detect.get("metadata", {}).get("kbId")
                        if kb_id:
                            # Look up the algorithm type from training config
                            try:
                                training_config = kb_client[MONGO_DB_NAME][TRAINING_COLLECTION_NAME].find_one({"kb_id": kb_id})
                                if training_config:
                                    # Get algorithm name from algorithms array
                                    algorithms = training_config.get("algorithms", [])
                                    algorithm_name = algorithms[0].get("name", "zscore") if algorithms else "zscore"
                                    algorithm_class = get_algorithm(algorithm_name)
                                    
                                    if algorithm_class and algorithm_class.detection_mode == DetectionMode.SERIES:
                                        print(f"\033[96m[DETECTION] Routing to SERIES detection for {algorithm_name}\033[0m")
                                        workers.submit(detect_series_algorithm, serie_to_detect)
                                    else:
                                        # Default to Z-score (POINT) detection
                                        workers.submit(detect_z_score, (serie_to_detect))
                                else:
                                    # No config found, use default
                                    workers.submit(detect_z_score, (serie_to_detect))
                            except Exception as e:
                                print(f"\033[93m[DETECTION] Error determining algorithm type: {e}, using default\033[0m")
                                workers.submit(detect_z_score, (serie_to_detect))
                        else:
                            workers.submit(detect_z_score, (serie_to_detect))

        except PyMongoError as e:
            print(f"[watch_detection_changes] Mongo error: {e}, reconnecting in 5s...")
            time.sleep(5)

        except Exception as e:

            print(f"[watch_detection_changes] Unexpected error: {e}")
            traceback.print_exc()
            time.sleep(5)


def detect_series_algorithm(serie_to_detect: Dict[str, Any]) -> None:
    """
    Detection function for SERIES algorithms (ARMA, LSTM, etc.).
    
    Unlike POINT detection, SERIES detection:
    - Fetches historical values via HistoryProvider
    - Passes the full window (history + current) to the algorithm
    - Algorithm predicts next value and compares to actual
    
    Args:
        serie_to_detect: Detection data from MongoDB change stream
    """
    try:
        print(f"\033[96m[SERIES DETECTION] Processing: {serie_to_detect}\033[0m", flush=True)
        
        kb_client = CreateConnectionToDA()
        
        kb_id = serie_to_detect["metadata"]["kbId"]
        dimension = serie_to_detect["metadata"]["dim"]
        value = serie_to_detect.get("value", 0)
        timestamp = serie_to_detect.get("timestamp")
        
        # Ensure timestamp is datetime
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        
        print(f"\033[94m[SERIES DETECTION] kb_id={kb_id}, dimension={dimension}\033[0m", flush=True)
        
        # Lookup training config (using kb_id as string, not ObjectId)
        training_config = kb_client[MONGO_DB_NAME][TRAINING_COLLECTION_NAME].find_one({"kb_id": kb_id})
        if not training_config:
            print(f"\033[91m[SERIES DETECTION] Training config not found for {kb_id}\033[0m")
            return
        
        # Also lookup KB config for kb_name and source_index from knowledge_base.kb_configs
        kb_config = kb_client["knowledge_base"]["kb_configs"].find_one({"_id": ObjectId(kb_id)})
        kb_name = kb_config.get("name", "Unknown") if kb_config else training_config.get("kb_description", "Unknown")
        source_index = kb_config.get("source_index", None) if kb_config else None
        
        algorithms = training_config.get("algorithms", [])
        algorithm_name = algorithms[0].get("name", "unknown") if algorithms else "unknown"
        
        # Get the training result to find model parameters
        pipeline = [{'$match': {'kb_id': kb_id, 'dimension': dimension}}]
        result = kb_client[MONGO_DB_NAME][SERIES_RESULT_COLLECTION_NAME].aggregate(pipeline)
        training_result = next(result, None)
        
        if training_result is None:
            print(f"\033[93m[SERIES DETECTION] No training result for kb_id={kb_id}, dim={dimension}\033[0m")
            return
        
        # Get algorithm from registry
        algorithm_class = get_algorithm(algorithm_name)
        if algorithm_class is None:
            print(f"\033[91m[SERIES DETECTION] Unknown algorithm: {algorithm_name}\033[0m")
            return
        
        # Get required history length from algorithm
        history_length = getattr(algorithm_class, 'required_history_length', 10)  # Default 10 if not specified
        
        # Initialize history provider and cache
        history_provider = get_history_provider(kb_client, MONGO_DB_NAME)
        
        # Fetch historical values
        print(f"\033[94m[SERIES DETECTION] Fetching {history_length} historical values before timestamp={timestamp}\033[0m")
        history_window = history_provider.get_history(
            kb_id=kb_id,
            dimension=dimension,
            before_timestamp=timestamp,
            window_size=history_length
        )
        
        print(f"\033[94m[SERIES DETECTION] Got {len(history_window.values)} values from history provider\033[0m")
        
        if len(history_window.values) < history_length:
            print(f"\033[93m[SERIES DETECTION] Insufficient history: {len(history_window.values)}/{history_length}\033[0m")
            return
        
        # Algorithm from registry is already an instance
        algorithm_instance = algorithm_class
        
        # Check for bucket profile (used as FEATURE)
        bucket_profile_id = training_result.get("bucket_profile_id")
        bucket_features = None
        
        if bucket_profile_id and timestamp:
            try:
                from Dispatcher.bucket_resolver import BucketResolver
                profile_doc = kb_client[MONGO_DB_NAME]["bucket_profiles"].find_one({"_id": bucket_profile_id})
                if profile_doc:
                    resolver = BucketResolver.from_dict(profile_doc)
                    bucket_key = resolver.resolve(timestamp)
                    # Convert bucket key to features (e.g., one-hot encoding)
                    bucket_features = {"bucket_key": bucket_key}
            except Exception as e:
                print(f"\033[93m[SERIES DETECTION] Could not resolve bucket: {e}\033[0m")
        
        # Create SeriesDetectionOrchestrator via factory method
        orchestrator = SeriesDetectionOrchestrator.create(
            bucket_profile_id=bucket_profile_id,
            baseline=training_result,  # Pass the whole training result as baseline
            mongo_client=kb_client,
            db_name=MONGO_DB_NAME
        )
        
        # Convert history to list format expected by algorithm
        history_list = history_window.to_list()
        
        # Run detection using the orchestrator's detect method
        detection_result = orchestrator.detect(
            value=value,
            timestamp=timestamp,
            history=history_list,
            algorithm_name=algorithm_name,
            metadata={}
        )
        
        is_anomaly = detection_result.get("is_anomaly", False)
        predicted_value = detection_result.get("predicted_value", value)
        error = detection_result.get("prediction_error", 0)  # Fixed: was "error", should be "prediction_error"
        threshold = detection_result.get("threshold", 0)
        
        print(f"\033[94m[SERIES DETECTION] value={value}, predicted={predicted_value:.2f}, error={error:.2f}, is_anomaly={is_anomaly}\033[0m")
        
        if is_anomaly:
            print("\033[31m=========================================================================================================================\033[0m")
            print(f"\033[31m SERIES ANOMALY DETECTED: {dimension} = {value} (predicted: {predicted_value:.2f})\033[0m")
            print("\033[31m=========================================================================================================================\033[0m")
            
            # Convert timestamp to ISO string
            ts = timestamp
            if isinstance(ts, datetime):
                ts = ts.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            
            url_post = ANOMALIES_INSIGHT_URL + "dashboard/" + kb_id + "/anomalies"
            headers = {'Accept': 'application/json', "Content-Type": "application/json"}
            
            processed_data = {
                'algorithm': f'{algorithm_name.upper()} (Series)',
                'metric': dimension,
                'text': f"Series anomaly: actual {value:.2f} vs predicted {predicted_value:.2f} (error: {error:.2f})",
                'timestamp': ts,
                'value': value,
                'created_at': datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                'kb_name': kb_name,
                'source_index': source_index,
                'bucket_key': bucket_features.get("bucket_key") if bucket_features else None,
                'bucket_profile_id': bucket_profile_id,
                'algorithm_details': {
                    'predicted_value': predicted_value,
                    'prediction_error': error,
                    'threshold': threshold,
                    'history_length': history_length,
                    'algorithm_type': 'SERIES',
                }
            }
            
            try:
                response = requests.post(url_post, json=processed_data, headers=headers)
                print(f"\033[92m[SERIES DETECTION] Anomaly posted: {response.status_code}\033[0m")
            except Exception as e:
                print(f"\033[91m[SERIES DETECTION] Failed to post anomaly: {e}\033[0m")
                
    except Exception as e:
        print(f"\033[91m[SERIES DETECTION] EXCEPTION: {e}\033[0m", flush=True)
        import traceback
        traceback.print_exc()


def detect_z_score(serie_to_detect):
    try:
        print(f"I am printing serie_to_detect: {serie_to_detect}", flush=True)
        kb_client = CreateConnectionToDA()

        kb_id = serie_to_detect["metadata"]["kbId"]
        dimension = serie_to_detect["metadata"]["dim"]
        print(f"[DETECTION] Got kb_id={kb_id}, dimension={dimension}", flush=True)

        # Look up KB config from knowledge_base.kb_configs for name and source_index
        print(f"[DETECTION] Looking up KB config...", flush=True)
        kb_config = kb_client["knowledge_base"]["kb_configs"].find_one({"_id": ObjectId(kb_id)})
        kb_name = kb_config.get("name", "Unknown") if kb_config else "Unknown"
        source_index = kb_config.get("source_index", None) if kb_config else None
        print(f"\033[94m[DETECTION] KB Name: {kb_name}, KB ID: {kb_id}, Source Index: {source_index}\033[0m", flush=True)

        pipeline = [{'$match':
                         {'kb_id': kb_id,
                          'dimension': dimension}
                     }]

        print(f"[DETECTION] Looking up training result...", flush=True)
        result = kb_client[MONGO_DB_NAME][SERIES_RESULT_COLLECTION_NAME].aggregate(
            pipeline)

        training_result = next(result, None)
        print(f"[DETECTION] Training result: {training_result is not None}", flush=True)
    
        if training_result is None:
            print(f"\033[93m[DETECTION] No training result found for kb_id={serie_to_detect['metadata']['kbId']}, dim={serie_to_detect['metadata']['dim']}\033[0m")
            return
    
        # Check if this is the NEW bucket-based training result format
        if "buckets" in training_result:
            # NEW FORMAT: Use bucket-aware detection
            print(f"\033[92m[DETECTION] Using bucket-aware detection for {serie_to_detect['metadata']['dim']}\033[0m")
            
            value = serie_to_detect.get("value", 0)
            timestamp = serie_to_detect.get("timestamp")
            
            # Try to resolve the bucket key using BucketResolver
            bucket_key = "global_default"
            bucket_profile_id = training_result.get("bucket_profile_id")
            
            if bucket_profile_id and timestamp:
                try:
                    from Dispatcher.bucket_resolver import BucketResolver
                    # Fetch bucket profile from MongoDB
                    profile_doc = kb_client[MONGO_DB_NAME]["bucket_profiles"].find_one({"_id": bucket_profile_id})
                    if profile_doc:
                        resolver = BucketResolver.from_dict(profile_doc)
                        # Ensure timestamp is datetime
                        if isinstance(timestamp, datetime):
                            bucket_key = resolver.resolve(timestamp)
                        print(f"\033[94m[DETECTION] Resolved bucket key: {bucket_key}\033[0m")
                except Exception as e:
                    print(f"\033[93m[DETECTION] Could not resolve bucket, using fallback: {e}\033[0m")
            
            # Get the baseline for the resolved bucket, or fall back to global
            baseline = None
            baseline_source = "unknown"
            
            if bucket_key in training_result.get("buckets", {}):
                baseline = training_result["buckets"][bucket_key]
                baseline_source = f"bucket:{bucket_key}"
            elif training_result.get("global_fallback"):
                baseline = training_result["global_fallback"]
                baseline_source = "global_fallback"
                bucket_key = "global_fallback"
            elif training_result.get("buckets"):
                # Use first available bucket as last resort
                first_key = next(iter(training_result["buckets"]))
                baseline = training_result["buckets"][first_key]
                baseline_source = f"first_bucket:{first_key}"
                bucket_key = first_key
            
            if not baseline:
                print(f"\033[91m[DETECTION] No baseline found in training result\033[0m")
                return
            
            mean = baseline.get("mean", 0)
            std = baseline.get("std", 1)
            threshold = baseline.get("threshold", 3.0)
            data_points = baseline.get("data_points", 0)
            percentile = baseline.get("percentile", 99.5)
            
            # Calculate z-score
            if std == 0:
                z_score = 0.0
            else:
                z_score = abs(value - mean) / std
            
            is_anomaly = z_score > threshold
            
            print(f"\033[94m[DETECTION] bucket={bucket_key}, value={value}, mean={mean:.2f}, std={std:.2f}, z_score={z_score:.2f}, threshold={threshold:.2f}, is_anomaly={is_anomaly}\033[0m")
            
            if is_anomaly:
                print("\033[31m=========================================================================================================================\033[0m")
                print(f"\033[31m ANOMALY DETECTED: {dimension} = {value} (z-score: {z_score:.2f})\033[0m")
                print("\033[31m=========================================================================================================================\033[0m")
                
                # Convert timestamp to ISO string
                ts = timestamp
                if isinstance(ts, datetime):
                    ts = ts.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
                
                url_post = ANOMALIES_INSIGHT_URL + "dashboard/" + kb_id + "/anomalies"
                headers = {'Accept': 'application/json', "Content-Type": "application/json"}
                
                # Build context-aware anomaly description
                context_desc = f"Anomaly in bucket '{bucket_key}'"
                if bucket_key.startswith("workday_"):
                    hour = bucket_key.split("_")[1]
                    context_desc = f"Workday anomaly at hour {hour}"
                elif bucket_key.startswith("off_hours_"):
                    hour = bucket_key.split("_")[2] if len(bucket_key.split("_")) > 2 else "unknown"
                    context_desc = f"Off-hours anomaly at hour {hour}"
                elif bucket_key.startswith("weekend"):
                    context_desc = "Weekend anomaly"
                elif bucket_key.startswith("holiday"):
                    context_desc = f"Holiday anomaly ({bucket_key})"
                elif bucket_key == "global_fallback" or bucket_key == "global_default":
                    context_desc = "Anomaly (no time-context profile)"
                
                processed_data = {
                    # Core fields
                    'algorithm': 'Z Score (Bucketed)',
                    'metric': dimension,
                    'text': f"{context_desc}: z-score {z_score:.2f} exceeds threshold {threshold:.2f}",
                    'timestamp': ts,
                    'value': value,
                    'created_at': datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                    # KB identification
                    'kb_name': kb_name,
                    'source_index': source_index,
                    # Bucket context
                    'bucket_key': bucket_key,
                    'bucket_profile_id': bucket_profile_id,
                    # Algorithm-specific details (flexible for any algorithm)
                    'algorithm_details': {
                        'z_score': z_score,
                        'threshold': threshold,
                        'mean': mean,
                        'std': std,
                        'baseline_data_points': data_points,
                        'percentile': percentile,
                        'baseline_source': baseline_source,
                        'deviation_from_mean': value - mean,
                    }
                }
                
                try:
                    response = requests.post(url_post, json=processed_data, headers=headers)
                    print(f"\033[92m[DETECTION] Anomaly posted to insights API: {response.status_code}\033[0m")
                except Exception as e:
                    print(f"\033[91m[DETECTION] Failed to post anomaly: {e}\033[0m")
            
            return
    
        # OLD FORMAT: Legacy detection code
        print(f"\033[93m[DETECTION] Using legacy detection format\033[0m")

        # 2) flatten nested fields (metadata -> metadata.kbId etc.)
        df = pd.json_normalize(serie_to_detect)

        # optional: rename for convenience
        df = df.rename(columns={
            "metadata.kbId": "kbId",
            "metadata.dim": "dim",
            "metadata.mode": "mode"
        })

        # 3) make _id string (pandas doesn't like ObjectId)
        if "_id" in df.columns:
            df["_id"] = df["_id"].astype(str)

        # 4) ensure timestamp is datetime dtype
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"])

        if training_result["work_day_enabled?"]:

            # we add a boolean to know if it's a workday or not
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
            print(
                "=========================================================================================================================")
            print(f"\033[31m anomaly detected: {anomalies} \033[0m")
            print(
                "=========================================================================================================================")

            url_post = ANOMALIES_INSIGHT_URL + "dashboard/" + serie_to_detect["metadata"]["kbId"] + "/anomalies"
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

            requests.post(url_post, json=processed_data, headers=headers)
    except Exception as e:
        print(f"\033[91m[DETECTION] EXCEPTION in detect_z_score: {e}\033[0m", flush=True)
        import traceback
        traceback.print_exc()


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
    """Main function. It creates 2 watchers, one for training (listens to Mongo's anomaly_detection -> training_config) and one for detection (listens to Mongo's anomaly_detection -> series)."""
    # Esto arma la conexión a MongoDB
    kb_client = CreateConnectionToKB()

    data_to_detect: Queue = Queue(maxsize=QUEUE_MAX_SIZE)

    # we automatically use max amount of (Cores - 1) and then create workers
    num_cpu_workers = max(1, multiprocessing.cpu_count() - 1)

    workers : ThreadPoolExecutor = ThreadPoolExecutor()
    #workers : ThreadPoolExecutor = ThreadPoolExecutor(50)

    # Start watcher in its own thread
    training_watcher = threading.Thread(
        target=restartable_thread,
        args=(watch_kb_changes,kb_client),
        daemon=True)

    detection_watcher = threading.Thread(
        target=restartable_thread,
        args=(watch_detection_changes,kb_client, workers, data_to_detect),
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
