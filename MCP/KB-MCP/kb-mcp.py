#!/usr/bin/env python3
import json
import uuid
import datetime
import logging
from jsonschema import validate, ValidationError
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure
import uuid
import os
from datetime import datetime
from typing import Optional
from mcp.server.fastmcp import FastMCP
from croniter import croniter
from elasticsearch import Elasticsearch
from pydantic import BaseModel

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

mcp = FastMCP("KB-MCP")



#Classes ------------------------------------------------------------------------------------------------------

# Id GUID, Description, Query Elastic Query only
class KBConfig(BaseModel):
    id: str
    description: str
    query_elastic: str

    def __init__(self, **data):
        super().__init__(**data)
        # Validate ESQL query after initialization
        esql_obj = ESQL(self.query_elastic)  # This will raise ValueError if invalid
        self.query_elastic = esql_obj.value
        log_message(f"ESQL query validated for KB config {self.id}")

# CRON class moved before classes that use it
class CRON:
    def __init__(self, value: str):
        if not self._is_valid_cron(value):
            log_message(f"CRON validation failed: Invalid CRON format: {value}", "error")
            raise ValueError(f"Invalid CRON format: {value}")
        self.value = value
        log_message(f"CRON validated successfully: {value}", "info")

    @staticmethod
    def _is_valid_cron(cron_string: str) -> bool:
        try:
            croniter(cron_string)
            return True
        except Exception:
            return False

    def __str__(self):
        return self.value

    def __repr__(self):
        return f"CRON('{self.value}')"

# KB Configuration Classes

class schedulingTrainingConfig(BaseModel):
    '''
    Configuration class for scheduling training jobs.
    '''
    from_date: datetime
    to_date: datetime
    mode: str

class schedulingDetectionConfig(BaseModel):
    '''
    Configuration class for scheduling detection jobs.
    '''
    frequency: str  # Will store CRON value
    window: str     # Will store CRON value
    start: datetime
    mode: str

    def __init__(self, **data):
        # Handle CRON objects in initialization
        if 'frequency' in data and isinstance(data['frequency'], CRON):
            data['frequency'] = data['frequency'].value
        if 'window' in data and isinstance(data['window'], CRON):
            data['window'] = data['window'].value
        super().__init__(**data)


class DaAlgParameters(BaseModel):
    algorithms: list

    def to_dict(self):
        """
        Convert all algorithms to dictionary format.
        Each algorithm object should have a to_dict() method.
        """
        return {
            "algorithms": [alg.to_dict() for alg in self.algorithms]
        }


#list of Anomaly Detection Algorithms --------------------------------------------------------------------------

# Zscore, used for anomaly detection based on statistical deviations
class ZScore:
    def __init__(self, threshold: float, observed_value: str):
        self.threshold = threshold
        self.observed_value = observed_value

    def to_dict(self):
        return {
            "threshold": self.threshold,
            "observedValue": self.observed_value
        }
    
# Auxilary classes --------------------------------------------------------------------------------------------

# ESQL class for validating ESQL queries
class ESQL:
    def __init__(self, value: str):
        if not self._is_valid_esql(value):
            log_message(f"ESQL validation failed: Invalid ESQL format: {value}", "error")
            raise ValueError(f"Invalid ESQL format: {value}")
        self.value = value
        log_message(f"ESQL validated successfully: {value[:50]}...", "info")

    @staticmethod
    def _is_valid_esql(query: str) -> bool:
        # Try localhost first (for local development), then Docker service name
        es_hosts = ["http://localhost:9200", "http://elasticsearch-dataset:9200"]

        for host in es_hosts:
            try:
                log_message(f"Attempting ESQL validation with Elasticsearch at {host}")
                es = Elasticsearch(host)
                # Convert single quotes to double quotes for ESQL compatibility
                validation_query = query.replace("'", '"') + " | LIMIT 0"
                es.esql.query(query=validation_query)
                log_message(f"ESQL validation successful with {host}")
                return True
            except Exception as e:
                log_message(f"ESQL validation failed with {host}: {str(e)}", "warning")
                continue

        # If both hosts failed, do basic syntax validation
        log_message("ESQL validation error (Elasticsearch not available at localhost or docker service)", "warning")
        # Basic validation: check if it contains FROM and has reasonable structure
        if "FROM" not in query.upper():
            return False
        # Allow validation to pass for development if ES is not available
        log_message("ESQL validation bypassed (Elasticsearch not available) - basic syntax check passed", "info")
        return True

    def __str__(self):
        return self.value

    def __repr__(self):
        return f"ESQL('{self.value}')"


class UUID:
    def __init__(self, value: str):
        if not self._is_valid_uuid(value):
            log_message(f"UUID validation failed: Invalid UUID format: {value}")
            raise ValueError(f"Invalid UUID format: {value}")
        self.value = value
        log_message(f"UUID validated successfully: {value}")

    @staticmethod
    def _is_valid_uuid(uuid_str: str) -> bool:
        try:
            uuid.UUID(uuid_str)
            return True
        except ValueError:
            return False

    def __str__(self):
        return self.value

    def __repr__(self):
        return f"UUID('{self.value}')"


def log_message(message: str, level: str = "info"):
    """
    Logs a message to both console and logs/log.txt file.
    Creates the logs folder and file if they don't exist.
    """
    # Log to console with proper formatting
    if level.lower() == "error":
        logger.error(message)
    elif level.lower() == "warning":
        logger.warning(message)
    elif level.lower() == "debug":
        logger.debug(message)
    else:
        logger.info(message)

    # Also log to file
    logs_dir = os.path.join(os.path.dirname(__file__), "logs")
    os.makedirs(logs_dir, exist_ok=True)
    log_file = os.path.join(logs_dir, "log.txt")
    timestamp = datetime.now().isoformat()
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")
    
# Extractor modes enum
class ExtractorModes(str):
    BATCH = "batch"
    STREAMING = "streaming"

# MCP Tools ---------------------------------------------------------------------------------------------------

@mcp.tool()
def create_da_config(
    kb_config: KBConfig = KBConfig(
        id=str(uuid.uuid4()),
        description="Default HTTP monitoring configuration",
        query_elastic="FROM .ds-kibana_sample_data_logs-* | WHERE @timestamp >= '2025-10-01T00:00:00.000Z' AND @timestamp < '2025-11-01T00:00:00.000Z' | EVAL es_timestamp = DATE_TRUNC(1 hour, @timestamp) | STATS status_code_200_counter = COUNT(*) WHERE response == '200', status_code_5xx_counter = COUNT(*) WHERE response >= '500' AND response < '600' BY es_timestamp | SORT es_timestamp"
    ),
    scheduling_training_config: schedulingTrainingConfig = schedulingTrainingConfig(
        from_date=datetime.fromisoformat("2025-09-01T00:00:00"),
        to_date=datetime.fromisoformat("2025-09-30T23:59:59"),
        mode="batch"
    ),
    scheduling_detection_config: schedulingDetectionConfig = schedulingDetectionConfig(
        frequency=CRON("*/5 * * * *"),  # Every 5 minutes
        window=CRON("0 * * * *"),      # Every hour
        start=datetime.fromisoformat("2025-10-01T00:00:00"),
        mode="streaming"
    ),
    da_alg_parameters: DaAlgParameters = DaAlgParameters(algorithms=[
        ZScore(threshold=3.0, observed_value="status_code_200_counter"),
        ZScore(threshold=2.5, observed_value="status_code_5xx_counter")
    ])
) -> str:
    """
    Create a Data Analytics (DA) algorithm configuration for the Knowledge Base system.

    This function validates all input parameters and provides detailed error messages
    to help ensure correct configuration creation.

    Args:
        kb_config (KBConfig): Configuration containing ID, description, and validated ESQL query
        scheduling_training_config (schedulingTrainingConfig): Training period configuration
        scheduling_detection_config (schedulingDetectionConfig): Detection scheduling configuration  
        da_alg_parameters (DaAlgParameters): Data analytics algorithm parameters

    Returns:
        str: Validation success message with configuration preview, or detailed error message

    Raises:
        ValueError: If any validation fails with specific error details
    """
    
    validation_errors = []
    
    # Validate KB Config
    try:
        if not kb_config.id or not isinstance(kb_config.id, str):
            validation_errors.append("KB Config ID must be a non-empty string")
        if not kb_config.description or not isinstance(kb_config.description, str):
            validation_errors.append("KB Config description must be a non-empty string")
        # ESQL validation happens automatically in KBConfig setter
    except ValueError as e:
        validation_errors.append(f"KB Config ESQL validation failed: {str(e)}")
    
    # Validate Training Config
    try:
        if scheduling_training_config.from_date >= scheduling_training_config.to_date:
            validation_errors.append("Training 'from_date' must be before 'to_date'")
        if scheduling_training_config.mode not in ["batch", "streaming"]:
            validation_errors.append("Training mode must be 'batch' or 'streaming'")
    except AttributeError:
        validation_errors.append("Invalid scheduling_training_config object")
    
    # Validate Detection Config
    try:
        if scheduling_detection_config.mode not in ["batch", "streaming"]:
            validation_errors.append("Detection mode must be 'batch' or 'streaming'")
        # CRON validation happens automatically in schedulingDetectionConfig
    except AttributeError:
        validation_errors.append("Invalid scheduling_detection_config object")
    
    # Validate DA Algorithm Parameters
    try:
        if not da_alg_parameters.algorithms or len(da_alg_parameters.algorithms) == 0:
            validation_errors.append("At least one algorithm must be specified")
        for i, alg in enumerate(da_alg_parameters.algorithms):
            if not hasattr(alg, 'to_dict'):
                validation_errors.append(f"Algorithm {i} must have a to_dict() method")
    except AttributeError:
        validation_errors.append("Invalid da_alg_parameters object")
    
    # If validation failed, return detailed errors
    if validation_errors:
        error_msg = "Configuration validation failed:\n" + "\n".join(f"- {err}" for err in validation_errors)
        log_message(f"Configuration validation failed: {len(validation_errors)} errors")
        return error_msg
    
    # Build preview of configuration
    config_preview = {
        "KB_Config": {
            "Id": kb_config.id,
            "Description": kb_config.description,
            "Query_Elastic": {"query": kb_config.query_elastic},
            "Scheduling": {
                "TrainingPeriod": {
                    "from": scheduling_training_config.from_date.isoformat(),
                    "to": scheduling_training_config.to_date.isoformat(),
                    "mode": scheduling_training_config.mode
                },
                "Detection": {
                    "frequency": scheduling_detection_config.frequency,
                    "window": scheduling_detection_config.window,
                    "start": scheduling_detection_config.start.isoformat(),
                    "mode": scheduling_detection_config.mode
                }
            },
            "DA_Alg_Parameters": da_alg_parameters.to_dict()
        }
    }
    
    log_message(f"Configuration validation successful for ID: {kb_config.id}")
    return f"✅ Configuration validation successful!\n\nPreview:\n{json.dumps(config_preview, indent=2)}\n\nNext step: Implement MongoDB saving logic."
    
    # # Validate against JSON schema
    # schema_path = os.path.join(os.path.dirname(__file__), "kb_config_schema.json")
    # try:
    #     with open(schema_path, "r") as f:
    #         schema = json.load(f)
    #     validate(instance=config_data, schema=schema)
    #     log_message("Configuration validated successfully against schema")
    # except (FileNotFoundError, ValidationError) as e:
    #     error_msg = f"Schema validation failed: {str(e)}"
    #     log_message(error_msg)
    #     return error_msg
    
    # # Connect to MongoDB and save
    # try:
    #     client = MongoClient("mongodb://localhost:27017/")
    #     db = client["kb-mongodb"]
    #     collection = db["kb_configs"]
        
    #     result = collection.insert_one(config_data)
    #     log_message(f"Configuration saved to MongoDB with ID: {kb_config.id}")
        
    #     return f"Configuration saved successfully with ID: {kb_config.id}\n\n{json.dumps(config_data, indent=2)}"
        
    # except (ConnectionFailure, OperationFailure) as e:
    #     error_msg = f"Database operation failed: {str(e)}"
    #     log_message(error_msg)
    #     return error_msg
    # finally:
    #     if 'client' in locals():
    #         client.close()


if __name__ == "__main__":
    mcp.run()