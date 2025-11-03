#!/usr/bin/env python3
from mcp_tools import create_da_config, list_available_algorithms

print("Testing dynamic docstrings...")
print("=" * 50)

print("Before calling functions:")
print("create_da_config.__doc__ is None:", create_da_config.__doc__ is None)
print("list_available_algorithms.__doc__ is None:", list_available_algorithms.__doc__ is None)

# Call the functions to trigger docstring generation
try:
    # These will fail but that's ok, we just want to trigger the docstring assignment
    create_da_config()
except Exception as e:
    print(f"create_da_config call failed (expected): {type(e).__name__}")

try:
    list_available_algorithms()
except Exception as e:
    print(f"list_available_algorithms call failed (expected): {type(e).__name__}")

print("\nAfter calling functions:")
print("create_da_config.__doc__ is None:", create_da_config.__doc__ is None)
print("list_available_algorithms.__doc__ is None:", list_available_algorithms.__doc__ is None)

if create_da_config.__doc__:
    print("create_da_config.__doc__ contains 'zscore':", 'zscore' in create_da_config.__doc__)
if list_available_algorithms.__doc__:
    print("list_available_algorithms.__doc__ contains 'zscore':", 'zscore' in list_available_algorithms.__doc__)

print("\nTest completed!")