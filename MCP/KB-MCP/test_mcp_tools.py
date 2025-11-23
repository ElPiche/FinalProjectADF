from utils import stderr_print
#!/usr/bin/env python3
"""
test_mcp_tools.py - Quick test script to verify MCP tools are properly registered.
"""

import asyncio
import importlib.util
import sys


async def _run_mcp_tool_validation() -> bool:
    """Shared async routine so pytest and CLI can reuse the same logic."""
    # Load the mcp_tools module directly
    spec = importlib.util.spec_from_file_location("mcp_tools_shim", "mcp_tools.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    stderr_print("✓ MCP instance created successfully")

    tools = await module.mcp.list_tools()
    stderr_print(f"✓ Tools registered: {len(tools)}")

    tool_names = [tool.name for tool in tools]
    stderr_print(f"✓ Tool names: {tool_names}")

    expected_tools = 7
    if len(tools) != expected_tools:
        stderr_print(f"✗ Expected {expected_tools} tools, got {len(tools)}")
        return False

    all_have_descriptions = True
    for tool in tools:
        desc_len = len(tool.description) if tool.description else 0
        if desc_len == 0:
            stderr_print(f"✗ Tool {tool.name}: missing description!")
            all_have_descriptions = False
        else:
            stderr_print(f"✓ Tool {tool.name}: description length = {desc_len}")

    if all_have_descriptions:
        stderr_print("\n🎉 All tests passed! MCP tools are properly configured.")
        return True

    stderr_print("\n❌ Some tools are missing descriptions.")
    return False


def test_mcp_tools():
    """Pytest entry point that wraps the async logic."""
    assert asyncio.run(_run_mcp_tool_validation())


if __name__ == "__main__":
    try:
        success = asyncio.run(_run_mcp_tool_validation())
    except Exception as exc:  # pragma: no cover - CLI helper
        stderr_print(f"✗ Test failed with error: {exc}")
        import traceback

        traceback.print_exc()
        success = False
    sys.exit(0 if success else 1)