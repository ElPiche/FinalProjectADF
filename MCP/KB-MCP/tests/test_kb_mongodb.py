#!/usr/bin/env python3
"""
This script was a container-integration test that inserts a KB config directly into MongoDB.
It is potentially intrusive (uses admin credentials) so it's placed under `tests/` to avoid accidental runs.

If you want to run it, review and set the `connection_string` variable appropriately for your environment.
"""

from pymongo import MongoClient
import sys
import os

# Ensure package root on path for local imports if needed
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

connection_string = 'mongodb://admin:1q2w3E*@mongodb:27017/?authSource=admin&replicaSet=rs0'

def main():
    print('Testing KB configuration creation from kb-mcp test script...')
    try:
        client = MongoClient(connection_string)
        kb_db = client['knowledge_base']
        kb_collection = kb_db['kb_configs']

        kb_config = {
            'name': 'test-kb-from-tests-folder',
            'description': 'Test KB config created from tests/test_kb_mongodb.py',
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

        insert_result = kb_collection.insert_one(kb_config)
        print('KB configuration inserted with ID:', insert_result.inserted_id)

        found_config = kb_collection.find_one({'_id': insert_result.inserted_id})
        print('Retrieved KB config name:', found_config['name'])
        print('Retrieved KB config description:', found_config['description'])

        print('SUCCESS: KB configuration saved to MongoDB from tests script!')

    except Exception as e:
        print('ERROR:', str(e))
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
