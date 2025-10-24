#!/usr/bin/env python3
import json
import uuid
import datetime
import logging
import re
import argparse
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

# Id GUID, Description, ChangeFlag, Scheduling, DA Alg Parameters
class KBConfig(BaseModel):
    id: str
    description: str
    changeFlag: int
    scheduling: dict
    daAlgParameters: dict

    def __init__(self, **data):
        super().__init__(**data)
        # Store original queries without validation during initialization
        # Validation will happen when tools are actually called
        log_message(f"KB config {self.id} initialized without SQL validation")

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
    # Future: Add other algorithm types here
    # THIS MEANS THIS CLASS WILL REMAIN AS IS UNTIL THE USER ASKS FOR MORE ALGORITHMS
    # THIS IS A CRITICAL COMMANDMENT

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
            # THIS MEANS THIS CLASS WILL REMAIN AS IS UNTIL THE USER ASKS FOR MORE ALGORITHMS
            # THIS IS A CRITICAL COMMANDMENT

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
    observed_value: str

    def to_dict(self):
        return {
            "observedValue": self.observed_value
        }
    
# Auxiliary classes --------------------------------------------------------------------------------------------

def extract_sql_output_fields(sql_query: str) -> list[str]:
    """
    Extract all output field names from SQL query.

    This function parses SQL queries to identify all field names that
    could be available as output from the SELECT clause.

    Args:
        sql_query (str): The complete SQL query string

    Returns:
        list[str]: List of all field names that could be output from the query

    Raises:
        ValueError: If query parsing fails due to malformed syntax

    Examples:
        >>> extract_sql_output_fields("SELECT field1, field2 FROM table WHERE condition")
        ['field1', 'field2']
    """
    import re

    # Find SELECT clause
    select_match = re.search(r'\bSELECT\s+(.+?)\s+FROM', sql_query, re.IGNORECASE | re.DOTALL)
    if not select_match:
        return []

    select_content = select_match.group(1).strip()

    # Split by commas, handling functions and aliases
    field_names = []
    fields = re.split(r',', select_content)
    for field in fields:
        field = field.strip()
        # Extract alias or field name
        alias_match = re.search(r'\s+AS\s+([a-zA-Z_][a-zA-Z0-9_]*)', field, re.IGNORECASE)
        if alias_match:
            field_names.append(alias_match.group(1))
        else:
            # Extract field name from expressions like COUNT(field) AS count
            name_match = re.search(r'([a-zA-Z_][a-zA-Z0-9_]*)\s*$', field)
            if name_match:
                field_names.append(name_match.group(1))

    return sorted(list(set(field_names)))


def extract_sql_select_fields(sql_query: str) -> list[str]:
    """
    Extract output field names from SQL SELECT clauses.

    This function parses SQL queries to identify field names defined in SELECT clauses,
    handling aggregations and aliases.

    Args:
        sql_query (str): The complete SQL query string

    Returns:
        list[str]: List of field names extracted from SELECT clauses

    Raises:
        ValueError: If SELECT clause parsing fails due to malformed syntax

    Examples:
        >>> extract_sql_select_fields("SELECT COUNT(*) as count, AVG(field) as avg_val FROM table")
        ['count', 'avg_val']
    """
    import re

    # Find SELECT clause
    select_match = re.search(r'\bSELECT\s+(.+?)\s+FROM', sql_query, re.IGNORECASE | re.DOTALL)
    if not select_match:
        return []

    select_content = select_match.group(1).strip()

    # Split by commas
    fields = re.split(r',', select_content)
    field_names = []
    for field in fields:
        field = field.strip()
        # Extract alias
        alias_match = re.search(r'\s+AS\s+([a-zA-Z_][a-zA-Z0-9_]*)', field, re.IGNORECASE)
        if alias_match:
            field_names.append(alias_match.group(1))
        else:
            # For simple fields or aggregations without alias
            name_match = re.search(r'([a-zA-Z_][a-zA-Z0-9_]*)\s*$', field)
            if name_match:
                field_names.append(name_match.group(1))

    return sorted(list(set(field_names)))


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


# SQL class for validating SQL queries
class SQL:
    def __init__(self, value: str):
        if not self._is_valid_sql(value):
            log_message(f"SQL validation failed: Invalid SQL format: {value}", "error")
            raise ValueError(f"Invalid SQL format: {value}")
        self.value = value
        log_message(f"SQL validated successfully: {value[:50]}...", "info")

    @staticmethod
    def _is_valid_sql(query: str) -> bool:
        # Basic SQL syntax validation without using MCP tools during startup
        try:
            # Basic regex validation for SQL structure
            if not re.search(r'\bSELECT\b', query, re.IGNORECASE):
                return False

            # Check for basic SQL structure
            if not re.search(r'\bFROM\b', query, re.IGNORECASE):
                return False

            # Check for balanced quotes
            single_quotes = query.count("'") - query.count("\\'")
            double_quotes = query.count('"') - query.count('\\"')
            if single_quotes % 2 != 0 or double_quotes % 2 != 0:
                return False

            log_message("SQL basic validation successful")
            return True
        except Exception as e:
            log_message(f"SQL validation failed: {str(e)}", "warning")
            return False

    def extract_output_fields(self) -> list[str]:
        """
        Extract all output field names from the SQL query.

        Returns:
            list[str]: List of all field names that could be output from the query

        Raises:
            ValueError: If query parsing fails
        """
        return extract_sql_output_fields(self.value)

    def extract_stats_fields(self) -> list[str]:
        """
        Extract output field names from SQL SELECT clauses.

        Returns:
            list[str]: List of field names defined in SELECT clauses

        Raises:
            ValueError: If SELECT clause parsing fails
        """
        return extract_sql_select_fields(self.value)

    def __str__(self):
        return self.value

    def __repr__(self):
        return f"SQL('{self.value}')"


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
    da_alg_parameters: Optional[DaAlgParameters] = None
) -> str:
    """
    Create a Data Analytics (DA) algorithm configuration for the Knowledge Base system.

    This function validates all input parameters and provides detailed error messages
    to help ensure correct configuration creation.

    Args:
        kb_config (KBConfig): Configuration containing ID, description, changeFlag, scheduling, and daAlgParameters
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
            changeFlag=0,
            scheduling={
                "trainingConfig": {
                    "trainingQuery": "SELECT DATE_TRUNC('hour', \"@timestamp\") AS es_timestamp, COUNT(CASE WHEN response = '200' THEN 1 END) AS status_code_200_counter, COUNT(CASE WHEN response >= '500' AND response < '600' THEN 1 END) AS status_code_5xx_counter FROM \".ds-kibana_sample_data_logs-*\" WHERE \"@timestamp\" >= '2025-10-01T00:00:00.000Z' AND \"@timestamp\" < '2025-11-01T00:00:00.000Z' GROUP BY DATE_TRUNC('hour', \"@timestamp\") ORDER BY es_timestamp",
                    "from": "2025-09-01T00:00:00Z",
                    "to": "2025-09-30T23:59:59Z",
                    "mode": "training",
                    "trainingWindow": 60,
                    "isActive": True
                },
                "detectionConfig": {
                    "detectionQuery": "SELECT DATE_TRUNC('hour', \"@timestamp\") AS es_timestamp, COUNT(CASE WHEN response = '200' THEN 1 END) AS status_code_200_counter, COUNT(CASE WHEN response >= '500' AND response < '600' THEN 1 END) AS status_code_5xx_counter FROM \".ds-kibana_sample_data_logs-*\" WHERE \"@timestamp\" >= '2025-10-10T00:00:00.000Z' AND \"@timestamp\" < '2025-10-11T00:00:00.000Z' GROUP BY DATE_TRUNC('hour', \"@timestamp\") ORDER BY es_timestamp",
                    "from": "2025-10-10T00:00:00Z",
                    "frequency": "*/15 * * * *",
                    "detectionWindow": 60,
                    "mode": "detection",
                    "isActive": False
                }
            },
            daAlgParameters={
                "zscore": [
                    {"observedValue": "status_code_200_counter"},
                    {"observedValue": "status_code_5xx_counter"}
                ]
            }
        )
    if da_alg_parameters is None:
        # Try to extract custom algorithms from KB config first
        # Handle both KBConfig objects and dict inputs from MCP
        da_alg_params = None
        if isinstance(kb_config, dict) and 'daAlgParameters' in kb_config:
            da_alg_params = kb_config['daAlgParameters']
        elif hasattr(kb_config, 'daAlgParameters'):
            da_alg_params = kb_config.daAlgParameters

        if da_alg_params:
            custom_algs = []
            # Extract zscore algorithms from KB config
            zscore_configs = da_alg_params.get("zscore", [])
            for alg_dict in zscore_configs:
                if isinstance(alg_dict, dict) and "observedValue" in alg_dict:
                    custom_algs.append(ZScore(observed_value=alg_dict["observedValue"]))

            if custom_algs:
                da_alg_parameters = DaAlgParameters(algorithms=custom_algs)
                log_message(f"Using {len(custom_algs)} custom algorithms from KB config")
            else:
                # Fall back to defaults if no valid custom algorithms found
                da_alg_parameters = DaAlgParameters(algorithms=[
                    ZScore(observed_value="status_code_200_counter"),
                    ZScore(observed_value="status_code_5xx_counter")
                ])
                log_message("No valid custom algorithms found, using defaults")
        else:
            # Use defaults when no KB config or daAlgParameters provided
            da_alg_parameters = DaAlgParameters(algorithms=[
                ZScore(observed_value="status_code_200_counter"),
                ZScore(observed_value="status_code_5xx_counter")
            ])
            log_message("Using default algorithms")

    validation_errors = []
    
    # Validate KB Config
    try:
        if not kb_config.id or not isinstance(kb_config.id, str):
            validation_errors.append("KB Config ID must be a non-empty string")
        if not kb_config.description or not isinstance(kb_config.description, str):
            validation_errors.append("KB Config description must be a non-empty string")
        # SQL validation will happen in the tool functions
    except ValueError as e:
        validation_errors.append(f"KB Config validation failed: {str(e)}")
    
    # Validate Training Config
    try:
        training_config = kb_config.scheduling.get('trainingConfig', {})
        if training_config.get('from') >= training_config.get('to'):
            validation_errors.append("Training 'from' must be before 'to'")
        if training_config.get('mode') not in ["training", "batch", "streaming"]:
            validation_errors.append("Training mode must be 'training', 'batch', or 'streaming'")
        if not isinstance(training_config.get('trainingWindow'), int) or training_config.get('trainingWindow') <= 0:
            validation_errors.append("Training window must be a positive integer")
    except (AttributeError, TypeError):
        validation_errors.append("Invalid training config in scheduling")

    # Validate Detection Config
    try:
        detection_config = kb_config.scheduling.get('detectionConfig', {})
        if detection_config.get('mode') not in ["detection", "batch", "streaming"]:
            validation_errors.append("Detection mode must be 'detection', 'batch', or 'streaming'")
        if not isinstance(detection_config.get('detectionWindow'), int) or detection_config.get('detectionWindow') <= 0:
            validation_errors.append("Detection window must be a positive integer")
        # CRON validation for frequency
        if 'frequency' in detection_config:
            try:
                CRON(detection_config['frequency'])
            except ValueError as e:
                validation_errors.append(f"Invalid detection frequency CRON: {str(e)}")
    except (AttributeError, TypeError):
        validation_errors.append("Invalid detection config in scheduling")
    
    # Validate DA Algorithm Parameters
    try:
        if not da_alg_parameters.algorithms or len(da_alg_parameters.algorithms) == 0:
            validation_errors.append("At least one algorithm must be specified")
        for i, alg in enumerate(da_alg_parameters.algorithms):
            if not hasattr(alg, 'to_dict'):
                validation_errors.append(f"Algorithm {i} must have a to_dict() method")

        # Cross-validate: Check that observed_value fields match SQL output fields
        if kb_config:
            try:
                # Validate training query using elasticsearch_sql tool
                training_query = kb_config.scheduling.get('trainingConfig', {}).get('trainingQuery')
                if training_query:
                    # Use elasticsearch_sql tool to validate and get output fields
                    validation_result = elasticsearch_sql(training_query + " LIMIT 0")
                    if "ERROR" in validation_result:
                        validation_errors.append(f"Training SQL query validation failed: {validation_result}")
                    else:
                        # Parse the result to get output fields
                        try:
                            result_data = json.loads(validation_result)
                            output_fields = [col['name'] for col in result_data.get('columns', [])]

                            if not output_fields:
                                validation_errors.append(
                                    "Training SQL query validation failed: No output fields found. "
                                    "The query must contain a SELECT clause that produces named fields."
                                )
                            else:
                                # Check each algorithm's observed_value against available output fields
                                missing_fields = []
                                for i, alg in enumerate(da_alg_parameters.algorithms):
                                    if hasattr(alg, 'observed_value'):
                                        if alg.observed_value not in output_fields:
                                            missing_fields.append(f"'{alg.observed_value}' (Algorithm {i})")
                                    else:
                                        validation_errors.append(f"Algorithm {i} missing observed_value field")

                                if missing_fields:
                                    validation_errors.append(
                                        f"Observed value fields not found in training SQL output: {', '.join(missing_fields)}. "
                                        f"Available SQL output fields: {output_fields}"
                                    )
                        except json.JSONDecodeError:
                            validation_errors.append("Training SQL query validation failed: Could not parse Elasticsearch response")

                # Validate detection query using elasticsearch_sql tool
                detection_query = kb_config.scheduling.get('detectionConfig', {}).get('detectionQuery')
                if detection_query:
                    # Use elasticsearch_sql tool to validate and get output fields
                    validation_result = elasticsearch_sql(detection_query + " LIMIT 0")
                    if "ERROR" in validation_result:
                        validation_errors.append(f"Detection SQL query validation failed: {validation_result}")
                    else:
                        # Parse the result to get output fields
                        try:
                            result_data = json.loads(validation_result)
                            output_fields = [col['name'] for col in result_data.get('columns', [])]

                            if not output_fields:
                                validation_errors.append(
                                    "Detection SQL query validation failed: No output fields found. "
                                    "The query must contain a SELECT clause that produces named fields."
                                )
                            else:
                                # Check each algorithm's observed_value against available output fields
                                missing_fields = []
                                for i, alg in enumerate(da_alg_parameters.algorithms):
                                    if hasattr(alg, 'observed_value'):
                                        if alg.observed_value not in output_fields:
                                            missing_fields.append(f"'{alg.observed_value}' (Algorithm {i})")
                                    else:
                                        validation_errors.append(f"Algorithm {i} missing observed_value field")

                                if missing_fields:
                                    validation_errors.append(
                                        f"Observed value fields not found in detection SQL output: {', '.join(missing_fields)}. "
                                        f"Available SQL output fields: {output_fields}"
                                    )
                        except json.JSONDecodeError:
                            validation_errors.append("Detection SQL query validation failed: Could not parse Elasticsearch response")

            except Exception as e:
                validation_errors.append(f"SQL query validation failed: {str(e)}")

    except AttributeError:
        validation_errors.append("Invalid da_alg_parameters object")
    
    # If validation failed, return detailed errors
    if validation_errors:
        error_msg = "Configuration validation failed:\n" + "\n".join(f"- {err}" for err in validation_errors)
        log_message(f"Configuration validation failed: {len(validation_errors)} errors")
        return error_msg
    
    # Build preview of configuration
    config_preview = {
        "kbConfig": {
            "id": kb_config.id,
            "description": kb_config.description,
            "changeFlag": kb_config.changeFlag,
            "scheduling": kb_config.scheduling,
            "daAlgParameters": da_alg_parameters.to_dict() if da_alg_parameters else kb_config.daAlgParameters
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


@mcp.tool()
def elasticsearch_sql(query: str) -> str:
    """
    Execute a SQL query against Elasticsearch.

    This tool allows running SQL queries on Elasticsearch indices, providing a SQL interface
    to the data stored in Elasticsearch.

    Args:
        query (str): The SQL query to execute (e.g., "SELECT * FROM index_name WHERE field = 'value' LIMIT 10")

    Returns:
        str: The results of the query in JSON format, including columns, rows, and cursor information.
             Returns an error message if the query fails on all available Elasticsearch hosts.

    Raises:
        No exceptions raised - errors are handled internally and returned as strings
    """
    # Try multiple Elasticsearch hosts for reliability
    es_hosts = ["http://localhost:9200", "http://elasticsearch-dataset:9200"]

    for host in es_hosts:
        try:
            log_message(f"Attempting SQL query execution with Elasticsearch at {host}")
            es = Elasticsearch(host)

            # Execute the SQL query using Elasticsearch's SQL API
            response = es.sql.query(query=query)

            # Format the results for easy consumption
            results = {
                "columns": response.get("columns", []),
                "rows": response.get("rows", []),
                "cursor": response.get("cursor"),
                "total_rows": len(response.get("rows", []))
            }

            log_message(f"SQL query executed successfully with {host}, returned {results['total_rows']} rows")
            return json.dumps(results, indent=2)

        except Exception as e:
            log_message(f"SQL query failed with {host}: {str(e)}", "warning")
            continue

    # If all hosts failed
    error_msg = "ERROR: Failed to execute SQL query on all Elasticsearch hosts"
    log_message(error_msg, "error")
    return error_msg


if __name__ == "__main__":
    # Check if this is being run as an MCP server (no arguments or --server flag)
    import sys
    if len(sys.argv) == 1 or (len(sys.argv) == 2 and sys.argv[1] == "--server"):
        # Start MCP server - NO stdout output allowed for stdio transport
        mcp.run()
    else:
        # Run test with command line arguments
        parser = argparse.ArgumentParser(description="KB-MCP Configuration Tool")
        parser.add_argument("--kb-config", type=str, help="JSON string for KB configuration")
        parser.add_argument("--da-alg", type=str, help="JSON string for DA algorithm parameters")
        parser.add_argument("--id", type=str, help="KB configuration ID")
        parser.add_argument("--description", type=str, help="KB configuration description")
        parser.add_argument("--change-flag", type=int, default=0, help="Change flag for KB config")
        parser.add_argument("--training-query", type=str, help="SQL query for training")
        parser.add_argument("--detection-query", type=str, help="SQL query for detection")
        parser.add_argument("--training-from", type=str, help="Training from date (ISO format)")
        parser.add_argument("--training-to", type=str, help="Training to date (ISO format)")
        parser.add_argument("--training-mode", type=str, default="training", help="Training mode")
        parser.add_argument("--training-window", type=int, default=60, help="Training window")
        parser.add_argument("--training-active", action="store_true", help="Training is active")
        parser.add_argument("--detection-from", type=str, help="Detection from date (ISO format)")
        parser.add_argument("--detection-frequency", type=str, help="Detection frequency (CRON)")
        parser.add_argument("--detection-mode", type=str, default="detection", help="Detection mode")
        parser.add_argument("--detection-window", type=int, default=60, help="Detection window")
        parser.add_argument("--detection-active", action="store_true", help="Detection is active")

        args = parser.parse_args()

        # Run test with parameters
        print("Testing create_da_config function...")

        # Build KB config from arguments
        if args.kb_config:
            try:
                kb_data = json.loads(args.kb_config)
                kb_config = KBConfig(**kb_data)
            except json.JSONDecodeError as e:
                print(f"Error parsing kb-config JSON: {e}")
                exit(1)
        else:
            # Build from individual arguments with defaults
            scheduling = {}

            # Default training config
            training_config = {
                "trainingQuery": args.training_query or "SELECT DATE_TRUNC('hour', \"@timestamp\") AS es_timestamp, COUNT(CASE WHEN response = '200' THEN 1 END) AS status_code_200_counter, COUNT(CASE WHEN response >= '500' AND response < '600' THEN 1 END) AS status_code_5xx_counter FROM \".ds-kibana_sample_data_logs-*\" WHERE \"@timestamp\" >= '2025-10-01T00:00:00.000Z' AND \"@timestamp\" < '2025-11-01T00:00:00.000Z' GROUP BY DATE_TRUNC('hour', \"@timestamp\") ORDER BY es_timestamp",
                "from": args.training_from or "2025-09-01T00:00:00Z",
                "to": args.training_to or "2025-09-30T23:59:59Z",
                "mode": args.training_mode,
                "trainingWindow": args.training_window,
                "isActive": args.training_active
            }
            scheduling["trainingConfig"] = training_config

            # Default detection config
            detection_config = {
                "detectionQuery": args.detection_query or "SELECT DATE_TRUNC('hour', \"@timestamp\") AS es_timestamp, COUNT(CASE WHEN response = '200' THEN 1 END) AS status_code_200_counter, COUNT(CASE WHEN response >= '500' AND response < '600' THEN 1 END) AS status_code_5xx_counter FROM \".ds-kibana_sample_data_logs-*\" WHERE \"@timestamp\" >= '2025-10-10T00:00:00.000Z' AND \"@timestamp\" < '2025-10-11T00:00:00.000Z' GROUP BY DATE_TRUNC('hour', \"@timestamp\") ORDER BY es_timestamp",
                "from": args.detection_from or "2025-10-10T00:00:00Z",
                "frequency": args.detection_frequency or "*/15 * * * *",
                "mode": args.detection_mode,
                "detectionWindow": args.detection_window,
                "isActive": args.detection_active
            }
            scheduling["detectionConfig"] = detection_config

            kb_config = KBConfig(
                id=args.id or str(uuid.uuid4()),
                description=args.description or "Test configuration",
                changeFlag=args.change_flag,
                scheduling=scheduling,
                daAlgParameters={
                    "zscore": [
                        {"observedValue": "status_code_200_counter"},
                        {"observedValue": "status_code_5xx_counter"}
                    ]
                }
            )

        # Build DA alg parameters
        da_alg_parameters = None
        if args.da_alg:
            try:
                alg_data = json.loads(args.da_alg)
                # Map observedValue to observed_value for ZScore
                zscore_algs = []
                for alg in alg_data.get("zscore", []):
                    if "observedValue" in alg:
                        alg["observed_value"] = alg.pop("observedValue")
                    zscore_algs.append(ZScore(**alg))
                da_alg_parameters = DaAlgParameters(algorithms=zscore_algs)
            except json.JSONDecodeError as e:
                print(f"Error parsing da-alg JSON: {e}")
                exit(1)

        # Call the function
        result = create_da_config(kb_config=kb_config, da_alg_parameters=da_alg_parameters)
        print("Function result:")
        print(result)
        print("\nTest completed.")