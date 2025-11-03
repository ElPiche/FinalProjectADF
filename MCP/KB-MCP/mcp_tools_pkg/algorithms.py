"""algorithms.py - Shared algorithm parsing utilities for KB-MCP tools

Provides consistent algorithm parsing and validation for create_da_config and modify_kb_config.
"""

from typing import List, Dict, Any
from mcp.server.fastmcp.exceptions import ToolError
from models import ZScoreConfig, AlgorithmConfig
from validation import validate_algorithms


def parse_algorithms_to_internal_format(algorithms: List[AlgorithmConfig]) -> List[Dict[str, Any]]:
    """
    Parse List[AlgorithmConfig] into internal storage format.
    
    This function handles the conversion from Pydantic AlgorithmConfig objects
    to the internal dict format used for storage and validation.
    
    Args:
        algorithms: List of AlgorithmConfig objects (ZScoreConfig, etc.)
        
    Returns:
        List of dicts in the format expected by validate_algorithms()
        
    Raises:
        ToolError: If algorithm type is unsupported
    """
    internal_algorithms = []
    
    for alg_config in algorithms:
        if isinstance(alg_config, ZScoreConfig):
            internal_algorithms.append({
                "alg_name": "zscore",
                "alg_parameters": [{"dimension": dim} for dim in alg_config.dimensions]
            })
        else:
            raise ToolError(f"Unsupported algorithm type: {type(alg_config)}")
    
    return internal_algorithms


def validate_algorithm_dimensions(algorithms: List[AlgorithmConfig], available_fields: List[str], query_type: str) -> None:
    """
    Validate that all algorithm dimensions exist in the query output fields.
    
    Args:
        algorithms: List of AlgorithmConfig objects
        available_fields: List of field names from SQL query output
        query_type: "training" or "detection" for error messages
        
    Raises:
        ToolError: If any dimension is not found in available fields
    """
    for alg_config in algorithms:
        if isinstance(alg_config, ZScoreConfig):
            for dimension in alg_config.dimensions:
                if dimension not in available_fields:
                    raise ToolError(f"Dimension '{dimension}' not found in {query_type} query output. Available fields: {available_fields}")