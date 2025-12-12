# Fire Test Replication Guide (Updated)

This guide explains how to run a modern "Fire Test" of the ADF stack using the current repository layout and Docker Compose.

Prerequisites
------------
- Docker & Docker Compose
- Python 3.11+ (for local testing) and common libs (pymongo, pandas, numpy)
- A working clone of the repo and a healthy Docker environment

Step 1 — Start the infrastructure
---------------------------------

1) From project root, start all services:

```pwsh
cd C:\path\to\FinalProjectADF
docker-compose up -d
```

2) Verify main services are healthy:

```pwsh
docker ps
```

Essential services that should be running: `elasticsearch-dataset`, `elasticsearch-anomalies`, `kibana`, `kibana-anomalies`, `mongodb`, `kb-mcp`, `etl-app` (extractor), `da-dispatcher`, and `logstash`.

Note: The `log-generator` is an optional load generator and will not start by default. Only use it for fire/stress tests by launching Docker Compose with the `stress` or `generate-logs` profile (see Step 0 / Fire Test using Log Generator). For normal development and tests, do not enable the stress profile.

Step 0 — Optional: Run a Fire Test using the Log Generator
---------------------------------------------------------
If you want to execute a Fire Test with a high throughput synthetic workload, use the `log-generator` service. The repository's `docker-compose.yml` defines a `log-generator` service (profiles: stress, generate-logs) that can be started with a profile. The log generator supports environment variables that you can modify to control traffic volume, burst behavior, and other settings.

Important: Running the stress profile will use additional CPU and memory; tune `BASE_REQUESTS_PER_HOUR`, `NUM_WORKERS`, and `CHUNK_SIZE` to avoid saturating the host. Consider running this in a separate machine or cloud instance if you need high throughput.

1) Optional: If you want to override the generator's environment variables, edit the `docker-compose.yml` file directly or pass an env-file name of your choice via `--env-file <your-file>` when starting Docker Compose. The generator works out-of-the-box with defaults and does not require any specific predefined env file.

2) Start the stack with stress profile (Windows PowerShell example):

```pwsh
# Launch infrastructure and stress generators (no env file required)
docker-compose --profile stress up -d --build
```

3) Verify the `log-generator` and `logstash` containers are running:

```pwsh
docker ps --filter name=log-generator --filter name=logstash
```

4) Monitor logs for the `log-generator` to track generated event throughput:

```pwsh
docker logs -f log-generator
```

5) Quick validation: Use KB-MCP to create a KB based on an index (ecommerce-logs) and short detection window. See Step 3 for KB config template and create the KB using the `kb-mcp` CLI.

6) Validate that Extractor has created training series (an `anomaly_detection.series` collection) and that the DA Dispatcher consumes series and produces models/anomalies. See Step 5 and Step 6 for details on how to verify.

7) Clean-up (stop only the stress components or everything):

```pwsh
# Stop log generator only
docker stop log-generator
# Or stop the whole stack including stress profile
docker-compose --profile stress down
```

Step 2 — Confirm Elasticsearch & sample data
-------------------------------------------

1) Confirm Elasticsearch is accessible:

```pwsh
curl -X GET "localhost:9200/_cluster/health?pretty"
```

2) If you need sample data (Kibana sample logs), the `kibana-init` container adds it automatically when the stack initializes.

Step 3 — Create KB Configurations (modern schema)
-------------------------------------------------

Use the KB-MCP CLI or FastMCP tool to create KB configurations. The modern schema uses `elasticsearch_sql_query`, `query_mode`, `source_index`, an `algorithm` object, and `scheduling` containing `training_config`/`detection_config`.

Example (ZScore, aggregated hourly):

```json
{
  "name": "http-5xx-errors",
  "description": "Monitors 5xx error counts",
  "source_index": "ecommerce-logs",
  "elasticsearch_sql_query": "FROM \"ecommerce-logs\" WHERE @timestamp >= '$from' AND @timestamp < '$to' | EVAL es_timestamp = DATE_TRUNC('hour', @timestamp) | STATS COUNT(CASE WHEN response >= 500 AND response < 600 THEN 1 ELSE NULL END) AS error_5xx_count BY es_timestamp | SORT es_timestamp",
  "query_mode": {"type": "aggregated", "timestamp_field": "es_timestamp"},
  "algorithm": {"name": "zscore", "parameters": [{"dimension": "error_5xx_count", "is_active": true}]},
  "scheduling": {
    "training_config": {"from": "2025-10-01T00:00:00Z", "to": "2025-10-09T23:59:59Z", "is_active": true},
    "detection_config": {"frequency": "*/5 * * * *", "detection_window": 3600, "is_active": true}
  }
}
```

Create the KB using the KB-MCP CLI (run inside the container to ensure network access):

```pwsh
docker exec -i kb-mcp python kb-mcp.py --kb-config '{...json...}'
```

Note: If you provide a legacy schema (algorithms instead of algorithm) KB-MCP will attempt migration but it is better to use the new schema.

Step 4 — Verify KB configs & start ETL
-------------------------------------

1) Verify KB configs are present in MongoDB `knowledge_base.kb_configs` and via MCP tool:

```pwsh
docker exec -i kb-mcp python kb-mcp.py --list-kb-configurations
```

2) The Extractor (etl-app) monitors KB definitions and, after a new KB is created, will materialize queries and create training series in MongoDB `anomaly_detection.series`.

Step 5 — Check MongoDB data
---------------------------

Check DBs and collections (replace with actual KB IDs):

```pwsh
docker exec mongodb mongosh -u admin -p '1q2w3E*' --authenticationDatabase admin --eval "show dbs"
docker exec mongodb mongosh -u admin -p '1q2w3E*' --authenticationDatabase admin --eval "use anomaly_detection; db.getCollectionNames();"
docker exec mongodb mongosh -u admin -p '1q2w3E*' --authenticationDatabase admin --eval "use anomaly_detection; db['series'].countDocuments({ 'metadata.kbId': 'REPLACE_WITH_KB_ID' })"
```

Training series are stored in `anomaly_detection.series` with `metadata.mode` 0 for training and 1 for detection.

Step 6 — Run DA Dispatcher & Verify Detection
--------------------------------------------

The DA-Dispatcher (`da-dispatcher`) will read KB configs and process training/detection. Start via Docker Compose or run the module directly for development:

```pwsh
docker exec -it da-dispatcher sh -c "python -m MotorDA.Dispatcher.DADispatcher"
```

Verify logs for training and detection steps:

```pwsh
docker logs da-dispatcher --tail 200
docker logs etl-app --tail 200
```

Step 7 — Troubleshooting
-------------------------

- Query syntax: Use double quotes for ES SQL identifiers; KB-MCP validates queries using the Extractor service. Double-check your query via `elasticsearch_sql` tool.
- CRON: Use a valid CRON expression for `detection_config.frequency` (5-field or 6-field with seconds). The Extractor validates sub-minute CRON expressions.
- DB names: KB configs are stored in `knowledge_base`, series and training models in `anomaly_detection`.

Validation Checklist
--------------------
- [ ] Docker Compose services are up & healthy
- [ ] KBs present in `knowledge_base.kb_configs`
- [ ] Training series are present in `anomaly_detection.series`
- [ ] Trained models saved in `anomaly_detection.trained_models`
- [ ] Detection results appear in Elasticsearch (anomalies index)

Notes
-----
- When developing locally, prefer `python -m MotorDA.Dispatcher.DADispatcher` to run dispatcher on the host rather than inside the container.
- Avoid using deprecated `Deployer` scripts — use `kb-mcp` CLI and the Extractor APIs.
- `create_da_config` performs unified validation using the extractor validation endpoints; if extractor is unavailable the tool will fall back to basic validation and warn you.

If you'd like, I can also update the 'Fire_Test_Commands.md' and other command examples that still reference legacy `detection_frequency: "5m"` or `Deployer/deployer.py` to the modern format. Let me know and I'll apply these changes across docs.
