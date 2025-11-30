#!/usr/bin/env python3
"""Test script to verify email configuration works via create_da_config"""
import asyncio
from mcp_tools_pkg.create_da_config import create_da_config
from models import QueryMode, AlgorithmConfig, AlgorithmParameter, AnomalyConfig

async def test():
    result = await create_da_config(
        name='Email-Test-Direct-Python',
        description='Testing email via direct Python call',
        elasticsearch_sql_query='SELECT DATE_TRUNC(\'minute\', "@timestamp") AS es_timestamp, COUNT(*) AS request_count FROM ".ds-kibana_sample_data_logs-*" WHERE "@timestamp" >= \'$from\' AND "@timestamp" < \'$to\' GROUP BY es_timestamp ORDER BY es_timestamp',
        query_mode=QueryMode(type='aggregated', timestamp_field='es_timestamp'),
        training_from='2025-11-01T00:00:00Z',
        training_to='2025-11-28T23:59:59Z',
        training_is_active=True,
        detection_is_active=True,
        detection_frequency='*/5 * * * *',
        detection_window=300,
        detection_start='2025-11-29T00:00:00Z',
        algorithm=AlgorithmConfig(name='zscore', parameters=[AlgorithmParameter(dimension='request_count', is_active=True)]),
        bucket_profile_id='enterprise_24x7',
        source_index='.ds-kibana_sample_data_logs-*',
        anomaly_config=AnomalyConfig(user_emails=['fidel.techera@estudiantes.utec.edu.uy'])
    )
    print(result)

if __name__ == '__main__':
    asyncio.run(test())
