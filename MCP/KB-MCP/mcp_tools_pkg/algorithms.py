"""
algorithms.py - Algorithm parsing and validation utilities for MCP tools.
"""

from typing import Iterable, List, Union
from mcp.server.fastmcp.exceptions import ToolError


def _iter_algorithms(algorithms: Union[List, dict, object]) -> Iterable:
    if algorithms is None:
        return []
    if isinstance(algorithms, (list, tuple, set)):
        return algorithms
    return [algorithms]


def parse_algorithms_to_internal_format(algorithms: Union[List, dict, object]) -> List[dict]:
    """Convert AlgorithmConfig objects to internal dictionaries (legacy + new schema)."""

    internal_algorithms: List[dict] = []

    for alg in _iter_algorithms(algorithms):
        if hasattr(alg, "model_dump"):
            internal_algorithms.append(alg.model_dump(by_alias=True))
        elif isinstance(alg, dict):
            internal_algorithms.append(alg)
        else:
            raise ToolError(f"Unsupported algorithm format: {type(alg)}")

    return internal_algorithms


def validate_algorithm_dimensions(algorithms: Union[List, dict, object], available_fields: List[str], query_type: str) -> None:
    """
    Validate that algorithm dimensions exist in the available fields from SQL query.

    Args:
        algorithms: List of AlgorithmConfigItem objects
        available_fields: List of field names available from the SQL query
        query_type: Type of query ("training" or "detection") for error messages

    Raises:
        ToolError: If any algorithm dimension is not found in available fields
    """
    for alg in _iter_algorithms(algorithms):
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
        elif hasattr(alg, "parameters"):
            for param in getattr(alg, "parameters", []) or []:
                dimension = getattr(param, "dimension", None)
                if dimension and dimension not in available_fields:
                    raise ToolError(
                        f"Algorithm dimension '{dimension}' not found in {query_type} query output fields. "
                        f"Available fields: {available_fields}"
                    )