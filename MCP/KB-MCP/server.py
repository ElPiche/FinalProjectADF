#!/usr/bin/env python3
import json
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("structured-output-server")

@mcp.tool()
def structure_output(text: str, format_type: str = "json") -> str:
    """
    Format text into structured output (JSON, XML, or YAML).

    Use this tool when you need to present information in a structured, machine-readable format.
    This is especially useful for:
    - API responses
    - Configuration data
    - Structured lists or objects
    - Data that needs to be parsed by other systems

    Args:
        text: The text content to format into structured output
        format_type: The output format - "json" (default), "xml", or "yaml"

    Returns:
        The input text formatted as structured output in the specified format

    Examples:
        Input: "name: John, age: 30, city: NYC"
        JSON Output: {"name": "John", "age": "30", "city": "NYC"}
    """
    try:
        if format_type.lower() == "json":
            # Try to parse as JSON first, if not, wrap in JSON
            try:
                parsed = json.loads(text)
                return json.dumps(parsed, indent=2)
            except json.JSONDecodeError:
                return json.dumps({"structured_output": text}, indent=2)
        elif format_type.lower() == "xml":
            # Simple XML wrapping
            return f"<structured_output>{text}</structured_output>"
        elif format_type.lower() == "yaml":
            # Simple YAML-like format
            return f"structured_output: {text}"
        else:
            return f"Unsupported format: {format_type}. Supported: json, xml, yaml"
    except Exception as e:
        return f"Error formatting output: {str(e)}"

@mcp.tool()
def create_da_config(query: str = "data", start_date: str = "", end_date: str = "", algorithm: str = "zScore") -> str:
    """
    Create a Data Analytics (DA) algorithm configuration with the specified parameters.

    This tool generates a structured configuration for DA algorithms that includes:
    - Elastic query parameters
    - Scheduling information (start/end dates)
    - Algorithm parameters

    The configuration is saved to da-config.json file and returned as JSON string.

    Args:
        query: The elastic query string (default: "data")
        start_date: Start date for scheduling (ISO format, e.g., "2024-01-01")
        end_date: End date for scheduling (ISO format, e.g., "2024-12-31")
        algorithm: The DA algorithm to use (default: "zScore")

    Returns:
        JSON string with the complete DA configuration structure
    """
    try:
        config = {
            "Query_elastic": {
                "query": query
            },
            "Scheduling": {
                "startDate": start_date,
                "endDate": end_date
            },
            "DA_Alg_Parameters": {
                "Algorithm": algorithm
            }
        }

        # Save to file
        with open("config/da-config.json", "w") as f:
            json.dump(config, f, indent=2)

        return json.dumps(config, indent=2)
    except Exception as e:
        return f"Error creating DA configuration: {str(e)}"

if __name__ == "__main__":
    mcp.run()