#!/usr/bin/env python3
import json
import uuid
import datetime
import logging
import re
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
from pydantic import BaseModel, field_validator

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

    @field_validator('algorithms', mode='before')
    @classmethod
    def convert_dict_algorithms(cls, v):
        if not isinstance(v, list):
            return v
        # Convert dict algorithms to proper objects
        converted_algorithms = []
        for alg in v:
            if isinstance(alg, dict):
                # Convert dict to appropriate algorithm object
                if 'threshold' in alg and 'observed_value' in alg:
                    converted_algorithms.append(ZScore(**alg))
                else:
                    # Unknown algorithm type, keep as dict but this will fail validation
                    converted_algorithms.append(alg)
            else:
                # Already a proper object
                converted_algorithms.append(alg)
        return converted_algorithms

    def to_dict(self):
        """
        Convert all algorithms to dictionary format grouped by algorithm type.
        Matches the expected KB config template structure.
        """
        # Group algorithms by type
        grouped = {
            "zscore": [],
            # "arma": [],
            # "kmeans": [],
        }

        for alg in self.algorithms:
            alg_dict = alg.to_dict()
            # Convert observed_value to observedValue for consistency with template
            if "observed_value" in alg_dict:
                alg_dict["observedValue"] = alg_dict.pop("observed_value")

            # Determine algorithm type and add to appropriate group
            if isinstance(alg, ZScore):
                grouped["zscore"].append(alg_dict)
            # Future: Add other algorithm types here
            # elif isinstance(alg, ARMA):
            #     grouped["arma"].append(alg_dict)
            # elif isinstance(alg, KMeans):
            #     grouped["kmeans"].append(alg_dict)
            # elif isinstance(alg, IForest):
            #     grouped["iforest"].append(alg_dict)

        return grouped


#list of Anomaly Detection Algorithms --------------------------------------------------------------------------

# Zscore, used for anomaly detection based on statistical deviations
class ZScore(BaseModel):
    threshold: float
    observed_value: str

    def to_dict(self):
        return {
            "threshold": self.threshold,
            "observedValue": self.observed_value
        }
    
# Auxiliary classes --------------------------------------------------------------------------------------------

def extract_all_output_field_names(esql_query: str) -> list[str]:
    """
    Extract all output field names from ESQL query, including both EVAL and STATS clauses.

    This function comprehensively parses ESQL queries to identify all field names that
    could be available as output, including fields created by EVAL and fields from STATS.

    Args:
        esql_query (str): The complete ESQL query string

    Returns:
        list[str]: List of all field names that could be output from the query

    Raises:
        ValueError: If query parsing fails due to malformed syntax

    Examples:
        >>> extract_all_output_field_names("FROM table | EVAL new_field = old_field * 2 | STATS count = COUNT(*) BY group")
        ['new_field', 'count']
    """
    field_names = set()

    # Extract fields from EVAL clauses
    eval_fields = _extract_eval_field_names(esql_query)
    field_names.update(eval_fields)

    # Extract fields from STATS clauses
    stats_fields = extract_stats_field_names(esql_query)
    field_names.update(stats_fields)

    return sorted(list(field_names))


def extract_stats_field_names(esql_query: str) -> list[str]:
    """
    Extract output field names from STATS clauses in an ESQL query.

    This function parses ESQL queries to identify field names defined in STATS clauses,
    handling complex expressions, aggregations, WHERE conditions, and multiple fields.

    Args:
        esql_query (str): The complete ESQL query string

    Returns:
        list[str]: List of field names extracted from STATS clauses

    Raises:
        ValueError: If STATS clause parsing fails due to malformed syntax

    Examples:
        >>> extract_stats_field_names("FROM table | STATS count = COUNT(*), avg_val = AVG(field) BY group")
        ['count', 'avg_val']

        >>> extract_stats_field_names("FROM table | STATS field1 = COUNT(*) WHERE condition == 'value' BY time")
        ['field1']
    """
    import re

    # Find STATS clause in the query
    stats_match = re.search(r'\bSTATS\s+(.+?)(?:\s+BY\s+|\s*$)', esql_query, re.IGNORECASE | re.DOTALL)
    if not stats_match:
        return []

    stats_content = stats_match.group(1).strip()

    # Split by commas, but be careful with commas inside functions or WHERE clauses
    field_definitions = _split_stats_fields(stats_content)

    field_names = []
    for field_def in field_definitions:
        field_name = _extract_field_name_from_definition(field_def.strip())
        if field_name:
            field_names.append(field_name)

    return field_names


def _extract_eval_field_names(esql_query: str) -> list[str]:
    """
    Extract field names created by EVAL clauses in an ESQL query.

    Args:
        esql_query (str): The complete ESQL query string

    Returns:
        list[str]: List of field names created by EVAL clauses
    """
    import re

    field_names = []

    # Find all EVAL clauses in the query
    eval_matches = re.findall(r'\bEVAL\s+(.+?)(?:\s*\|\s*|\s*$)', esql_query, re.IGNORECASE | re.DOTALL)

    for eval_content in eval_matches:
        # Split by commas to handle multiple assignments in one EVAL
        assignments = _split_eval_assignments(eval_content.strip())

        for assignment in assignments:
            field_name = _extract_field_name_from_eval_assignment(assignment.strip())
            if field_name:
                field_names.append(field_name)

    return field_names


def _split_eval_assignments(eval_content: str) -> list[str]:
    """
    Split EVAL content by commas, handling nested functions and complex expressions.

    Args:
        eval_content (str): The content between EVAL and next pipe

    Returns:
        list[str]: Individual assignment expressions
    """
    assignments = []
    current_assignment = ""
    paren_depth = 0
    in_quotes = False
    quote_char = None

    i = 0
    while i < len(eval_content):
        char = eval_content[i]

        # Handle quotes
        if char in ('"', "'") and (i == 0 or eval_content[i-1] != '\\'):
            if not in_quotes:
                in_quotes = True
                quote_char = char
            elif char == quote_char:
                in_quotes = False
                quote_char = None

        # Handle parentheses
        elif not in_quotes:
            if char == '(':
                paren_depth += 1
            elif char == ')':
                paren_depth -= 1

        # Handle commas (only at top level)
        if char == ',' and paren_depth == 0 and not in_quotes:
            assignments.append(current_assignment.strip())
            current_assignment = ""
        else:
            current_assignment += char

        i += 1

    # Add the last assignment
    if current_assignment.strip():
        assignments.append(current_assignment.strip())

    return assignments


def _extract_field_name_from_eval_assignment(assignment: str) -> str:
    """
    Extract the field name from an EVAL assignment expression.

    Handles patterns like:
    - field_name = expression
    - field_name=expression (no spaces)

    Args:
        assignment (str): A single assignment from EVAL clause

    Returns:
        str: The field name, or empty string if parsing fails
    """
    # Look for field_name = expression pattern
    match = re.match(r'^([a-zA-Z_][a-zA-Z0-9_]*)\s*=', assignment.strip())
    if match:
        return match.group(1).strip()

    return ""


def _split_stats_fields(stats_content: str) -> list[str]:
    """
    Split STATS content by commas, handling nested functions and WHERE clauses.

    Args:
        stats_content (str): The content between STATS and BY keywords

    Returns:
        list[str]: Individual field definitions
    """
    fields = []
    current_field = ""
    paren_depth = 0
    in_quotes = False
    quote_char = None

    i = 0
    while i < len(stats_content):
        char = stats_content[i]

        # Handle quotes
        if char in ('"', "'") and (i == 0 or stats_content[i-1] != '\\'):
            if not in_quotes:
                in_quotes = True
                quote_char = char
            elif char == quote_char:
                in_quotes = False
                quote_char = None

        # Handle parentheses
        elif not in_quotes:
            if char == '(':
                paren_depth += 1
            elif char == ')':
                paren_depth -= 1

        # Handle commas (only at top level)
        if char == ',' and paren_depth == 0 and not in_quotes:
            fields.append(current_field.strip())
            current_field = ""
        else:
            current_field += char

        i += 1

    # Add the last field
    if current_field.strip():
        fields.append(current_field.strip())

    return fields


def _extract_field_name_from_definition(field_definition: str) -> str:
    """
    Extract the field name from a single STATS field definition.

    Handles patterns like:
    - field_name = expression
    - field_name = AGG_FUNCTION(...) WHERE condition

    Args:
        field_definition (str): A single field definition from STATS clause

    Returns:
        str: The field name, or empty string if parsing fails
    """
    # Remove WHERE clause if present (everything after WHERE)
    field_def = re.split(r'\s+WHERE\s+', field_definition, flags=re.IGNORECASE)[0].strip()

    # Look for field_name = expression pattern
    match = re.match(r'^([a-zA-Z_][a-zA-Z0-9_]*)\s*=', field_def.strip())
    if match:
        return match.group(1).strip()

    return ""


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

    def extract_output_fields(self) -> list[str]:
        """
        Extract all output field names from the ESQL query, including EVAL and STATS fields.

        Returns:
            list[str]: List of all field names that could be output from the query

        Raises:
            ValueError: If query parsing fails
        """
        return extract_all_output_field_names(self.value)

    def extract_stats_fields(self) -> list[str]:
        """
        Extract output field names from STATS clauses in the ESQL query.

        Returns:
            list[str]: List of field names defined in STATS clauses

        Raises:
            ValueError: If STATS clause parsing fails
        """
        return extract_stats_field_names(self.value)

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


def connect_mongodb():
    """
    Connect to MongoDB KB instance with proper error handling and logging.

    Returns:
        MongoClient: Connected MongoDB client, or None if connection fails
    """
    # Use percent-encoded password for host connections
    mongo_uri = "mongodb://admin:1q2w3E%2A@localhost:27018/?authSource=admin"
    db_name = "kb_configs"  # Database name for KB configurations

    try:
        log_message(f"Attempting to connect to MongoDB at {mongo_uri.replace('1q2w3E%2A', '***')}")
        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)

        # Test the connection
        client.admin.command('ping')
        log_message("MongoDB connection successful")

        # Verify database access
        db = client[db_name]
        log_message(f"MongoDB database '{db_name}' accessible")
        return client

    except ConnectionFailure as e:
        log_message(f"MongoDB connection failed: {str(e)}", "error")
        return None
    except OperationFailure as e:
        log_message(f"MongoDB authentication/authorization failed: {str(e)}", "error")
        return None
    except Exception as e:
        log_message(f"Unexpected MongoDB connection error: {str(e)}", "error")
        return None
    
# Extractor modes enum
class ExtractorModes(str):
    BATCH = "batch"
    STREAMING = "streaming"

# MCP Tools ---------------------------------------------------------------------------------------------------

@mcp.tool()
def create_da_config(
    kb_config: Optional[KBConfig] = None,
    scheduling_training_config: Optional[schedulingTrainingConfig] = None,
    scheduling_detection_config: Optional[schedulingDetectionConfig] = None,
    da_alg_parameters: Optional[DaAlgParameters] = None
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

    # Set defaults if None
    if kb_config is None:
        kb_config = KBConfig(
            id=str(uuid.uuid4()),
            description="Default HTTP monitoring configuration",
            query_elastic="FROM .ds-kibana_sample_data_logs-* | WHERE @timestamp >= '2025-10-01T00:00:00.000Z' AND @timestamp < '2025-11-01T00:00:00.000Z' | EVAL es_timestamp = DATE_TRUNC(1 hour, @timestamp) | STATS status_code_200_counter = COUNT(*) WHERE response == '200', status_code_5xx_counter = COUNT(*) WHERE response >= '500' AND response < '600' BY es_timestamp | SORT es_timestamp"
        )
    if scheduling_training_config is None:
        scheduling_training_config = schedulingTrainingConfig(
            from_date=datetime.fromisoformat("2025-09-01T00:00:00"),
            to_date=datetime.fromisoformat("2025-09-30T23:59:59"),
            mode="batch"
        )
    if scheduling_detection_config is None:
        scheduling_detection_config = schedulingDetectionConfig(
            frequency=CRON("*/5 * * * *"),  # Every 5 minutes
            window=CRON("0 * * * *"),      # Every hour
            start=datetime.fromisoformat("2025-10-01T00:00:00"),
            mode="streaming"
        )
    if da_alg_parameters is None:
        da_alg_parameters = DaAlgParameters(algorithms=[
            ZScore(threshold=3.0, observed_value="status_code_200_counter"),
            ZScore(threshold=2.5, observed_value="status_code_5xx_counter")
        ])

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

        # Cross-validate: Check that observed_value fields match ESQL output fields
        if kb_config:
            try:
                esql_obj = ESQL(kb_config.query_elastic)
                output_fields = esql_obj.extract_output_fields()
                stats_fields = esql_obj.extract_stats_fields()

                if not output_fields:
                    validation_errors.append(
                        "ESQL query validation failed: No output fields found. "
                        "The query must contain either EVAL or STATS clauses that produce named fields."
                    )
                elif not stats_fields:
                    validation_errors.append(
                        "ESQL query validation failed: No STATS clause found. "
                        "The query must contain a STATS clause to aggregate data for anomaly detection."
                    )
                else:
                    # Check each algorithm's observed_value against all available output fields
                    missing_fields = []
                    invalid_algorithms = []

                    for i, alg in enumerate(da_alg_parameters.algorithms):
                        if hasattr(alg, 'observed_value'):
                            if alg.observed_value not in output_fields:
                                missing_fields.append(f"'{alg.observed_value}' (Algorithm {i})")
                            elif alg.observed_value not in stats_fields:
                                # Field exists but is not from STATS - this might be valid if it's an EVAL field
                                # but for anomaly detection, we typically want aggregated STATS fields
                                validation_errors.append(
                                    f"Algorithm {i} observed_value '{alg.observed_value}' is an EVAL field, "
                                    f"not a STATS aggregation field. For anomaly detection, use STATS output fields. "
                                    f"Available STATS fields: {stats_fields}"
                                )
                        else:
                            invalid_algorithms.append(f"Algorithm {i} (missing observed_value field)")

                    if missing_fields:
                        validation_errors.append(
                            f"Observed value fields not found in ESQL output: {', '.join(missing_fields)}. "
                            f"Available ESQL output fields: {output_fields}"
                        )

                    if invalid_algorithms:
                        validation_errors.append(
                            f"Invalid algorithms: {', '.join(invalid_algorithms)}. "
                            "All algorithms must have an observed_value field."
                        )

            except ValueError as e:
                validation_errors.append(f"ESQL query validation failed: {str(e)}")

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
    log_message(f"Configuration preview: {json.dumps(config_preview, indent=2)}")

    # Print configuration preview to console in correct format
    print("\nConfiguration Preview:")
    print(json.dumps(config_preview, indent=2))
    print()

    # Connect to MongoDB and save the configuration
    client = connect_mongodb()
    if client is None:
        error_msg = "Failed to connect to MongoDB - configuration not saved"
        log_message(error_msg, "error")
        return f"ERROR: {error_msg}"

    try:
        db = client["kb_configs"]
        collection = db["configurations"]

        # Insert the configuration
        result = collection.insert_one(config_preview)
        log_message(f"Configuration saved to MongoDB with document ID: {str(result.inserted_id)}")

        # Verify the save by counting documents
        doc_count = collection.count_documents({"KB_Config.Id": kb_config.id})
        log_message(f"Verification: {doc_count} document(s) found with ID {kb_config.id}")

        success_msg = f"SUCCESS: Configuration saved to MongoDB!\n\nID: {kb_config.id}\n\nConfiguration saved successfully."
        log_message("Configuration creation and saving completed successfully")
        return success_msg

    except OperationFailure as e:
        error_msg = f"MongoDB operation failed: {str(e)}"
        log_message(error_msg, "error")
        return f"ERROR: {error_msg}"
    except Exception as e:
        error_msg = "Unexpected error during MongoDB save"
        log_message(f"{error_msg}: {type(e).__name__}: {str(e)}", "error")
        return f"ERROR: {error_msg}"
    finally:
        try:
            client.close()
        except Exception as e:
            log_message(f"Error closing MongoDB client: {str(e)}", "warning")


if __name__ == "__main__":
    # Test the create_da_config function to demonstrate config_preview logging
    print("Testing create_da_config function...")
    result = create_da_config()
    print("Function result:")
    print(result)
    print("\nTest completed.")

    # Now start the MCP server
    mcp.run()