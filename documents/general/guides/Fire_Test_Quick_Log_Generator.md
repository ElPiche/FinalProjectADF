```markdown
# Quick Fire Test — Log Generator

Purpose: Validate end-to-end flows quickly using the built-in `log-generator` service. Useful for smoke tests, verifying extractor/dispatcher behavior, and monitoring anomaly output. This guide is optional — do not start the log-generator unless you intend to run a stress test.

Prerequisites
- Docker & Docker Compose
- Docker host with CPU/memory capacity for the load configured
- `kb-mcp` and other services available via Docker Compose

Quick Run (Win PowerShell)
---------------------------
1) Optional: To configure the generator for a quick test, edit the `docker-compose.yml` service environment values, or pass a custom env file via `--env-file <your-file>` if you prefer (this is optional; defaults are sufficient for most tests).

2) Start everything with stress generation profile:

```pwsh
docker-compose --profile stress up -d --build
```

3) Create a quick KB (use 1-minute buckets, 1 minute detection frequency):

```pwsh
docker exec -i kb-mcp python kb-mcp.py --kb-config '{"name":"quick-fire","description":"Quick 1-min detection","source_index":"ecommerce-logs","elasticsearch_sql_query":"FROM \"ecommerce-logs\" WHERE @timestamp >= '$from' AND @timestamp < '$to' | EVAL es_timestamp = DATE_TRUNC(\"minute\", @timestamp) | STATS COUNT(CASE WHEN response >= 500 AND response < 600 THEN 1 ELSE NULL END) AS error_5xx_count BY es_timestamp | SORT es_timestamp","query_mode":{"type":"aggregated","timestamp_field":"es_timestamp"},"algorithm":{"name":"zscore","parameters":[{"dimension":"error_5xx_count","is_active":true}]},"scheduling":{"training_config":{"from":"2025-12-11T00:00:00Z","to":"2025-12-11T23:59:59Z","is_active":true},"detection_config":{"frequency":"*/1 * * * *","detection_window":60,"is_active":true}}}'
```

4) Monitor logs & health
```pwsh
docker logs -f log-generator
docker logs -f etl-app
docker logs -f da-dispatcher
```

5) Verify series produced by Extractor and models by Dispatcher:
```pwsh
docker exec mongodb mongosh -u admin -p '1q2w3E*' --authenticationDatabase admin --eval "use anomaly_detection; db['series'].count()"
docker exec mongodb mongosh -u admin -p '1q2w3E*' --authenticationDatabase admin --eval "use anomaly_detection; db['trained_models'].find().pretty()"
curl -s 'http://localhost:9201/anomaly_results/_search?pretty' | jq '.hits.hits'
```

6) Cleanup (stop generator):
```pwsh
docker stop log-generator
docker-compose --profile stress down
```

Notes & Tips
- Match the KB `source_index` with the log-generator `INDEX_NAME` (default `ecommerce-logs`).
- Set `HISTORICAL_DAYS` to a small number (1-2) for quicker tests; this reduces initial load creation time.
- Avoid excessively high `BASE_REQUESTS_PER_HOUR` on local machines to prevent resource starvation.
- For sub-minute detection frequency (e.g., every 10s), the extractor validates 6-field (Spring) CRON expressions. Use extractor validation endpoints when creating KBs to confirm the CRON expression is accepted.

```
