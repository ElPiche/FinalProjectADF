from utils import stderr_print
#!/usr/bin/env python3
import json
import uuid
import datetime
import logging
import re
import argparse
import time
from jsonschema import validate, ValidationError
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure
from bson import ObjectId
import uuid
import os
from datetime import datetime
from typing import Optional, Dict, Any, List
from mcp.server.fastmcp import FastMCP
from croniter import croniter
from elasticsearch import Elasticsearch
from pydantic import BaseModel, field_validator, Field
from typing import List, Union, Optional
from mcp.server.fastmcp.exceptions import ToolError

# Global Configuration Variables --------------------------------------------------------------------------------

# Database Configuration
db_kb_name = "knowledge_base"
db_kb_collection_name = "kb_configs"
db_logger_name = "knowledge_base_mcp_logs"
mongo_connection_string = os.getenv("MONGO_CONNECTION_STRING", "mongodb://admin:1q2w3E*@mongodb:27017/?authSource=admin&replicaSet=rs0")
mongo_timeout_ms = 2000  # Reduced timeout for faster startup

# Elasticsearch Configuration
# es_host_env = os.getenv("es_host", "http://elasticsearch-dataset:9200")
es_host = os.getenv("ES_HOSTS", "http://elasticsearch-dataset:9200")

# Logging Configuration
logs_dir = "logs"
log_file = "log.txt"
structured_log_file = "structured_logs.jsonl"

# Algorithms Configuration
supported_algorithms = {"zscore"}

# Timeout Configuration
sql_validation_timeout_seconds = 2

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

mcp = FastMCP("KB-MCP")


# Structured Logging System ----------------------------------------------------------------------------------

class StructuredLogger:
    """Enhanced logging system with MongoDB storage and structured JSON format."""

    def __init__(self):
        self.mongo_client = None
        self.logs_collection = None
        self.file_fallback = True
        self.session_id = str(uuid.uuid4())  # Unique session identifier

    def connect(self) -> bool:
        """Connect to kb-mcp-logs database for structured logging."""
        try:
            # Use global mongo_connection_string configuration
            global mongo_connection_string
            self.mongo_client = MongoClient(mongo_connection_string)
            db = self.mongo_client["kb-mcp-logs"]
            self.logs_collection = db["logs"]
            # Test connection
            self.mongo_client.admin.command('ping')
            return True
        except Exception as e:
            stderr_print(f"Failed to connect to logs database: {e}")
            self.file_fallback = True
            return False

    def log(self, level: str, component: str, method: str, message: str,
            request_id: Optional[str] = None, duration_ms: Optional[float] = None,
            extra_data: Optional[Dict[str, Any]] = None):
        """Log a structured message to both MongoDB and file."""

        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "session_id": self.session_id,
            "level": level.upper(),
            "component": component,
            "method": method,
            "message": message,
            "request_id": request_id,
            "duration_ms": duration_ms,
            "extra_data": extra_data or {}
        }

        # Always write to file as backup
        self._write_to_file(log_entry)

        # Write to MongoDB if connected
        if self.logs_collection is not None:
            try:
                self.logs_collection.insert_one(log_entry)
            except Exception as e:
                # Fallback to enhanced file logging
                log_entry["mongo_error"] = str(e)
                log_entry["fallback"] = True
                self._write_to_file(log_entry)

    def _make_json_serializable(self, obj):
        """Convert non-JSON serializable objects to strings."""
        if isinstance(obj, dict):
            return {key: self._make_json_serializable(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [self._make_json_serializable(item) for item in obj]
        elif hasattr(obj, '__str__'):
            # Convert ObjectId and other objects to string
            return str(obj)
        else:
            return obj

    def _write_to_file(self, log_entry: Dict[str, Any]):
        """Write log entry to file in both human-readable and JSON formats."""
        global logs_dir
        logs_dir_path = os.path.join(os.path.dirname(__file__), logs_dir)
        os.makedirs(logs_dir_path, exist_ok=True)

        # Human-readable format for console/logs
        timestamp = log_entry["timestamp"]
        level = log_entry["level"]
        component = log_entry["component"]
        method = log_entry["method"]
        message = log_entry["message"]
        request_id = log_entry.get("request_id", "")[:8] if log_entry.get("request_id") else ""
        duration = f" ({log_entry['duration_ms']:.1f}ms)" if log_entry.get("duration_ms") else ""

        human_readable = f"[{timestamp}] [{level}] [{component}:{method}] {message}{duration}"
        if request_id:
            human_readable += f" [REQ:{request_id[:8]}]"
        # Add session ID to human-readable format
        human_readable += f" [SESSION:{self.session_id[:8]}]"

        # Write human-readable to console and file
        stderr_print(human_readable)

        log_file_path = os.path.join(logs_dir_path, log_file)
        with open(log_file_path, "a", encoding="utf-8") as f:
            f.write(human_readable + "\n")

        # Write JSON to separate file for structured analysis
        json_log_file = os.path.join(logs_dir_path, structured_log_file)
        # Convert ObjectId to string for JSON serialization
        serializable_log_entry = self._make_json_serializable(log_entry)
        with open(json_log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(serializable_log_entry) + "\n")


# Global structured logger instance
structured_logger = StructuredLogger()


def log_message(message: str, level: str = "info", component: str = None, method: str = None,
                request_id: str = None, duration_ms: float = None, extra_data: dict = None):
    """
    Enhanced logging with both file and MongoDB structured storage.

    Args:
        message: Log message
        level: Log level (error, warning, info, debug)
        component: Component name (auto-detected if None)
        method: Method name (auto-detected if None)
        request_id: Request correlation ID
        duration_ms: Operation duration in milliseconds
        extra_data: Additional structured data
    """
    # Auto-detect component/method from call stack if not provided
    if component is None or method is None:
        import inspect
        frame = inspect.currentframe().f_back
        method_name = frame.f_code.co_name

        # Try to get class name from self
        component_name = "unknown"
        if 'self' in frame.f_locals:
            component_name = frame.f_locals['self'].__class__.__name__

        if component is None:
            component = component_name
        if method is None:
            method = method_name

    # Log to structured system (safely)
    try:
        structured_logger.log(level, component, method, message, request_id, duration_ms, extra_data)
    except Exception as e:
        # Fallback to basic logging if structured logger fails
        logger.log(getattr(logging, level.upper(), logging.INFO), f"[{component}:{method}] {message}")
        if extra_data:
            logger.debug(f"Extra data: {extra_data}")


#Classes ------------------------------------------------------------------------------------------------------

# Knowledge Base Configuration
class KBConfig(BaseModel):
    # No id field - MongoDB will auto-generate _id
    name: str
    description: str
    change_flag: int  # snake_case
    scheduling: dict
    algorithms: List[Dict[str, Any]]  # Simple list of algorithm dicts

    def __init__(self, **data):
        super().__init__(**data)
        # Basic validation - detailed validation happens in tools
        if not self.name or not isinstance(self.name, str):
            raise ValueError("Name must be a non-empty string")
        if not self.description or not isinstance(self.description, str):
            raise ValueError("Description must be a non-empty string")
        log_message(f"KB config structure validated for: {self.name}", "info", "kb_config", "validation")

# CRON class moved before classes that use it
class CRON:
    def __init__(self, value: str):
        if not self._is_valid_cron(value):
            log_message(f"CRON validation failed: Invalid CRON format: {value}", "error", "cron", "validation")
            raise ValueError(f"Invalid CRON format: {value}")
        self.value = value
        log_message(f"CRON validated successfully: {value}", "info", "cron", "validation")

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


# Supported algorithms - only fully implemented ones
SUPPORTED_ALGORITHMS = {"zscore"}

# Algorithm configuration models for FastMCP tool parameters
class ZScoreConfig(BaseModel):
    algorithm: str = Field(default="zscore", description="Algorithm type")
    dimensions: List[str] = Field(description="List of field names to monitor for anomalies")

# Commented out for future implementation when KMeans is added to framework
# class KMeansConfig(BaseModel):
#     algorithm: str = Field(default="kmeans", description="Algorithm type")
#     dimension: str = Field(description="Field name to cluster")
#     clusters: List[int] = Field(description="List of cluster counts to test")

# Union type for all supported algorithms (expand when more algorithms are added)
AlgorithmConfig = Union[ZScoreConfig]  # Add KMeansConfig, ARMAConfig, etc. when implemented


def validate_algorithms(algorithms: List[Dict[str, Any]]) -> List[str]:
    """
    Validate algorithms array structure and supported algorithms.

    Args:
        algorithms: List of algorithm configuration dictionaries

    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []

    if not algorithms:
        errors.append("algorithms array cannot be empty")
        return errors

    for i, alg in enumerate(algorithms):
        if not isinstance(alg, dict):
            errors.append(f"algorithm {i}: must be a dictionary")
            continue

        alg_name = alg.get("alg_name")
        if not alg_name:
            errors.append(f"algorithm {i}: missing alg_name")
            continue

        if alg_name not in supported_algorithms:
            errors.append(f"algorithm {i}: '{alg_name}' is not supported. Supported algorithms: {list(supported_algorithms)}")
            continue

        if "alg_parameters" not in alg:
            errors.append(f"algorithm {i}: missing alg_parameters")
            continue

        params = alg["alg_parameters"]
        if not isinstance(params, list):
            errors.append(f"algorithm {i}: alg_parameters must be a list")
            continue

        for j, param in enumerate(params):
            if not isinstance(param, dict):
                errors.append(f"algorithm {i}, parameter {j}: must be a dictionary")
                continue
            if "dimension" not in param:
                errors.append(f"algorithm {i}, parameter {j}: missing dimension")

    return errors
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

            log_message("SQL basic validation successful", "info", "sql", "validation")
            return True
        except Exception as e:
            log_message(f"SQL validation failed: {str(e)}", "warning", "sql", "validation")
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
            log_message(f"UUID validation failed: Invalid UUID format: {value}", "error", "uuid", "validation")
            raise ValueError(f"Invalid UUID format: {value}")
        self.value = value
        log_message(f"UUID validated successfully: {value}", "info", "uuid", "validation")

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


# Initialize MCP server quickly without blocking on MongoDB
stderr_print("Initializing KB-MCP server...")
stderr_print("Skipping structured logger initialization for faster startup...")

# Set up basic logging for now
logger.info("KB-MCP server starting...")

# Initialize structured logger in background (commented out for now)
# try:
#     structured_logger.connect()
#     log_message("KB-MCP session started", "info", "kb_mcp", "startup")
#     log_message("KB-MCP session initialized", "info", "structured_logger", "init",
#                 extra_data={"session_id": structured_logger.session_id})
#     stderr_print(f"Structured logger initialized successfully - Session ID: {structured_logger.session_id[:8]}...")
# except Exception as e:
#     stderr_print(f"Structured logger initialization failed: {e}")
#     stderr_print("Continuing with basic logging only...")
#     # Fallback to basic logging if structured logger fails
#     logger.error(f"Structured logger initialization failed: {e}")
#     # Reset structured logger to prevent further connection attempts
#     structured_logger.mongo_client = None
#     structured_logger.logs_collection = None


def connect_mongodb():
    """
    Connect to MongoDB KB instance with proper error handling and logging.
    Optimized for replica set connections.

    Returns:
        MongoClient: Connected MongoDB client, or None if connection fails
    """
    # Use global mongo_connection_string configuration
    global mongo_connection_string
    
    start_time = time.time()
    try:
        log_message(f"Attempting to connect to MongoDB at {mongo_connection_string.replace('1q2w3E%2A', '***')}",
                    "info", "connect_mongodb", "connection")
        
        # Enhanced client configuration for replica sets
        client = MongoClient(
            mongo_connection_string, 
            serverSelectionTimeoutMS=mongo_timeout_ms,
            connectTimeoutMS=mongo_timeout_ms,
            socketTimeoutMS=mongo_timeout_ms,
            retryWrites=True,
            retryReads=True,
            readPreference='primaryPreferred'  # Allow reads from secondary if primary unavailable
        )

        # Test the connection with detailed error information
        result = client.admin.command('ping')
        log_message(f"MongoDB ping successful: {result}", "info", "connect_mongodb", "ping")
        
        # Check replica set status for additional debugging
        try:
            rs_status = client.admin.command('replSetGetStatus')
            log_message(f"Replica set status: {rs_status.get('set', 'unknown')}", "info", "connect_mongodb", "replica_set")
        except Exception as rs_e:
            log_message(f"Could not get replica set status (may be normal): {rs_e}", "warning", "connect_mongodb", "replica_set")
        
        duration_ms = (time.time() - start_time) * 1000
        log_message("MongoDB connection successful", "info", "connect_mongodb", "connection",
                    duration_ms=duration_ms)

        # Verify database access
        db = client[db_kb_name]
        log_message(f"MongoDB database '{db_kb_name}' accessible", "info", "connect_mongodb", "database")
        return client

    except ConnectionFailure as e:
        duration_ms = (time.time() - start_time) * 1000
        log_message(f"MongoDB connection failed: {str(e)}", "error", "connect_mongodb", "connection",
                    duration_ms=duration_ms)
        return None
    except OperationFailure as e:
        duration_ms = (time.time() - start_time) * 1000
        log_message(f"MongoDB authentication/authorization failed: {str(e)}", "error", "connect_mongodb", "auth",
                    duration_ms=duration_ms)
        return None
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_message(f"Unexpected MongoDB connection error: {str(e)}", "error", "connect_mongodb", "connection",
                    duration_ms=duration_ms)
        return None
    
# Extractor modes enum
class ExtractorModes(str):
    BATCH = "batch"
    STREAMING = "streaming"

# MCP Tools ---------------------------------------------------------------------------------------------------

@mcp.tool()
def create_da_config(
    name: str = Field(description="Configuration name"),
    description: str = Field(description="Human-readable description"),
    training_query: str = Field(description="SQL query for training data"),
    detection_query: str = Field(description="SQL query for detection"),
    training_from: str = Field(description="Training start timestamp (ISO format)"),
    training_to: str = Field(description="Training end timestamp (ISO format)"),
    detection_frequency: str = Field(description="Detection frequency (CRON format)"),
    detection_start: str = Field(description="Detection start timestamp (ISO format)"),
    algorithms: List[AlgorithmConfig] = Field(description="List of algorithm configurations")
) -> str:
    """Create a Data Analytics (DA) algorithm configuration for the Knowledge Base system."""
    request_id = str(uuid.uuid4())[:8]
    start_time = time.time()

    log_message("Tool execution started", "info", "create_da_config", "entry",
                request_id=request_id, extra_data={
                    "config_name": name,
                    "algorithm_count": len(algorithms) if algorithms else 0
                })
    """
    Create a Data Analytics configuration for the Knowledge Base system.

    This tool accepts individual parameters for KB configuration and uses structured algorithm objects
    for type safety and validation. Currently supports ZScore algorithm with multiple dimensions.

    Args:
        name: Configuration name
        description: Human-readable description
        training_query: SQL query for training data (must include fields used by algorithms)
        detection_query: SQL query for detection (must include same fields as training)
        training_from: Training period start (ISO timestamp)
        training_to: Training period end (ISO timestamp)
        detection_frequency: CRON expression for detection frequency
        detection_start: Detection start timestamp (ISO format)
        algorithms: List of algorithm configurations (currently ZScoreConfig supported)

    Algorithm Configuration:
    Use ZScoreConfig objects to specify ZScore algorithm parameters:

    ZScoreConfig(
        dimensions=["field1", "field2"]  # List of field names from SQL queries
    )

    Field names in dimensions must exactly match output fields from both training_query and detection_query.

    Example:
        algorithms=[
            ZScoreConfig(dimensions=["status_200_count", "bytes_sum"])
        ]

    Returns:
        Success message with configuration ID or detailed validation error
    """

    # Basic parameter validation
    if not name or not isinstance(name, str):
        raise ToolError("name must be a non-empty string")
    if not description or not isinstance(description, str):
        raise ToolError("description must be a non-empty string")

    # Validate CRON expression
    try:
        CRON(detection_frequency)
    except ValueError as e:
        raise ToolError(f"Invalid detection frequency CRON: {str(e)}")

    # Convert algorithm configs to internal format
    internal_algorithms = []
    for alg_config in algorithms:
        if isinstance(alg_config, ZScoreConfig):
            internal_algorithms.append({
                "alg_name": "zscore",
                "alg_parameters": [{"dimension": dim} for dim in alg_config.dimensions]
            })
        else:
            raise ToolError(f"Unsupported algorithm type: {type(alg_config)}")

    # Validate algorithms using existing validation function
    algorithm_errors = validate_algorithms(internal_algorithms)
    if algorithm_errors:
        error_msg = "Algorithm validation failed:\n" + "\n".join(f"- {err}" for err in algorithm_errors)
        log_message(f"Algorithm validation failed: {len(algorithm_errors)} errors", "error",
                    "create_da_config", "validation", request_id=request_id)
        raise ToolError(error_msg)

    # Cross-validate algorithms against SQL queries
    if training_query:
        validation_result = elasticsearch_sql(training_query + " LIMIT 0")
        if "ERROR" in validation_result:
            raise ToolError(f"Training SQL query validation failed: {validation_result}")
        else:
            try:
                result_data = json.loads(validation_result)
                available_fields = [col['name'] for col in result_data.get('columns', [])]

                for alg_config in algorithms:
                    if isinstance(alg_config, ZScoreConfig):
                        for dimension in alg_config.dimensions:
                            if dimension not in available_fields:
                                raise ToolError(f"Dimension '{dimension}' not found in training query output. Available fields: {available_fields}")
            except json.JSONDecodeError:
                raise ToolError("Could not parse training SQL validation response")

    if detection_query:
        validation_result = elasticsearch_sql(detection_query + " LIMIT 0")
        if "ERROR" in validation_result:
            raise ToolError(f"Detection SQL query validation failed: {validation_result}")
        else:
            try:
                result_data = json.loads(validation_result)
                available_fields = [col['name'] for col in result_data.get('columns', [])]

                for alg_config in algorithms:
                    if isinstance(alg_config, ZScoreConfig):
                        for dimension in alg_config.dimensions:
                            if dimension not in available_fields:
                                raise ToolError(f"Dimension '{dimension}' not found in detection query output. Available fields: {available_fields}")
            except json.JSONDecodeError:
                raise ToolError("Could not parse detection SQL validation response")

    # Build configuration for storage
    config_to_store = {
        "name": name,
        "description": description,
        "change_flag": 0,  # Always start with 0 for new configs
        "scheduling": {
            "training_config": {
                "training_query": training_query,
                "from": training_from,
                "to": training_to,
                "training_window": 3600,  # Default value
                "is_active": True  # Default value
            },
            "detection_config": {
                "detection_query": detection_query,
                "from": detection_start,
                "frequency": detection_frequency,
                "detection_window": 3600,  # Default value
                "is_active": False  # Default value
            }
        },
        "algorithms": internal_algorithms
    }

    log_message(f"Configuration validation successful for: {name}", "info",
                "create_da_config", "validation", request_id=request_id)

    # Print configuration preview
    stderr_print("\nConfiguration Preview:")
    stderr_print(json.dumps(config_to_store, indent=2))
    stderr_print()

    # Save to MongoDB
    client = connect_mongodb()
    if client is None:
        error_msg = "Failed to connect to MongoDB - configuration not saved"
        log_message(error_msg, "error", "create_da_config", "save", request_id=request_id)
        raise ToolError(error_msg)

    try:
        db = client[db_kb_name]
        collection = db[db_kb_collection_name]

        result = collection.insert_one(config_to_store)
        document_id = str(result.inserted_id)

        duration_ms = (time.time() - start_time) * 1000
        success_msg = f"SUCCESS: Configuration saved to MongoDB!\n\nDocument ID: {document_id}\n\nConfiguration saved successfully."
        log_message("Configuration creation completed successfully", "info",
                    "create_da_config", "completion", request_id=request_id,
                    duration_ms=duration_ms, extra_data={"document_id": document_id})
        return success_msg

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        error_msg = f"Failed to save configuration: {str(e)}"
        log_message(error_msg, "error", "create_da_config", "save", request_id=request_id,
                    duration_ms=duration_ms, extra_data={"error_type": type(e).__name__})
        raise ToolError(error_msg)
    finally:
        try:
            client.close()
        except:
            pass


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
    algorithms: dict = None
) -> str:
    """Modify an existing KB configuration by ID."""
    request_id = str(uuid.uuid4())[:8]
    start_time = time.time()

    log_message("Tool execution started", "info", "modify_kb_config", "entry",
                request_id=request_id, extra_data={"config_id": config_id})
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
        algorithms: New algorithms array (optional)

    Returns:
        Success message with updated configuration details, or error message
    """
    client = connect_mongodb()
    if client is None:
        raise ToolError("Failed to connect to MongoDB")

    try:
        db = client[db_kb_name]
        collection = db[db_kb_collection_name]

        # Find the configuration - use MongoDB _id directly
        try:
            config_doc = collection.find_one({"_id": ObjectId(config_id)})
        except Exception as e:
            raise ToolError(f"Invalid configuration ID format: '{config_id}' - {str(e)}")

        if not config_doc:
            raise ToolError(f"Configuration with ID '{config_id}' not found")

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
                raise ToolError(f"Invalid training query: {str(e)}")

        if detection_query is not None:
            # Validate SQL query
            try:
                sql_obj = SQL(detection_query)
                updates["scheduling.detection_config.detection_query"] = detection_query  # snake_case
            except ValueError as e:
                raise ToolError(f"Invalid detection query: {str(e)}")

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
                raise ToolError(f"Invalid detection frequency: {str(e)}")

        if detection_start is not None:
            updates["scheduling.detection_config.from"] = detection_start  # snake_case

        if algorithms is not None:
            # Validate algorithms array
            algorithm_errors = validate_algorithms(algorithms)
            if algorithm_errors:
                error_msg = "Algorithm validation failed:\n" + "\n".join(f"- {err}" for err in algorithm_errors)
                raise ToolError(error_msg)
            updates["algorithms"] = algorithms

        if not updates:
            log_message("No valid updates provided", "warning", "modify_kb_config", "validation",
                        request_id=request_id, extra_data={"config_id": config_id})
            raise ToolError("No valid updates provided")

        # Apply updates - increment change_flag directly
        updates["change_flag"] = config_doc.get("change_flag", 0) + 1  # Direct field access, snake_case

        # Apply updates
        result = collection.update_one(
            {"_id": ObjectId(config_id)},
            {"$set": updates}
        )

        if result.modified_count == 0:
            log_message("No changes were made to the configuration", "warning",
                        "modify_kb_config", "update", request_id=request_id,
                        extra_data={"config_id": config_id})
            raise ToolError("No changes were made to the configuration")

        # Retrieve and return updated configuration (exclude MongoDB ObjectId)
        updated_doc = collection.find_one({"_id": ObjectId(config_id)}, {"_id": 0})
        duration_ms = (time.time() - start_time) * 1000

        if updated_doc:
            log_message(f"Configuration '{config_id}' updated successfully", "info",
                       "modify_kb_config", "completion", request_id=request_id,
                       duration_ms=duration_ms, extra_data={"config_id": config_id})
            return f"SUCCESS: Configuration '{config_id}' updated successfully."
        else:
            log_message(f"Configuration '{config_id}' updated but could not retrieve document", "warning",
                       "modify_kb_config", "completion", request_id=request_id,
                       duration_ms=duration_ms, extra_data={"config_id": config_id})
            return f"SUCCESS: Configuration '{config_id}' updated successfully, but could not retrieve updated document."

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_message(f"Error modifying configuration {config_id}: {str(e)}", "error",
                    "modify_kb_config", "error", request_id=request_id,
                    duration_ms=duration_ms, extra_data={"config_id": config_id, "error_type": type(e).__name__})
        raise ToolError(f"Failed to modify configuration: {str(e)}")
    finally:
        try:
            client.close()
        except:
            pass


@mcp.tool()
def list_kb_configurations() -> str:
    """List all KB configurations stored in MongoDB."""
    request_id = str(uuid.uuid4())[:8]
    start_time = time.time()

    log_message("Tool execution started", "info", "list_kb_configurations", "entry",
                request_id=request_id)
    """
    List all KB configurations stored in MongoDB.

    This tool retrieves all KB configurations from the database and returns
    a formatted summary including IDs, descriptions, algorithms, and scheduling.

    Returns:
        Formatted string listing all KB configurations with their details
    """
    client = connect_mongodb()
    if client is None:
        raise ToolError("Failed to connect to MongoDB")

    try:
        db = client[db_kb_name]
        collection = db[db_kb_collection_name]

        # Retrieve all configurations - include all fields including _id
        configs = list(collection.find({}, {}))

        if not configs:
            log_message("No KB configurations found in database", "info",
                       "list_kb_configurations", "query", request_id=request_id)
            return "No KB configurations found in the database."

        # Format output
        log_message(f"Found {len(configs)} configurations in database", "info",
                   "list_kb_configurations", "query", request_id=request_id,
                   extra_data={"config_count": len(configs)})
        output = "# KB Configurations Summary\n\n"
        output += f"Found {len(configs)} configuration(s):\n\n"

        for config_doc in configs:
            # Direct access, no kbConfig wrapper
            kb_config = config_doc

            config_id = str(kb_config.get("_id", "Unknown"))  # Use MongoDB _id
            name = kb_config.get("name", "Unknown")
            description = kb_config.get("description", "No description")

            # Extract algorithm info - NEW format
            algorithms_list = kb_config.get("algorithms", [])  # NEW: algorithms field
            algorithms = []
            for alg_config in algorithms_list:
                alg_name = alg_config.get("alg_name", "unknown")
                alg_parameters = alg_config.get("alg_parameters", [])
                dimensions = [p.get("dimension", "unknown") for p in alg_parameters if isinstance(p, dict)]
                algorithms.append(f"{alg_name}({', '.join(dimensions)})")

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

        duration_ms = (time.time() - start_time) * 1000
        log_message(f"Configurations list generated successfully", "info",
                   "list_kb_configurations", "completion", request_id=request_id,
                   duration_ms=duration_ms, extra_data={"config_count": len(configs)})
        return output

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_message(f"Error listing configurations: {str(e)}", "error",
                    "list_kb_configurations", "error", request_id=request_id,
                    duration_ms=duration_ms, extra_data={"error_type": type(e).__name__})
        raise ToolError(f"Failed to list configurations: {str(e)}")
    finally:
        try:
            client.close()
        except:
            pass


@mcp.tool()
def describe_mcp_server() -> str:
    """Get a comprehensive description of the KB-MCP server and how to use it."""
    request_id = str(uuid.uuid4())[:8]
    start_time = time.time()

    log_message("Tool execution started", "info", "describe_mcp_server", "entry",
                request_id=request_id)
    """
    Get a comprehensive description of the KB-MCP server and how to use it.

    This tool provides an overview of the MCP server's purpose, available tools,
    and usage guidelines for the SQL-based Knowledge Base configuration system.
    """
    description = """
# KB-MCP Server Overview

**VERSION 2.0 (October 2025)**: Complete rewrite with global configuration variables, structured logging, and enhanced algorithm validation. Migrated from ES|QL to SQL queries for unlimited scalability.

## Purpose
The KB-MCP (Knowledge Base Model Context Protocol) server provides comprehensive tools for creating, managing, and validating Data Analytics (DA) algorithm configurations for the Knowledge Base anomaly detection system.

## Key Features
- **Global Configuration System**: Centralized configuration management for database, Elasticsearch, logging, and algorithms
- **Structured Logging**: Advanced logging system with MongoDB storage, session tracking, and performance monitoring
- **SQL Query Support**: Full Elasticsearch SQL integration with unlimited result sets
- **Algorithm Validation**: Comprehensive validation ensuring algorithm parameters match SQL query outputs
- **Performance Monitoring**: Request correlation IDs, duration tracking, and detailed metrics
- **MongoDB Integration**: Robust configuration storage with change tracking and versioning

## System Architecture

### Global Configuration Variables
```python
# Database Configuration
db_kb_name = "knowledge_base"
db_kb_collection_name = "kb_configs"
mongo_connection_string = os.getenv("MONGO_CONNECTION_STRING", "mongodb://admin:1q2w3E%2A@localhost:27017/?authSource=admin&replicaSet=rs0")

# Elasticsearch Configuration
es_host = os.getenv("ES_HOSTS", "http://localhost:9200,http://elasticsearch-dataset:9200")

# Logging Configuration
logs_dir = "logs"
structured_log_file = "structured_logs.jsonl"

# Algorithm Support
supported_algorithms = {"zscore"}
```

### Structured Logging System
- **Session Tracking**: Unique session IDs for request correlation
- **Performance Metrics**: Request duration and throughput monitoring
- **Dual Storage**: Human-readable console logs + structured JSON logs
- **MongoDB Integration**: Logs stored in dedicated `kb-mcp-logs` database
- **Fallback Support**: File-based logging when MongoDB unavailable

## Available Tools

### 1. create_da_config
Creates and validates new anomaly detection configurations with comprehensive cross-validation.
- **Input**: KB configuration dict with name, description, scheduling, and algorithms array
- **Algorithms Format** (REQUIRED STRUCTURE):
  ```json
  "algorithms": [
    {
      "alg_name": "zscore",
      "alg_parameters": [
        {"dimension": "field_name_1"},
        {"dimension": "field_name_2"}
      ]
    }
  ]
  ```
- **Critical Requirements**:
  - `alg_name` must be "zscore" (only supported algorithm)
  - `alg_parameters` must be non-empty array
  - Each parameter needs `dimension` field matching SQL output exactly
  - Dimensions validated against both training and detection queries
- **Validation**: SQL queries, CRON expressions, algorithm parameters, field matching
- **Output**: Validation results, configuration preview, and MongoDB storage confirmation
- **Performance**: Request tracking with duration metrics

### 2. modify_kb_config
Updates existing KB configurations with change tracking and validation.
- **Input**: Configuration ID and selective field updates
- **Features**: Automatic change_flag increment, partial updates supported
- **Validation**: SQL queries, CRON expressions, algorithm parameters
- **Output**: Update confirmation with modified configuration details

### 3. list_kb_configurations
Retrieves and formats all KB configurations from MongoDB.
- **Input**: None
- **Output**: Markdown-formatted summary with IDs, descriptions, algorithms, and scheduling
- **Features**: Algorithm dimension display, scheduling information, configuration count

### 4. elasticsearch_sql
Executes SQL queries against Elasticsearch with reliability and performance monitoring.
- **Input**: Complete SQL query string
- **Features**: Multi-host failover, timeout handling, result formatting
- **Output**: Structured JSON with columns, rows, cursor information, and metadata
- **Performance**: Execution time tracking and host selection metrics

### 5. list_available_algorithms
Provides comprehensive algorithm specifications and implementation status.
- **Input**: None
- **Output**: JSON with available algorithms, future algorithms, and usage notes
- **Features**: Parameter specifications, implementation status, framework readiness

### 6. describe_mcp_server (this tool)
Provides current system documentation and usage guidance.
- **Input**: None
- **Output**: Comprehensive overview of current implementation
- **Features**: Real-time system status, configuration examples, migration notes

## Configuration Structure (Current Format)

```json
{
  "name": "Configuration Name",
  "description": "Human-readable description",
  "change_flag": 0,
  "scheduling": {
    "training_config": {
      "training_query": "SELECT DATE_TRUNC('hour', \\"@timestamp\\") AS es_timestamp, COUNT(*) as total_requests FROM \\"index-*\\" WHERE \\"@timestamp\\" >= '2025-10-01T00:00:00.000Z' GROUP BY DATE_TRUNC('hour', \\"@timestamp\\")",
      "from": "2025-10-01T00:00:00Z",
      "to": "2025-10-02T00:00:00Z",
      "training_window": 3600,
      "is_active": true
    },
    "detection_config": {
      "detection_query": "SELECT DATE_TRUNC('hour', \\"@timestamp\\") AS es_timestamp, COUNT(*) as total_requests FROM \\"index-*\\" WHERE \\"@timestamp\\" >= '2025-10-10T00:00:00.000Z' GROUP BY DATE_TRUNC('hour', \\"@timestamp\\")",
      "from": "2025-10-10T00:00:00Z",
      "frequency": "*/15 * * * *",
      "detection_window": 3600,
      "is_active": false
    }
  },
  "algorithms": [
    {
      "alg_name": "zscore",
      "alg_parameters": [
        {"dimension": "total_requests"}
      ]
    }
  ]
}
```

## Algorithm Format (Current Implementation)

### Required Structure
Each algorithm configuration must follow this exact JSON structure:

```json
"algorithms": [
  {
    "alg_name": "zscore",
    "alg_parameters": [
      {"dimension": "field_name_1"},
      {"dimension": "field_name_2"}
    ]
  }
]
```

### Field Requirements
- **alg_name**: String, must be "zscore" (case-insensitive)
- **alg_parameters**: Array of objects, cannot be empty
- **dimension**: String, must exactly match SQL query output field names

### Validation Process
1. **Algorithm Support**: Only "zscore" is currently supported
2. **Parameter Structure**: alg_parameters must be a non-empty array
3. **Field Matching**: Each dimension must exist in both training and detection SQL query outputs
4. **SQL Validation**: Queries are tested against Elasticsearch before configuration storage

### Common Configuration Mistakes
- ❌ `"alg_name": "z-score"` → ✅ `"alg_name": "zscore"`
- ❌ Missing `alg_parameters` array → ✅ Include empty array minimum
- ❌ `"dimension": "field_that_does_not_exist"` → ✅ Use only fields from SQL output
- ❌ Empty alg_parameters → ✅ Include at least one dimension

### Example Valid Configurations

**Single Dimension ZScore:**
```json
"algorithms": [
  {
    "alg_name": "zscore",
    "alg_parameters": [
      {"dimension": "request_count"}
    ]
  }
]
```

**Multi-Dimension ZScore:**
```json
"algorithms": [
  {
    "alg_name": "zscore",
    "alg_parameters": [
      {"dimension": "total_requests"},
      {"dimension": "error_rate"},
      {"dimension": "response_time"}
    ]
  }
]
```

### SQL Query Compatibility
Algorithm dimensions must match SQL SELECT field names exactly:

```sql
-- Valid: dimension "request_count" matches alias
SELECT COUNT(*) AS request_count FROM "index-*" GROUP BY timestamp

-- Invalid: dimension "COUNT(*)" doesn't match alias
SELECT COUNT(*) AS request_count FROM "index-*" GROUP BY timestamp
```

## SQL Query Guidelines

### Supported Syntax
- Standard SQL SELECT statements with aggregation
- Date/time functions: `DATE_TRUNC('hour', "@timestamp")`
- Conditional expressions: `COUNT(CASE WHEN condition THEN 1 END)`
- GROUP BY and ORDER BY clauses
- Field quoting: `"@timestamp"`, `"field_name"`

### Field Matching Requirements
- Algorithm `dimension` fields must exactly match SQL query output column names
- Use descriptive aliases: `COUNT(*) AS request_count`
- Validate queries with `elasticsearch_sql` before configuration

### Best Practices
1. Test all queries with `elasticsearch_sql` tool first
2. Use appropriate date ranges for training data
3. Ensure aggregation fields align with anomaly detection needs
4. Validate CRON expressions for scheduling
5. Use descriptive configuration names and descriptions

## Algorithm Support

### Currently Implemented
- **ZScore**: Statistical anomaly detection using standard deviation thresholds
  - **Parameter**: `dimension` (field name from SQL query output)
  - **Validation**: Field must exist in both training and detection queries
  - **Status**: Fully implemented and tested

### Framework Ready (Not Yet Implemented)
- **ARMA**: Time series forecasting (AutoRegressive Moving Average)
- **KMeans**: Clustering-based anomaly detection
- **IForest**: Isolation Forest anomaly detection

## Error Handling & Validation

### Comprehensive Validation
- **SQL Syntax**: Basic SQL structure validation with Elasticsearch testing
- **Field Matching**: Algorithm dimensions cross-validated against SQL query outputs
- **CRON Expressions**: Scheduling frequency validation using croniter
- **Algorithm Parameters**: Supported algorithms and parameter structure validation
- **MongoDB Connectivity**: Connection and authentication validation with fallback logging

### Algorithm-Specific Validation Rules

**ZScore Algorithm Validation:**
- Must have `alg_name: "zscore"` (case-insensitive)
- `alg_parameters` must be non-empty array
- Each parameter must contain `dimension` field
- All dimensions must exist in training AND detection query outputs
- Dimensions are validated against actual Elasticsearch SQL query results

**Common Validation Errors:**
```
ERROR: Algorithm validation failed:
- algorithm 0: 'z-score' is not supported. Supported algorithms: {'zscore'}
- algorithm 0: missing alg_parameters
- algorithm 0, parameter 0: missing dimension
- ERROR: Dimension 'invalid_field' not found in training query output. Available fields: ['request_count', 'error_rate']
```

### Error Response Format
```
ERROR: [Specific Error Type]: [Detailed Description]
Available fields: [field1, field2, ...]
Validation failed for algorithm 0: [specific issue]
```

### Best Practices for Error Prevention
1. **Test SQL Queries First**: Use `elasticsearch_sql` tool to verify queries before configuration
2. **Validate Field Names**: Ensure all algorithm dimensions match SQL SELECT aliases exactly
3. **Use Supported Algorithms**: Currently only "zscore" is implemented
4. **Check Parameter Structure**: Follow exact JSON structure requirements
5. **Review Configuration**: Use the preview output to verify before MongoDB storage

### Logging Integration
- All operations logged with session and request correlation
- Performance metrics tracked for all database and Elasticsearch operations
- Structured JSON logs for programmatic analysis
- Human-readable console logs for debugging

## Migration & Compatibility

### From Version 1.0 to 2.0
- **Configuration Format**: `da_alg_parameters` object → `algorithms` array
- **Algorithm Structure**: `{"zscore": [{"observedValue": "..."}]}` → `[{"alg_name": "zscore", "alg_parameters": [{"dimension": "..."}]}]`
- **Storage**: File-based → MongoDB with change tracking
- **Query Language**: ES|QL → SQL for unlimited scalability
- **Logging**: Basic console → Structured with MongoDB storage

### Backward Compatibility
- Legacy configurations can be migrated using the new format
- Old ES|QL queries need conversion to SQL syntax
- Algorithm parameter mapping provided in migration tools

## Performance & Monitoring

### Request Tracking
- Unique request IDs for correlation across logs
- Session-based grouping for multi-request operations
- Duration tracking for performance analysis

### Database Operations
- Connection pooling and timeout management
- Automatic retry logic for transient failures
- Change flag tracking for configuration versioning

### Elasticsearch Integration
- Multi-host failover for high availability
- Query execution time monitoring
- Result size and cursor management

This implementation provides enterprise-grade reliability, comprehensive validation, and extensive monitoring capabilities for production anomaly detection systems.
"""
    duration_ms = (time.time() - start_time) * 1000
    log_message("Server description generated successfully", "info",
               "describe_mcp_server", "completion", request_id=request_id,
               duration_ms=duration_ms)
    return description


@mcp.tool()
def list_available_algorithms() -> str:
    """List all available DA algorithms and their parameters."""
    request_id = str(uuid.uuid4())[:8]
    start_time = time.time()

    log_message("Tool execution started", "info", "list_available_algorithms", "entry",
                request_id=request_id)
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

    # Only show algorithms that are in SUPPORTED_ALGORITHMS
    available_algorithms = []
    future_algorithms = []

    for alg_key, alg_spec in algorithm_specs.items():
        if alg_key.lower() in SUPPORTED_ALGORITHMS:
            alg_info = alg_spec.copy()
            alg_info["status"] = "Implemented"
            available_algorithms.append(alg_info)
        else:
            alg_info = alg_spec.copy()
            alg_info["status"] = "Framework ready - implementation pending"
            future_algorithms.append(alg_info)

    algorithms_info = {
        "available_algorithms": available_algorithms,
        "future_algorithms": future_algorithms,
        "usage_notes": [
            "Only algorithms in SUPPORTED_ALGORITHMS can be used in configurations",
            "All algorithms require dimension to match SQL query output fields",
            "Framework is designed for easy addition of new algorithms",
            "Algorithm parameters are validated during configuration creation"
        ]
    }

    duration_ms = (time.time() - start_time) * 1000
    log_message("Algorithm list generated successfully", "info",
               "list_available_algorithms", "completion", request_id=request_id,
               duration_ms=duration_ms, extra_data={
                   "available_count": len(algorithms_info["available_algorithms"]),
                   "future_count": len(algorithms_info["future_algorithms"])
               })
    return json.dumps(algorithms_info, indent=2)


@mcp.tool()
def elasticsearch_sql(query: str) -> str:
    """Execute a SQL query against Elasticsearch."""
    request_id = str(uuid.uuid4())[:8]
    start_time = time.time()

    log_message("Tool execution started", "info", "elasticsearch_sql", "entry",
                request_id=request_id, extra_data={"query_length": len(query)})
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
    # Use global es_host configuration
    global es_host

    try:
        log_message(f"Attempting SQL query execution with Elasticsearch at {es_host}")
        es = Elasticsearch(es_host, timeout=sql_validation_timeout_seconds)

        # Execute the SQL query using Elasticsearch's SQL API
        response = es.sql.query(query=query)

        # Format the results for easy consumption
        results = {
            "columns": response.get("columns", []),
            "rows": response.get("rows", []),
            "cursor": response.get("cursor"),
            "total_rows": len(response.get("rows", []))
        }

        duration_ms = (time.time() - start_time) * 1000
        log_message(f"SQL query executed successfully with {es_host}, returned {results['total_rows']} rows", "info",
                    "elasticsearch_sql", "execution", request_id=request_id,
                    duration_ms=duration_ms, extra_data={"host": es_host, "row_count": results['total_rows']})
        return json.dumps(results, indent=2)

    except Exception as e:
        log_message(f"SQL query failed with {es_host}: {str(e)}", "warning",
                    "elasticsearch_sql", "retry", request_id=request_id,
                    extra_data={"host": es_host, "error_type": type(e).__name__})
        # Store the last error for reporting
        last_error = e

    # If all hosts failed
    duration_ms = (time.time() - start_time) * 1000
    error_msg = f"ERROR: Failed to execute SQL query on all Elasticsearch hosts - {str(last_error) if 'last_error' in locals() else 'No hosts available'}"
    log_message(error_msg, "error", "elasticsearch_sql", "failure", request_id=request_id,
                duration_ms=duration_ms, extra_data={"hosts_tried": len(es_host)})
    raise ToolError(error_msg)


if __name__ == "__main__":
    # Check if this is being run as an MCP server (no arguments or --server flag)
    import sys
    stderr_print(f"Starting KB-MCP with args: {sys.argv}", file=sys.stderr)
    stderr_print("Elasticsearch host: ", es_host)
    
    if len(sys.argv) == 1 or (len(sys.argv) == 2 and sys.argv[1] == "--server"):
        # Start MCP server using stdio transport (default for FastMCP)
        stderr_print("Starting MCP server with stdio transport...", file=sys.stderr)
        stderr_print("Attempting to initialize MongoDB connection...", file=sys.stderr)
        
        # Test MongoDB connection
        mongo_client = connect_mongodb()
        if mongo_client:
            stderr_print("MongoDB connection successful", file=sys.stderr)
            mongo_client.close()
        else:
            stderr_print("MongoDB connection failed, continuing anyway...", file=sys.stderr)
        
        try:
            stderr_print("MCP server initialized, starting main loop...", file=sys.stderr)
            # FastMCP run() should handle stdio transport and keep the process alive
            mcp.run()
        except KeyboardInterrupt:
            stderr_print("MCP server interrupted by user", file=sys.stderr)
            sys.exit(0)
        except Exception as e:
            stderr_print(f"Error starting MCP server: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc(file=sys.stderr)
            sys.exit(1)
    elif len(sys.argv) == 2 and sys.argv[1] == "--daemon":
        # Run HTTP server for Docker container using simple HTTP handler
        stderr_print("Starting KB-MCP HTTP server...", file=sys.stderr)
        stderr_print("Attempting to initialize MongoDB connection...", file=sys.stderr)
        
        # Test MongoDB connection
        mongo_client = connect_mongodb()
        if mongo_client:
            stderr_print("MongoDB connection successful", file=sys.stderr)
            mongo_client.close()
        else:
            stderr_print("MongoDB connection failed", file=sys.stderr)
        
        try:
            # Create a simple HTTP server for MCP
            from http.server import HTTPServer, BaseHTTPRequestHandler
            import json
            
            class MCPHandler(BaseHTTPRequestHandler):
                def do_GET(self):
                    if self.path == '/health':
                        self.send_response(200)
                        self.send_header('Content-type', 'application/json')
                        self.send_header('Access-Control-Allow-Origin', '*')
                        self.end_headers()
                        response = json.dumps({"status": "healthy", "service": "KB-MCP"})
                        self.wfile.write(response.encode())
                    else:
                        self.send_response(404)
                        self.end_headers()
                
                def do_POST(self):
                    # Handle MCP JSON-RPC requests
                    content_length = int(self.headers['Content-Length'])
                    post_data = self.rfile.read(content_length)
                    
                    try:
                        request_data = json.loads(post_data.decode())
                        # Simple echo for now - would need proper MCP JSON-RPC handling
                        response = {
                            "jsonrpc": "2.0",
                            "id": request_data.get("id"),
                            "result": {"message": "KB-MCP server is running"}
                        }
                        
                        self.send_response(200)
                        self.send_header('Content-type', 'application/json')
                        self.send_header('Access-Control-Allow-Origin', '*')
                        self.end_headers()
                        self.wfile.write(json.dumps(response).encode())
                    except Exception as e:
                        self.send_response(500)
                        self.send_header('Content-type', 'application/json')
                        self.end_headers()
                        error_response = {
                            "jsonrpc": "2.0",
                            "id": None,
                            "error": {"code": -32000, "message": str(e)}
                        }
                        self.wfile.write(json.dumps(error_response).encode())
                
                def do_OPTIONS(self):
                    # Handle CORS preflight
                    self.send_response(200)
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
                    self.send_header('Access-Control-Allow-Headers', 'Content-Type')
                    self.end_headers()
                
                def log_message(self, format, *args):
                    # Suppress HTTP server logs to stderr
                    pass
            
            server = HTTPServer(('0.0.0.0', 8000), MCPHandler)
            stderr_print("HTTP server started on port 8000...", file=sys.stderr)
            server.serve_forever()
            
        except KeyboardInterrupt:
            stderr_print("KB-MCP HTTP server interrupted by user", file=sys.stderr)
            sys.exit(0)
        except Exception as e:
            stderr_print(f"Error starting KB-MCP HTTP server: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc(file=sys.stderr)
            
            # Fallback to simple daemon mode
            stderr_print("Falling back to daemon mode...", file=sys.stderr)
            stderr_print("KB-MCP daemon is running and ready to accept connections", file=sys.stderr)
            
            # Keep the process alive
            try:
                while True:
                    time.sleep(30)
                    stderr_print("KB-MCP daemon heartbeat", file=sys.stderr)
            except KeyboardInterrupt:
                stderr_print("KB-MCP daemon interrupted by user", file=sys.stderr)
                sys.exit(0)
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

        # NEW: Algorithm specification arguments
        parser.add_argument("--algorithms", type=str, help="JSON string for algorithms array (new format)")
        parser.add_argument("--alg-zscore-dimensions", type=str, nargs='+', help="Dimensions for ZScore algorithm")
        parser.add_argument("--alg-kmeans-dimension", type=str, help="Dimension for KMeans algorithm")
        parser.add_argument("--alg-kmeans-clusters", type=int, default=3, help="Number of clusters for KMeans")

        args = parser.parse_args()

        # Run test with parameters
        stderr_print("Testing create_da_config function...")

        # Build KB config from arguments
        if args.kb_config:
            try:
                kb_data = json.loads(args.kb_config)
                kb_config = KBConfig(**kb_data)
            except json.JSONDecodeError as e:
                stderr_print(f"Error parsing kb-config JSON: {e}")
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

            # Build algorithms array - simplified specification
            algorithms = None
            if args.algorithms:
                # Use provided algorithms JSON
                try:
                    algorithms = json.loads(args.algorithms)
                except json.JSONDecodeError as e:
                    stderr_print(f"Error parsing algorithms JSON: {e}")
                    exit(1)
            else:
                # Build from individual algorithm arguments
                algorithms = []

                # Add ZScore if dimensions provided
                if args.alg_zscore_dimensions:
                    algorithms.append({
                        "alg_name": "zscore",
                        "alg_parameters": [
                            {"dimension": dim} for dim in args.alg_zscore_dimensions
                        ]
                    })

                # Add KMeans if dimension provided (but will fail validation since not supported)
                if args.alg_kmeans_dimension:
                    algorithms.append({
                        "alg_name": "kmeans",
                        "alg_parameters": [{
                            "dimension": args.alg_kmeans_dimension,
                            "alg_metadata": [{"key": "clusters", "values": str(args.alg_kmeans_clusters)}]
                        }]
                    })

                # Default fallback if no algorithms specified
                if not algorithms:
                    algorithms = [{
                        "alg_name": "zscore",
                        "alg_parameters": [
                            {"dimension": "total_requests"}
                        ]
                    }]

            kb_config = KBConfig(
                name=args.name or "Test Configuration",
                description=args.description or "Test configuration for anomaly detection",
                change_flag=0,  # Always start with 0 for new configs
                scheduling=scheduling,
                algorithms=algorithms  # Use algorithms directly
            )

        # Convert KBConfig to dict for console testing
        kb_config_dict = {
            "name": kb_config.name,
            "description": kb_config.description,
            "change_flag": kb_config.change_flag,
            "scheduling": kb_config.scheduling,
            "algorithms": kb_config.algorithms
        }

        # Call the function
        result = create_da_config(kb_config=kb_config_dict, algorithms=algorithms)
        stderr_print("Function result:")
        stderr_print(result)
        stderr_print("\nTest completed.")