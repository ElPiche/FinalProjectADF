#!/usr/bin/env python3
from pymongo import MongoClient
import sys

# Use the working connection string
connection_string = 'mongodb://admin:1q2w3E*@mongodb:27017/?authSource=admin&replicaSet=rs0'

if __name__ != "__main__":
    import pytest

    pytest.skip("Manual MongoDB test; run directly instead of via pytest", allow_module_level=True)

print('Testing KB configuration creation from kb-mcp container...')
try:
    client = MongoClient(connection_string)

    # Access the knowledge_base database (same as existing configs)
    kb_db = client['knowledge_base']
    kb_collection = kb_db['kb_configs']

    # Create a simple KB configuration entry
    kb_config = {
        'name': 'test-kb-from-container',
        'description': 'Test KB config created directly from kb-mcp container',
        'change_flag': 0,
        'scheduling': {
            'training_config': {
                'training_query': 'SELECT @timestamp, bytes FROM ".ds-kibana_sample_data_logs-2025.11.02-000001" WHERE @timestamp >= "2025-10-01" AND @timestamp < "2025-11-01"',
                'from': '2025-10-01T00:00:00Z',
                'to': '2025-10-31T23:59:59Z',
                'training_window': 3600,
                'is_active': True
            },
            'detection_config': {
                'detection_query': 'SELECT @timestamp, bytes FROM ".ds-kibana_sample_data_logs-2025.11.02-000001" WHERE @timestamp >= NOW() - INTERVAL 1 HOUR',
                'from': '2025-11-02T20:00:00Z',
                'frequency': '0 */10 * * * *',
                'detection_window': 3600,
                'is_active': False
            }
        },
        'algorithms': [
            {
                'alg_name': 'zscore',
                'alg_parameters': [
                    {'dimension': 'bytes'}
                ]
            }
        ]
    }

    # Insert the KB configuration
    insert_result = kb_collection.insert_one(kb_config)
    print('KB configuration inserted with ID:', insert_result.inserted_id)

    # Verify the entry was inserted
    found_config = kb_collection.find_one({'_id': insert_result.inserted_id})
    print('Retrieved KB config name:', found_config['name'])
    print('Retrieved KB config description:', found_config['description'])

    print('SUCCESS: KB configuration saved to MongoDB from kb-mcp container!')

except Exception as e:
    print('ERROR:', str(e))
    import traceback
    traceback.print_exc()