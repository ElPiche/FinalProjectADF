#!/usr/bin/env python3
import sys
sys.path.insert(0, '/app')
from mcp_tools_pkg.modify_kb_config import modify_kb_config
from models import ZScoreConfig

# Override MongoDB connection for local testing
import db
db.mongo_connection_string = "mongodb://admin:1q2w3E*@localhost:27017/?authSource=admin&replicaSet=rs0&directConnection=true"

# Create test algorithm config using ZScoreConfig model
zscore_config = ZScoreConfig(dimensions=["bytes"])

# Test config ID (from previously created config)
test_config_id = "69080ca0fa82d20eb549daec"

# Run the test
print("Testing modify_kb_config with algorithm update...")

try:
    result = modify_kb_config(
        config_id=test_config_id,
        description="Updated test configuration via modify_kb_config",
        algorithms=[zscore_config]
    )
    print('SUCCESS: modify_kb_config test passed')
    print(result)
except Exception as e:
    print(f'ERROR: modify_kb_config test failed: {e}')
    print('Note: This test requires a valid config_id from a previously created configuration')