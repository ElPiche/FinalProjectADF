#!/usr/bin/env python3
"""
Manual test that calls `create_da_config` directly. Moved to `tests/` to avoid accidental module imports.

Be careful: running this will call into the create flow and may write to MongoDB.
"""

import asyncio
import sys
import os
# Ensure package root (KB-MCP) is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from mcp_tools_pkg.create_da_config import create_da_config
from models import ZScoreConfig

# Create a proper ZScoreConfig object
zscore_config = ZScoreConfig(alg_name='zscore', alg_parameters=[{'dimension': 'bytes'}])

# Define queries
training_q = 'SELECT timestamp, bytes FROM ".ds-kibana_sample_data_logs-2025.11.02-000001" WHERE timestamp >= "2025-10-01" AND timestamp < "2025-11-01"'
detection_q = 'SELECT timestamp, bytes FROM ".ds-kibana_sample_data_logs-2025.11.02-000001" WHERE timestamp >= NOW() - INTERVAL 1 HOUR'

def main():
    # Call the function directly
    result = asyncio.run(
        create_da_config(
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
    )

    print('KB Config created successfully:')
    print(result)


if __name__ == '__main__':
    main()
