#!/usr/bin/env python3
"""Test MCP create_da_config with anomaly_config via direct function call"""
import asyncio
import sys

# Add app directory to path
sys.path.insert(0, '/app')

from mcp_tools import create_da_config
from models import QueryMode, AlgorithmConfig, AlgorithmParameter, AnomalyConfig

async def test_mcp_email():
    """Test that anomaly_config with user_emails works via MCP tool"""
    print("Testing create_da_config with anomaly_config...")
    
    result = await create_da_config(
        name='MCP-Email-Via-Function',
        description='Testing email via direct MCP function call',
        elasticsearch_sql_query='SELECT DATE_TRUNC(\'minute\', "@timestamp") AS es_timestamp, COUNT(*) AS request_count FROM ".ds-kibana_sample_data_logs-*" WHERE "@timestamp" >= \'$from\' AND "@timestamp" < \'$to\' GROUP BY es_timestamp ORDER BY es_timestamp',
        query_mode=QueryMode(type='aggregated', timestamp_field='es_timestamp'),
        training_from='2025-11-01T00:00:00Z',
        training_to='2025-11-28T23:59:59Z',
        training_is_active=True,
        detection_is_active=True,
        detection_frequency='*/5 * * * *',
        detection_window=300,
        detection_start='2025-11-29T00:00:00Z',
        algorithm=AlgorithmConfig(
            name='zscore',
            parameters=[AlgorithmParameter(dimension='request_count', is_active=True)]
        ),
        bucket_profile_id='enterprise_24x7',
        source_index='.ds-kibana_sample_data_logs-*',
        anomaly_config=AnomalyConfig(user_emails=['fidel.techera@estudiantes.utec.edu.uy'])
    )
    
    print("Result:")
    print(result)
    
    # Verify in MongoDB
    from db import connect_mongodb, db_kb_name, db_kb_collection_name
    client = connect_mongodb()
    if client:
        db = client[db_kb_name]
        collection = db[db_kb_collection_name]
        doc = collection.find_one({'name': 'MCP-Email-Via-Function'}, {'name': 1, 'anomaly_config': 1})
        print("\nMongoDB Document:")
        print(doc)
        if doc and doc.get('anomaly_config', {}).get('user_emails'):
            print("\n✅ SUCCESS: Email was saved correctly via MCP tool!")
        else:
            print("\n❌ FAILED: Email was NOT saved")
        client.close()

if __name__ == '__main__':
    asyncio.run(test_mcp_email())
