"""
algorithms.py - Algorithm parsing and validation utilities for MCP tools.
"""

from typing import List, Union
from mcp.server.fastmcp.exceptions import ToolError


def parse_algorithms_to_internal_format(algorithms: List) -> List[dict]:
    """
    Convert AlgorithmConfigItem objects to internal dictionary format.

    Args:
        algorithms: List of AlgorithmConfigItem objects or dictionaries

    Returns:
        List of algorithm dictionaries in internal format
    """
    internal_algorithms = []

    for alg in algorithms:
        if hasattr(alg, 'alg_name') and hasattr(alg, 'alg_parameters'):
            # It's an AlgorithmConfigItem object
            alg_dict = {
                "alg_name": alg.alg_name,
                "alg_parameters": []
            }

            for param in alg.alg_parameters:
                if hasattr(param, 'dimension'):
                    param_dict = {"dimension": param.dimension}
                    if hasattr(param, 'alg_metadata') and param.alg_metadata is not None:
                        param_dict["alg_metadata"] = param.alg_metadata
                    alg_dict["alg_parameters"].append(param_dict)

            internal_algorithms.append(alg_dict)
        elif isinstance(alg, dict):
            # Already in dictionary format
            internal_algorithms.append(alg)
        else:
            raise ToolError(f"Unsupported algorithm format: {type(alg)}")

    return internal_algorithms


def validate_algorithm_dimensions(algorithms: List, available_fields: List[str], query_type: str) -> None:
    """
    Validate that algorithm dimensions exist in the available fields from SQL query.

    Args:
        algorithms: List of AlgorithmConfigItem objects
        available_fields: List of field names available from the SQL query
        query_type: Type of query ("training" or "detection") for error messages

    Raises:
        ToolError: If any algorithm dimension is not found in available fields
    """
    for alg in algorithms:
        if hasattr(alg, 'alg_parameters'):
            # AlgorithmConfigItem object
            for param in alg.alg_parameters:
                if hasattr(param, 'dimension'):
                    dimension = param.dimension
                    if dimension not in available_fields:
                        raise ToolError(
                            f"Algorithm dimension '{dimension}' not found in {query_type} query output fields. "
                            f"Available fields: {available_fields}"
                        )
        elif isinstance(alg, dict):
            # Dictionary format
            for param in alg.get('alg_parameters', []):
                if isinstance(param, dict) and 'dimension' in param:
                    dimension = param['dimension']
                    if dimension not in available_fields:
                        raise ToolError(
                            f"Algorithm dimension '{dimension}' not found in {query_type} query output fields. "
                            f"Available fields: {available_fields}"
                        )