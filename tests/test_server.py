"""Server build + tool invocation through the MCP SDK layer."""

from __future__ import annotations

import httpx
import respx

from ga4gh_mcp.config import load_settings
from ga4gh_mcp.server import TOOL_NAMES, build_server
from ga4gh_mcp.context import ServerContext


async def test_all_tools_register_with_schemas():
    ctx = ServerContext.create(load_settings())
    mcp = build_server(load_settings(), ctx=ctx)
    tools = await mcp.list_tools()
    names = {t.name for t in tools}
    assert names == set(TOOL_NAMES)
    for t in tools:
        assert t.description and isinstance(t.inputSchema, dict)
    await ctx.aclose()


@respx.mock
async def test_call_tool_through_sdk(registry_data):
    respx.get("https://registry.test/api/services").mock(
        return_value=httpx.Response(200, json=registry_data["services"]))
    respx.get("https://registry.test/api/deployments").mock(
        return_value=httpx.Response(200, json=registry_data["deployments"]))
    respx.get("https://registry.test/api/standards").mock(
        return_value=httpx.Response(200, json=registry_data["standards"]))
    settings = load_settings(registry_base_url="https://registry.test/api")
    ctx = ServerContext.create(settings)
    mcp = build_server(settings, ctx=ctx)
    # FastMCP.call_tool returns (content, structured_result)
    result = await mcp.call_tool("list_service_types", {})
    structured = result[1] if isinstance(result, tuple) else result
    assert structured["ok"] is True
    assert structured["data"]["service_counts"]["DRS"] == 25
    await ctx.aclose()
