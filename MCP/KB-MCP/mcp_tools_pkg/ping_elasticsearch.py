import uuid
import time
from utils import log_message as _utils_log_message


def log_message(message: str, level: str = "info", component: str = "mcp_tools", method: str = "entry", **kwargs):
    return _utils_log_message(level, component, method, message, **kwargs)


def ping_elasticsearch_debug():
    request_id = str(uuid.uuid4())[:8]
    try:
        import db
        hosts_to_try = []
        try:
            primary = db.es_host
            if primary:
                hosts_to_try.extend(h.strip() for h in str(primary).split(",") if h.strip())
        except Exception:
            hosts_to_try.append("http://elasticsearch-dataset:9200")

        hosts_to_try.extend([
            "http://localhost:9200",
            "http://elasticsearch-dataset:9200",
            "http://elasticsearch:9200",
            "http://127.0.0.1:9200"
        ])

        seen = set()
        candidate_hosts = []
        for h in hosts_to_try:
            if h not in seen:
                seen.add(h)
                candidate_hosts.append(h)

        from elasticsearch import Elasticsearch
        for host in candidate_hosts:
            try:
                log_message(f"Pinging Elasticsearch candidate host: {host}", "info", "ping_elasticsearch_debug", "entry",
                            request_id=request_id, extra_data={"host": host})
                print(f"[KB-MCP] Pinging Elasticsearch host: {host}")
                es = Elasticsearch(host, timeout=2)
                try:
                    if es.ping():
                        info = {}
                        try:
                            info = es.info()
                        except Exception as e_info:
                            log_message(f"es.info() failed for {host}: {str(e_info)}", "warning",
                                        "ping_elasticsearch_debug", "info_fail", request_id=request_id,
                                        extra_data={"host": host, "error_type": type(e_info).__name__})
                            print(f"[KB-MCP] es.info() failed for {host}: {e_info}")
                        log_message(f"Elasticsearch ping successful for {host}", "info",
                                    "ping_elasticsearch_debug", "success", request_id=request_id,
                                    extra_data={"host": host, "info": info})
                        print(f"[KB-MCP] Ping successful for {host} - info: {info}")
                        return host
                    else:
                        log_message(f"Elasticsearch ping returned False for {host}", "warning",
                                    "ping_elasticsearch_debug", "ping_false", request_id=request_id,
                                    extra_data={"host": host})
                        print(f"[KB-MCP] Ping returned False for {host}")
                except Exception as e:
                    log_message(f"Elasticsearch ping attempt raised for {host}: {str(e)}", "warning",
                                "ping_elasticsearch_debug", "ping_exception", request_id=request_id,
                                extra_data={"host": host, "error_type": type(e).__name__})
                    print(f"[KB-MCP] Ping exception for {host}: {e}")
            except Exception as e_outer:
                log_message(f"Failed to construct Elasticsearch client for {host}: {str(e_outer)}", "warning",
                            "ping_elasticsearch_debug", "client_exception", request_id=request_id,
                            extra_data={"host": host, "error_type": type(e_outer).__name__})
                print(f"[KB-MCP] Client construction failed for {host}: {e_outer}")

        log_message("All Elasticsearch ping attempts failed", "error",
                    "ping_elasticsearch_debug", "all_failed", request_id=request_id,
                    extra_data={"hosts_tried": len(candidate_hosts)})
        print("[KB-MCP] All Elasticsearch ping attempts failed")
        return False
    except Exception as e:
        try:
            log_message(f"Ping helper unexpected error: {str(e)}", "error",
                        "ping_elasticsearch_debug", "error", request_id=request_id,
                        extra_data={"error_type": type(e).__name__})
        except Exception:
            pass
        print(f"[KB-MCP] Ping helper unexpected error: {e}")
        return False


def ping_elasticsearch() -> str:
    request_id = str(uuid.uuid4())[:8]
    start = time.time()
    try:
        success = ping_elasticsearch_debug()
        duration_ms = (time.time() - start) * 1000
        log_message(f"ping_elasticsearch tool completed: {success}", "info",
                    "ping_elasticsearch", "completion", request_id=request_id,
                    duration_ms=duration_ms, extra_data={"ping_success": success})
        print(f"[KB-MCP] ping_elasticsearch result: {success}")
        import json
        return json.dumps({"ping_success": success, "duration_ms": duration_ms})
    except Exception as e:
        duration_ms = (time.time() - start) * 1000
        log_message(f"ping_elasticsearch tool error: {str(e)}", "error",
                    "ping_elasticsearch", "error", request_id=request_id,
                    duration_ms=duration_ms, extra_data={"error_type": type(e).__name__})
        print(f"[KB-MCP] ping_elasticsearch error: {e}")
        import json
        return json.dumps({"ping_success": False, "error": str(e), "duration_ms": duration_ms})

