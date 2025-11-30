from utils import stderr_print
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
from models import AlgorithmConfig

# Create a proper AlgorithmConfig object
zscore_config = AlgorithmConfig(name='zscore', parameters=[{'dimension': 'bytes'}])

# Define query
unified_query = (
    "SELECT @timestamp, bytes FROM \".ds-kibana_sample_data_logs-2025.11.02-000001\" "
    "WHERE @timestamp >= '$from' AND @timestamp < '$to'"
)

def main():
    # Call the function directly
    result = asyncio.run(
        create_da_config(
            name='test-kb-manual-check-direct',
            description='Test KB configuration created directly in Python',
            elasticsearch_sql_query=unified_query,
            query_mode={'type': 'raw', 'timestamp_field': '@timestamp'},
            training_from='2025-10-01T00:00:00Z',
            training_to='2025-10-31T23:59:59Z',
            training_is_active=True,
            detection_is_active=True,
            detection_frequency='0 */5 * * * *',
            detection_start='2025-11-02T20:00:00Z',
            detection_window=3600,
            algorithm=zscore_config
        )
    )

    stderr_print('KB Config created successfully:')
    stderr_print(result)


if __name__ == '__main__':
    main()