# profile_after.py - Profile the modular KB-MCP implementation

import cProfile
import pstats
import io
import sys
import os

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))

def profile_imports():
    """Profile module imports."""
    pr = cProfile.Profile()
    pr.enable()

    # Import all modules
    import models
    import validation
    import db
    import mcp_tools
    import utils
    import instrumentation

    pr.disable()
    return pr

def profile_basic_operations():
    """Profile basic operations like model creation and validation."""
    pr = cProfile.Profile()
    pr.enable()

    from models import KBConfig, ZScoreConfig, CRON
    from validation import validate_algorithms, extract_sql_output_fields

    # Create a test config
    config = KBConfig(
        name="Profile Test Config",
        description="Test description for profiling",
        change_flag=0,
        scheduling={
            "training_config": {
                "training_query": "SELECT field1, field2 FROM test_table",
                "from": "2025-01-01T00:00:00Z",
                "to": "2025-01-02T00:00:00Z",
                "training_window": 3600,
                "is_active": True
            },
            "detection_config": {
                "detection_query": "SELECT field1, field2 FROM test_table",
                "from": "2025-01-02T00:00:00Z",
                "frequency": "*/15 * * * *",
                "detection_window": 3600,
                "is_active": False
            }
        },
        algorithms=[{
            "alg_name": "zscore",
            "alg_parameters": [{"dimension": "field1"}]
        }]
    )

    # Test CRON validation
    cron = CRON("*/15 * * * *")

    # Test algorithm validation
    errors = validate_algorithms([{
        "alg_name": "zscore",
        "alg_parameters": [{"dimension": "field1"}]
    }])

    # Test SQL field extraction
    fields = extract_sql_output_fields("SELECT field1, field2 FROM table")

    pr.disable()
    return pr

def profile_instrumentation():
    """Profile instrumentation decorators."""
    pr = cProfile.Profile()
    pr.enable()

    from instrumentation import timed

    @timed
    def test_function():
        return sum(range(1000))

    result = test_function()

    pr.disable()
    return pr

def run_profiling():
    """Run all profiling tests and save results."""
    print("Profiling modular KB-MCP implementation...")

    # Profile imports
    print("Profiling imports...")
    pr_imports = profile_imports()
    s_imports = io.StringIO()
    ps_imports = pstats.Stats(pr_imports, stream=s_imports).sort_stats('cumulative')
    ps_imports.print_stats()

    # Profile basic operations
    print("Profiling basic operations...")
    pr_ops = profile_basic_operations()
    s_ops = io.StringIO()
    ps_ops = pstats.Stats(pr_ops, stream=s_ops).sort_stats('cumulative')
    ps_ops.print_stats()

    # Profile instrumentation
    print("Profiling instrumentation...")
    pr_inst = profile_instrumentation()
    s_inst = io.StringIO()
    ps_inst = pstats.Stats(pr_inst, stream=s_inst).sort_stats('cumulative')
    ps_inst.print_stats()

    # Save profiles
    with open('profile.after.imports', 'w') as f:
        f.write(s_imports.getvalue())
    print("Saved profile.after.imports")

    with open('profile.after.operations', 'w') as f:
        f.write(s_ops.getvalue())
    print("Saved profile.after.operations")

    with open('profile.after.instrumentation', 'w') as f:
        f.write(s_inst.getvalue())
    print("Saved profile.after.instrumentation")

    print("Profiling completed. Profile files saved.")

if __name__ == "__main__":
    run_profiling()