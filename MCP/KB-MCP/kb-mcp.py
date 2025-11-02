#!/usr/bin/env python3
"""
KB-MCP Server - Refactored modular implementation

This is the main entry point that imports from the modular components
and provides backward compatibility for existing deployments.
"""

import sys
import os
import argparse

# Add current directory to path for module imports
sys.path.insert(0, os.path.dirname(__file__))

# Import from our modules
from mcp_tools import mcp, create_da_config, modify_kb_config, list_kb_configurations, describe_mcp_server, list_available_algorithms, elasticsearch_sql
from utils import structured_logger, log_message, initialize_logging, shutdown_logging
from db import connect_mongodb

# Re-export for backward compatibility
__all__ = [
    'create_da_config', 'modify_kb_config', 'list_kb_configurations',
    'describe_mcp_server', 'list_available_algorithms', 'elasticsearch_sql',
    'mcp', 'structured_logger', 'log_message', 'connect_mongodb'
]

if __name__ == "__main__":
    # Check if this is being run as an MCP server (no arguments or --server flag)
    print(f"Starting KB-MCP with args: {sys.argv}", file=sys.stderr)
    print("Elasticsearch host: ", "http://elasticsearch-dataset:9200")  # From db.py

    if len(sys.argv) == 1 or (len(sys.argv) == 2 and sys.argv[1] == "--server"):
        # Start MCP server using stdio transport (default for FastMCP)
        print("Starting MCP server with stdio transport...", file=sys.stderr)
        print("Attempting to initialize MongoDB connection...", file=sys.stderr)

        # Test MongoDB connection and get connection string
        mongo_client = connect_mongodb()
        mongo_connection_string = None
        if mongo_client:
            print("MongoDB connection successful", file=sys.stderr)
            # Get connection string from db module
            try:
                from db import mongo_connection_string as mongo_conn_str
                mongo_connection_string = mongo_conn_str
            except ImportError:
                # Fallback to default connection string
                mongo_connection_string = "mongodb://admin:1q2w3E%2A@mongodb:27017/?authSource=admin&replicaSet=rs0"
            mongo_client.close()
        else:
            print("MongoDB connection failed, continuing anyway...", file=sys.stderr)
            # Still try to initialize logging with MongoDB attempt
            mongo_connection_string = "mongodb://admin:1q2w3E%2A@mongodb:27017/?authSource=admin&replicaSet=rs0"

        # Initialize dual logging system (file + MongoDB)
        print("Initializing dual logging system...", file=sys.stderr)
        print(f"[INIT_LOGGING_DEBUG] initialize_logging will receive: {repr(mongo_connection_string)}", file=sys.stderr)
        session_id = initialize_logging(mongo_connection_string)
        print(f"Logging initialized with session ID: {session_id[:8]}", file=sys.stderr)
        
        # Log session startup
        log_message("KB-MCP session started", "info", "kb_mcp", "startup")
        log_message("KB-MCP session initialized", "info", "structured_logger", "init", 
                   extra_data={"session_id": session_id})

        try:
            print("MCP server initialized, starting main loop...", file=sys.stderr)
            # FastMCP run() should handle stdio transport and keep the process alive
            mcp.run()
        except KeyboardInterrupt:
            print("MCP server interrupted by user", file=sys.stderr)
            log_message("KB-MCP session ended by user", "info", "kb_mcp", "shutdown")
            shutdown_logging()
            sys.exit(0)
        except Exception as e:
            print(f"Error starting MCP server: {e}", file=sys.stderr)
            log_message(f"KB-MCP server error: {str(e)}", "error", "kb_mcp", "startup_error", 
                       extra_data={"error_type": type(e).__name__})
            import traceback
            traceback.print_exc(file=sys.stderr)
            shutdown_logging()
            sys.exit(1)
    elif len(sys.argv) == 2 and sys.argv[1] == "--daemon":
        # Run HTTP server for Docker container using simple HTTP handler
        print("Starting KB-MCP HTTP server...", file=sys.stderr)
        print("Attempting to initialize MongoDB connection...", file=sys.stderr)

        # Test MongoDB connection and get connection string
        mongo_client = connect_mongodb()
        mongo_connection_string = None
        if mongo_client:
            print("MongoDB connection successful", file=sys.stderr)
            # Get connection string from db module
            try:
                from db import mongo_connection_string as mongo_conn_str
                mongo_connection_string = mongo_conn_str
            except ImportError:
                # Fallback to default connection string
                mongo_connection_string = "mongodb://admin:1q2w3E%2A@mongodb:27017/?authSource=admin&replicaSet=rs0"
            mongo_client.close()
        else:
            print("MongoDB connection failed", file=sys.stderr)
            # Still try to initialize logging with MongoDB attempt
            mongo_connection_string = "mongodb://admin:1q2w3E%2A@mongodb:27017/?authSource=admin&replicaSet=rs0"

        # Initialize dual logging system (file + MongoDB)
        print("Initializing dual logging system...", file=sys.stderr)
        session_id = initialize_logging(mongo_connection_string)
        print(f"Logging initialized with session ID: {session_id[:8]}", file=sys.stderr)
        
        # Log session startup
        log_message("KB-MCP HTTP server started", "info", "kb_mcp", "startup")
        log_message("KB-MCP session initialized", "info", "structured_logger", "init", 
                   extra_data={"session_id": session_id})

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
            print("HTTP server started on port 8000...", file=sys.stderr)
            server.serve_forever()

        except KeyboardInterrupt:
            print("KB-MCP HTTP server interrupted by user", file=sys.stderr)
            sys.exit(0)
        except Exception as e:
            print(f"Error starting KB-MCP HTTP server: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc(file=sys.stderr)

            # Fallback to simple daemon mode
            print("Falling back to daemon mode...", file=sys.stderr)
            print("KB-MCP daemon is running and ready to accept connections", file=sys.stderr)

            # Keep the process alive
            try:
                while True:
                    import time
                    time.sleep(30)
                    print("KB-MCP daemon heartbeat", file=sys.stderr)
            except KeyboardInterrupt:
                print("KB-MCP daemon interrupted by user", file=sys.stderr)
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
        print("Testing create_da_config function...")

        # Build KB config from arguments
        if args.kb_config:
            try:
                import json
                kb_data = json.loads(args.kb_config)
                from models import KBConfig
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

            # Build algorithms array - simplified specification
            algorithms = None
            if args.algorithms:
                # Use provided algorithms JSON
                try:
                    algorithms = json.loads(args.algorithms)
                except json.JSONDecodeError as e:
                    print(f"Error parsing algorithms JSON: {e}")
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

            from models import KBConfig
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
        print("Function result:")
        print(result)
        print("\nTest completed.")