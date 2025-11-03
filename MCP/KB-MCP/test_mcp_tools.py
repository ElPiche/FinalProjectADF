#!/usr/bin/env python3
"""
test_mcp_tools.py - Quick test script to verify MCP tools are properly registered.
"""

import asyncio
import importlib.util
import sys

async def test_mcp_tools():
    """Test that all MCP tools are properly registered with descriptions."""
    try:
        # Load the mcp_tools module directly
        spec = importlib.util.spec_from_file_location('mcp_tools_shim', 'mcp_tools.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        print('✓ MCP instance created successfully')

        # Get tools
        tools = await module.mcp.list_tools()
        print(f'✓ Tools registered: {len(tools)}')

        tool_names = [tool.name for tool in tools]
        print(f'✓ Tool names: {tool_names}')

        expected_tools = 7
        if len(tools) != expected_tools:
            print(f'✗ Expected {expected_tools} tools, got {len(tools)}')
            return False

        # Check descriptions
        all_have_descriptions = True
        for tool in tools:
            desc_len = len(tool.description) if tool.description else 0
            if desc_len == 0:
                print(f'✗ Tool {tool.name}: missing description!')
                all_have_descriptions = False
            else:
                print(f'✓ Tool {tool.name}: description length = {desc_len}')

        if all_have_descriptions:
            print('\n🎉 All tests passed! MCP tools are properly configured.')
            return True
        else:
            print('\n❌ Some tools are missing descriptions.')
            return False

    except Exception as e:
        print(f'✗ Test failed with error: {e}')
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = asyncio.run(test_mcp_tools())
    sys.exit(0 if success else 1)