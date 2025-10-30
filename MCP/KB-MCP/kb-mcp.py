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
from bson import ObjectId
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

# Knowledge Base Configuration
class KBConfig(BaseModel):
    # No id field - MongoDB will auto-generate _id
    name: str
    description: str
    change_flag: int  # snake_case
    scheduling: dict
    da_alg_parameters: dict  # snake_case

    def __init__(self, **data):
        super().__init__(**data)
        # Basic validation - detailed validation happens in tools
        if not self.name or not isinstance(self.name, str):
            raise ValueError("Name must be a non-empty string")
        if not self.description or not isinstance(self.description, str):
            raise ValueError("Description must be a non-empty string")
        log_message(f"KB config structure validated for: {self.name}")

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
            "dimension": self.observed_value  # Map to dimension for template compatibility
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
    mongo_uri = "mongodb://admin:1q2w3E%2A@localhost:27017/?authSource=admin"
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
    kb_config: dict,
    da_alg_parameters: dict
) -> str:
    """
    Create a Data Analytics (DA) algorithm configuration for the Knowledge Base system.

    This function validates all input parameters and provides detailed error messages
    to help ensure correct configuration creation.

    Args:
        kb_config (dict): Configuration containing name, description, changeFlag, scheduling, and daAlgParameters
        da_alg_parameters (dict): Data analytics algorithm parameters

    Returns:
        str: Validation success message with configuration preview, or detailed error message

    Raises:
        ValueError: If any validation fails with specific error details
    """

    # Debug logging to understand what MCP is passing
    log_message(f"DEBUG: kb_config type: {type(kb_config)}")
    log_message(f"DEBUG: kb_config value: {kb_config}")
    log_message(f"DEBUG: da_alg_parameters type: {type(da_alg_parameters)}")
    log_message(f"DEBUG: da_alg_parameters value: {da_alg_parameters}")

    # Convert dictionaries to proper objects
    try:
        # Convert kb_config dict to KBConfig object
        kb_config_obj = KBConfig(**kb_config)
        log_message(f"DEBUG: Successfully converted kb_config to KBConfig object")

        # Convert da_alg_parameters dict to DaAlgParameters object
        # Handle the algorithms list conversion
        algorithms_list = []
        if 'algorithms' in da_alg_parameters:
            for alg_dict in da_alg_parameters['algorithms']:
                if isinstance(alg_dict, dict) and 'observed_value' in alg_dict:
                    algorithms_list.append(ZScore(**alg_dict))
                else:
                    # Try to convert observedValue to observed_value if needed
                    alg_copy = alg_dict.copy()
                    if 'observedValue' in alg_copy and 'observed_value' not in alg_copy:
                        alg_copy['observed_value'] = alg_copy.pop('observedValue')
                    algorithms_list.append(ZScore(**alg_copy))

        da_params_obj = DaAlgParameters(algorithms=algorithms_list)
        log_message(f"DEBUG: Successfully converted da_alg_parameters to DaAlgParameters object")

    except Exception as e:
        log_message(f"ERROR: Failed to convert input objects: {str(e)}", "error")
        return f"ERROR: Failed to convert input objects: {str(e)}"

    # REMOVED: Default configuration generation - function now requires explicit parameters

    validation_errors = []
    
    # Validate KB Config
    try:
        if not kb_config_obj.name or not isinstance(kb_config_obj.name, str):
            validation_errors.append("KB Config name must be a non-empty string")
        if not kb_config_obj.description or not isinstance(kb_config_obj.description, str):
            validation_errors.append("KB Config description must be a non-empty string")
        # SQL validation will happen in the tool functions
    except (ValueError, AttributeError) as e:
        validation_errors.append(f"KB Config validation failed: {str(e)}")

    # Validate Training Config
    try:
        training_config = kb_config_obj.scheduling.get('training_config', {})  # snake_case
        if training_config.get('from') >= training_config.get('to'):
            validation_errors.append("Training 'from' must be before 'to'")
        # Mode validation removed - not implementing at this time
        if not isinstance(training_config.get('training_window'), int) or training_config.get('training_window') <= 0:  # snake_case
            validation_errors.append("Training window must be a positive integer")
    except (AttributeError, TypeError):
        validation_errors.append("Invalid training config in scheduling")

    # Validate Detection Config
    try:
        detection_config = kb_config_obj.scheduling.get('detection_config', {})  # snake_case
        # Mode validation removed - not implementing at this time
        if not isinstance(detection_config.get('detection_window'), int) or detection_config.get('detection_window') <= 0:  # snake_case
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
        if not da_params_obj.algorithms or len(da_params_obj.algorithms) == 0:
            validation_errors.append("At least one algorithm must be specified")
        for i, alg in enumerate(da_params_obj.algorithms):
            if not hasattr(alg, 'to_dict'):
                validation_errors.append(f"Algorithm {i} must have a to_dict() method")

        # Cross-validate: Check that observed_value fields match SQL output fields
        if kb_config_obj:
            try:
                # Validate training query using elasticsearch_sql tool
                training_query = kb_config_obj.scheduling.get('training_config', {}).get('training_query')  # snake_case
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
                                for i, alg in enumerate(da_params_obj.algorithms):
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
                detection_query = kb_config_obj.scheduling.get('detection_config', {}).get('detection_query')  # snake_case
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
                                for i, alg in enumerate(da_params_obj.algorithms):
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
    
    # Build configuration in template format (snake_case, no wrapper, NO id field)
    config_to_store = {
        "name": kb_config_obj.name,
        "description": kb_config_obj.description,
        "change_flag": kb_config_obj.change_flag,  # snake_case
        "scheduling": kb_config_obj.scheduling,  # Use scheduling directly as it should already be in snake_case format
        "da_alg_parameters": kb_config_obj.da_alg_parameters  # Use da_alg_parameters directly
    }

    log_message(f"Configuration validation successful for: {kb_config_obj.name}")
    log_message(f"Configuration to store: {json.dumps(config_to_store, indent=2)}")

    # Print configuration preview to console in correct format
    print("\nConfiguration Preview:")
    print(json.dumps(config_to_store, indent=2))
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

        # Insert the configuration directly (no kbConfig wrapper)
        result = collection.insert_one(config_to_store)
        log_message(f"Configuration saved to MongoDB with document ID: {str(result.inserted_id)}")

        # Verify the save by counting documents with this name
        doc_count = collection.count_documents({"name": kb_config_obj.name})
        log_message(f"Verification: {doc_count} document(s) found with name {kb_config_obj.name}")

        success_msg = f"SUCCESS: Configuration saved to MongoDB!\n\nDocument ID: {str(result.inserted_id)}\n\nConfiguration saved successfully."
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
def modify_kb_config(
    config_id: str,
    description: str = None,
    training_query: str = None,
    detection_query: str = None,
    training_from: str = None,
    training_to: str = None,
    detection_frequency: str = None,
    detection_start: str = None,
    da_alg_parameters: dict = None
) -> str:
    """
    Modify an existing KB configuration by ID.

    This tool allows updating specific fields of an existing KB configuration stored in MongoDB.
    Only the provided parameters will be updated; others remain unchanged.

    Args:
        config_id (str): UUID of the configuration to modify (required)
        description (str): New description (optional)
        training_query (str): New SQL training query (optional)
        detection_query (str): New SQL detection query (optional)
        training_from (str): New training start date (ISO format, optional)
        training_to (str): New training end date (ISO format, optional)
        detection_frequency (str): New detection frequency (CRON format, optional)
        detection_start (str): New detection start date (ISO format, optional)
        da_alg_parameters (dict): New algorithm parameters (optional)

    Returns:
        Success message with updated configuration details, or error message
    """
    client = connect_mongodb()
    if client is None:
        return "ERROR: Failed to connect to MongoDB"

    try:
        db = client["kb_configs"]
        collection = db["configurations"]

        # Find the configuration - use MongoDB _id directly
        try:
            config_doc = collection.find_one({"_id": ObjectId(config_id)})
        except Exception as e:
            return f"ERROR: Invalid configuration ID format: '{config_id}' - {str(e)}"

        if not config_doc:
            return f"ERROR: Configuration with ID '{config_id}' not found"

        # Prepare updates - direct field access, no kbConfig wrapper
        updates = {}

        if description is not None:
            updates["description"] = description  # Direct field access

        if training_query is not None:
            # Validate SQL query
            try:
                sql_obj = SQL(training_query)
                updates["scheduling.training_config.training_query"] = training_query  # snake_case
            except ValueError as e:
                return f"ERROR: Invalid training query: {str(e)}"

        if detection_query is not None:
            # Validate SQL query
            try:
                sql_obj = SQL(detection_query)
                updates["scheduling.detection_config.detection_query"] = detection_query  # snake_case
            except ValueError as e:
                return f"ERROR: Invalid detection query: {str(e)}"

        if training_from is not None:
            updates["scheduling.training_config.from"] = training_from  # snake_case

        if training_to is not None:
            updates["scheduling.training_config.to"] = training_to  # snake_case

        if detection_frequency is not None:
            # Validate CRON
            try:
                CRON(detection_frequency)
                updates["scheduling.detection_config.frequency"] = detection_frequency  # snake_case
            except ValueError as e:
                return f"ERROR: Invalid detection frequency: {str(e)}"

        if detection_start is not None:
            updates["scheduling.detection_config.from"] = detection_start  # snake_case

        if da_alg_parameters is not None:
            # Validate algorithm parameters
            try:
                # Extract zscore algorithms - handle dimension instead of observedValue
                zscore_algs = []
                if "zscore" in da_alg_parameters:
                    for alg_dict in da_alg_parameters["zscore"]:
                        if isinstance(alg_dict, dict) and "dimension" in alg_dict:  # NEW: dimension
                            zscore_algs.append(ZScore(observed_value=alg_dict["dimension"]))  # Map dimension to observed_value

                if zscore_algs:
                    da_params = DaAlgParameters(algorithms=zscore_algs)
                    updates["da_alg_parameters"] = da_alg_parameters  # snake_case
                else:
                    return "ERROR: No valid ZScore algorithms found in da_alg_parameters"
            except Exception as e:
                return f"ERROR: Invalid algorithm parameters: {str(e)}"

        if not updates:
            return "WARNING: No valid updates provided"

        # Apply updates - increment change_flag directly
        updates["change_flag"] = config_doc.get("change_flag", 0) + 1  # Direct field access, snake_case

        # Apply updates
        result = collection.update_one(
            {"_id": ObjectId(config_id)},
            {"$set": updates}
        )

        if result.modified_count == 0:
            return "WARNING: No changes were made to the configuration"

        # Retrieve and return updated configuration (exclude MongoDB ObjectId)
        updated_doc = collection.find_one({"_id": ObjectId(config_id)}, {"_id": 0})
        if updated_doc:
            return f"SUCCESS: Configuration '{config_id}' updated successfully."
        else:
            return f"SUCCESS: Configuration '{config_id}' updated successfully, but could not retrieve updated document."

    except Exception as e:
        log_message(f"Error modifying configuration {config_id}: {str(e)}", "error")
        return f"ERROR: Failed to modify configuration: {str(e)}"
    finally:
        try:
            client.close()
        except:
            pass


@mcp.tool()
def list_kb_configurations() -> str:
    """
    List all KB configurations stored in MongoDB.

    This tool retrieves all KB configurations from the database and returns
    a formatted summary including IDs, descriptions, algorithms, and scheduling.

    Returns:
        Formatted string listing all KB configurations with their details
    """
    client = connect_mongodb()
    if client is None:
        return "ERROR: Failed to connect to MongoDB"

    try:
        db = client["kb_configs"]
        collection = db["configurations"]

        # Retrieve all configurations - include all fields including _id
        configs = list(collection.find({}, {}))

        if not configs:
            return "No KB configurations found in the database."

        # Format output
        output = "# KB Configurations Summary\n\n"
        output += f"Found {len(configs)} configuration(s):\n\n"

        for config_doc in configs:
            # Direct access, no kbConfig wrapper
            kb_config = config_doc

            config_id = str(kb_config.get("_id", "Unknown"))  # Use MongoDB _id
            name = kb_config.get("name", "Unknown")
            description = kb_config.get("description", "No description")

            # Extract algorithm info - handle dimension instead of observedValue
            da_params = kb_config.get("da_alg_parameters", {})  # snake_case
            algorithms = []
            if "zscore" in da_params:
                algorithms.extend([f"ZScore({alg.get('dimension', 'unknown')})" for alg in da_params["zscore"]])  # NEW: dimension

            # Extract scheduling info - snake_case
            scheduling = kb_config.get("scheduling", {})
            training_config = scheduling.get("training_config", {})  # snake_case
            detection_config = scheduling.get("detection_config", {})  # snake_case

            training_from = training_config.get("from", "Unknown")
            training_to = training_config.get("to", "Unknown")
            detection_freq = detection_config.get("frequency", "Unknown")
            detection_from = detection_config.get("from", "Unknown")

            output += f"## Configuration: {name}\n"
            output += f"- **ID**: {config_id}\n"
            output += f"- **Description**: {description}\n"
            output += f"- **Algorithms**: {', '.join(algorithms) if algorithms else 'None'}\n"
            output += f"- **Training Period**: {training_from} to {training_to}\n"
            output += f"- **Detection**: Every {detection_freq} starting {detection_from}\n\n"

        return output

    except Exception as e:
        log_message(f"Error listing configurations: {str(e)}", "error")
        return f"ERROR: Failed to list configurations: {str(e)}"
    finally:
        try:
            client.close()
        except:
            pass


@mcp.tool()
def describe_mcp_server() -> str:
    """
    Get a comprehensive description of the KB-MCP server and how to use it.

    This tool provides an overview of the MCP server's purpose, available tools,
    and usage guidelines for the SQL-based Knowledge Base configuration system.
    """
    description = """
# KB-MCP Server Overview

**IMPORTANT UPDATE (October 2025)**: The KB-MCP server has been migrated from ES|QL to SQL queries to overcome ES|QL's 10,000 entry limitation. All configurations now use Elasticsearch SQL syntax with full pagination support.

## Purpose
The KB-MCP (Knowledge Base Model Context Protocol) server provides tools for creating, managing, and querying Data Analytics (DA) algorithm configurations for the Knowledge Base system.

## Key Features
- **SQL Query Support**: Uses Elasticsearch SQL instead of ES|QL for unlimited result sets
- **MongoDB Storage**: Configurations stored in MongoDB for reliability and scalability
- **Algorithm Validation**: Ensures algorithm parameters match SQL query outputs
- **Comprehensive Management**: Create, modify, list, and query configurations

## Available Tools

### 1. create_da_config
Creates and validates new anomaly detection configurations.
- **Input**: Complete KB configuration object with SQL queries and algorithm parameters
- **Output**: Validation results and MongoDB storage confirmation
- **Use Case**: Setting up new monitoring configurations

### 2. modify_kb_config
Updates existing KB configurations in MongoDB.
- **Input**: Configuration ID and fields to update
- **Output**: Update confirmation with modified configuration
- **Use Case**: Adjusting existing monitoring parameters

### 3. list_kb_configurations
Lists all KB configurations stored in MongoDB.
- **Input**: None
- **Output**: Formatted summary of all configurations
- **Use Case**: Administrative overview of deployed configurations

### 4. elasticsearch_sql
Executes SQL queries directly against Elasticsearch.
- **Input**: SQL query string
- **Output**: Query results with columns, rows, and metadata
- **Use Case**: Testing queries and data exploration

### 5. list_available_algorithms
Shows all supported anomaly detection algorithms.
- **Input**: None
- **Output**: Algorithm specifications and status
- **Use Case**: Understanding available detection methods

### 6. describe_mcp_server (this tool)
Provides server overview and usage guidance.
- **Input**: None
- **Output**: Comprehensive documentation
- **Use Case**: Learning about the system capabilities

## How to Use

### 1. Data Exploration First
Before creating configurations, use the `elasticsearch_sql` tool to explore your data and craft appropriate SQL queries.

### 2. Configuration Creation
Use `create_da_config` with a complete configuration object containing:
- Unique ID (auto-generated if not provided)
- Descriptive name
- SQL queries for training and detection
- Scheduling parameters
- Algorithm specifications

### 3. Configuration Management
- Use `list_kb_configurations` to see all deployed configs
- Use `modify_kb_config` to update existing configurations
- Use `elasticsearch_sql` to test and validate queries

## Configuration Structure

```json
{
  "name": "Configuration Name",
  "description": "Human-readable description",
  "change_flag": 0,
  "scheduling": {
    "training_config": {
      "training_query": "SELECT ... FROM ... WHERE ... GROUP BY ...",
      "from": "2025-09-01T00:00:00Z",
      "to": "2025-09-30T23:59:59Z",
      "training_window": 3600,
      "is_active": true
    },
    "detection_config": {
      "detection_query": "SELECT ... FROM ... WHERE ... GROUP BY ...",
      "from": "2025-10-10T00:00:00Z",
      "frequency": "*/15 * * * *",
      "detection_window": 3600,
      "is_active": false
    }
  },
  "da_alg_parameters": {
    "zscore": [
      {"dimension": "field_name"}
    ],
    "arma": [
      {
        "dimension": "field_name",
        "algorithm_metadata": [
          {"key": "p", "value": 2},
          {"key": "d", "value": 1},
          {"key": "q", "value": 2}
        ]
      }
    ]
  }
}
```

## SQL Query Guidelines

### Supported Syntax
- Standard SQL SELECT statements
- Aggregation functions (COUNT, SUM, AVG, etc.)
- Date/time functions (DATE_TRUNC, etc.)
- Conditional expressions (CASE WHEN)
- GROUP BY and ORDER BY clauses

### Field Naming
- Use descriptive aliases for aggregated fields
- Ensure `observedValue` fields in algorithms match SQL output column names
- Example: `COUNT(*) AS request_count` → `observedValue: "request_count"`

### Best Practices
1. Test queries with `elasticsearch_sql` before configuration
2. Use appropriate date ranges for training data
3. Ensure aggregation fields align with anomaly detection needs
4. Validate CRON expressions for scheduling

## Algorithm Support

### Currently Supported
- **ZScore**: Statistical anomaly detection
  - Parameter: `observedValue` (field to monitor)

### Future Support (Framework Ready)
- **ARMA**: Time series forecasting
- **KMeans**: Clustering-based detection
- **IForest**: Isolation forest anomaly detection

## Error Handling

The system provides detailed error messages for:
- Invalid SQL syntax
- Missing or mismatched field names
- Invalid CRON expressions
- MongoDB connection failures
- Algorithm parameter validation errors

## Migration Notes

### From ES|QL to SQL
- **Query Language**: `FROM index | STATS ...` → `SELECT ... FROM index GROUP BY ...`
- **Date Functions**: `DATE_TRUNC(1 hour, @timestamp)` → `DATE_TRUNC('hour', "@timestamp")`
- **Conditional Counts**: `COUNT(*) WHERE condition` → `COUNT(CASE WHEN condition THEN 1 END)`
- **Field References**: `@timestamp` → `"@timestamp"` (quoted for SQL)

### Configuration Updates
- **Storage**: File-based → MongoDB
- **Structure**: Flattened → Nested scheduling objects
- **Algorithms**: Threshold-based → Field-based only

This migration provides unlimited scalability while maintaining all core anomaly detection functionality.
"""
    return description


@mcp.tool()
def list_available_algorithms() -> str:
    """
    List all available DA algorithms and their parameters.

    This tool returns information about supported anomaly detection algorithms
    by examining the available algorithm classes and their specifications.

    Returns:
        JSON string containing algorithm specifications
    """
    # Define all possible algorithms with their specifications
    algorithm_specs = {
        "ZScore": {
            "name": "ZScore",
            "description": "Statistical anomaly detection using standard deviation thresholds",
            "class_name": "ZScore",
            "parameters": [
                {
                    "name": "observedValue",
                    "type": "string",
                    "required": True,
                    "description": "Field name from SQL query output to monitor for anomalies"
                }
            ],
            "example": {
                "observedValue": "request_count"
            }
        },
        "ARMA": {
            "name": "ARMA",
            "description": "Time series forecasting using AutoRegressive Moving Average",
            "class_name": "ARMA",
            "parameters": [
                {"name": "p", "type": "integer", "description": "AR order"},
                {"name": "d", "type": "integer", "description": "Differencing order"},
                {"name": "q", "type": "integer", "description": "MA order"},
                {"name": "observedValue", "type": "string", "description": "Time series field"}
            ]
        },
        "KMeans": {
            "name": "KMeans",
            "description": "Clustering-based anomaly detection",
            "class_name": "KMeans",
            "parameters": [
                {"name": "nClusters", "type": "integer", "description": "Number of clusters"},
                {"name": "observedValue", "type": "string", "description": "Field to cluster"}
            ]
        },
        "IForest": {
            "name": "IForest",
            "description": "Isolation Forest anomaly detection",
            "class_name": "IForest",
            "parameters": [
                {"name": "nEstimators", "type": "integer", "description": "Number of trees"},
                {"name": "contamination", "type": "float", "description": "Expected anomaly ratio"},
                {"name": "randomState", "type": "integer", "description": "Random seed"},
                {"name": "observedValue", "type": "string", "description": "Field to analyze"}
            ]
        }
    }

    # Check which algorithms are available in the current system
    available_algorithms = []
    future_algorithms = []

    for alg_key, alg_spec in algorithm_specs.items():
        try:
            # Try to get the class from globals
            alg_class = globals().get(alg_spec["class_name"])
            if alg_class:
                # Check if it's a proper algorithm class (has to_dict method)
                if hasattr(alg_class, 'to_dict'):
                    alg_info = alg_spec.copy()
                    alg_info["status"] = "Implemented"
                    available_algorithms.append(alg_info)
                else:
                    # Framework exists but not fully implemented
                    alg_info = alg_spec.copy()
                    alg_info["status"] = "Framework ready - implementation pending"
                    future_algorithms.append(alg_info)
            else:
                # Class doesn't exist yet
                alg_info = alg_spec.copy()
                alg_info["status"] = "Framework ready - implementation pending"
                future_algorithms.append(alg_info)
        except Exception as e:
            # Any error means the algorithm isn't available
            alg_info = alg_spec.copy()
            alg_info["status"] = "Framework ready - implementation pending"
            future_algorithms.append(alg_info)

    algorithms_info = {
        "available_algorithms": available_algorithms,
        "future_algorithms": future_algorithms,
        "usage_notes": [
            "Currently only ZScore is fully implemented",
            "All algorithms require observedValue to match SQL query output fields",
            "Framework is designed for easy addition of new algorithms",
            "Algorithm parameters are validated during configuration creation"
        ]
    }

    return json.dumps(algorithms_info, indent=2)


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
        parser.add_argument("--name", type=str, help="KB configuration name")
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
                "training_query": args.training_query or "SELECT DATE_TRUNC('hour', \"@timestamp\") AS es_timestamp, COUNT(CASE WHEN response = '200' THEN 1 END) AS status_code_200_counter, COUNT(CASE WHEN response >= '500' AND response < '600' THEN 1 END) AS status_code_5xx_counter FROM \".ds-kibana_sample_data_logs-*\" WHERE \"@timestamp\" >= '2025-10-01T00:00:00.000Z' AND \"@timestamp\" < '2025-11-01T00:00:00.000Z' GROUP BY DATE_TRUNC('hour', \"@timestamp\") ORDER BY es_timestamp",
                "from": args.training_from or "2025-09-01T00:00:00Z",
                "to": args.training_to or "2025-09-30T23:59:59Z",
                "training_window": args.training_window,
                "is_active": args.training_active
            }
            scheduling["training_config"] = training_config

            # Default detection config
            detection_config = {
                "detection_query": args.detection_query or "SELECT DATE_TRUNC('hour', \"@timestamp\") AS es_timestamp, COUNT(CASE WHEN response = '200' THEN 1 END) AS status_code_200_counter, COUNT(CASE WHEN response >= '500' AND response < '600' THEN 1 END) AS status_code_5xx_counter FROM \".ds-kibana_sample_data_logs-*\" WHERE \"@timestamp\" >= '2025-10-10T00:00:00.000Z' AND \"@timestamp\" < '2025-10-11T00:00:00.000Z' GROUP BY DATE_TRUNC('hour', \"@timestamp\") ORDER BY es_timestamp",
                "from": args.detection_from or "2025-10-10T00:00:00Z",
                "frequency": args.detection_frequency or "*/15 * * * *",
                "detection_window": args.detection_window,
                "is_active": args.detection_active
            }
            scheduling["detection_config"] = detection_config

            kb_config = KBConfig(
                name=args.name or "Test Configuration",
                description=args.description or "Test configuration for anomaly detection",
                change_flag=0,  # Always start with 0 for new configs
                scheduling=scheduling,
                da_alg_parameters={
                    "zscore": [
                        {"dimension": "status_code_200_counter"},
                        {"dimension": "status_code_5xx_counter"}
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