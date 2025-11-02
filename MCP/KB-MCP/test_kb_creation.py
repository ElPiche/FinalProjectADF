#!/usr/bin/env python3
import sys
sys.path.insert(0, '/app')
from mcp_tools_pkg.create_da_config import create_da_config
from models import ZScoreConfig

# Create a proper ZScoreConfig object
zscore_config = ZScoreConfig(algorithm='zscore', dimensions=['bytes'])

# Define queries
training_q = 'SELECT timestamp, bytes FROM ".ds-kibana_sample_data_logs-2025.11.02-000001" WHERE timestamp >= "2025-10-01" AND timestamp < "2025-11-01"'
detection_q = 'SELECT timestamp, bytes FROM ".ds-kibana_sample_data_logs-2025.11.02-000001" WHERE timestamp >= NOW() - INTERVAL 1 HOUR'

# Call the function directly
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