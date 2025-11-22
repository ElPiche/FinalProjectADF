#!/usr/bin/env python3
import sys
sys.path.insert(0, '/app')
from mcp_tools_pkg.create_da_config import create_da_config
from models import ZScoreConfig
import json
from unittest.mock import patch

if __name__ != "__main__":
    import pytest

    pytest.skip("Manual test script; run directly instead of via pytest", allow_module_level=True)

# Override MongoDB connection for local testing
import db
db.mongo_connection_string = "mongodb://admin:1q2w3E*@localhost:27017/?authSource=admin&replicaSet=rs0&directConnection=true"

# Mock elasticsearch_sql to avoid external dependencies
def mock_elasticsearch_sql(query):
    # Return a mock response with the expected columns
    mock_response = {
        "columns": [{"name": "bytes"}],
        "rows": []
    }
    return json.dumps(mock_response)

# Create algorithm config using ZScoreConfig model
zscore_config = ZScoreConfig(dimensions=["bytes"])

# Define queries
training_q = 'SELECT bytes FROM test_table'
detection_q = 'SELECT bytes FROM test_table'

# Run the test with mocked elasticsearch
with patch('mcp_tools_pkg.elasticsearch_sql.elasticsearch_sql', side_effect=mock_elasticsearch_sql):
    result = create_da_config(
        name='test-kb-manual-check-direct',
        description='Test KB configuration created directly in Python',
        training_query=training_q,
        detection_query=detection_q,
        training_from='2025-10-01T00:00:00Z',
        training_to='2025-10-31T23:59:59Z',
        detection_frequency='0 */5 * * * *',
        detection_start='2025-11-02T20:00:00Z',
        algorithms=[zscore_config]
    )

print('KB Config created successfully:')
print(result)