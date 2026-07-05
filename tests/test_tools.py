"""Tool-level tests: invoke real MCP tools against a mocked registry/services."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from ga4gh_mcp.config import Settings
from ga4gh_mcp.server import build_server

pytestmark = pytest.mark.asyncio

BASE = "https://registry.example/v1"

SERVICES = [
    {"id": "ai.viral", "name": "Viral AI", "type": {"artifact": "drs", "version": "1.3.0"},
     "organization": {"name": "DNAstack"}, "url": "https://viral.ai", "environment": "Production"},
    {"id": "bdc.wes", "name": "BDC WES", "type": {"artifact": "wes", "version": "1.0.0"},
     "organization": {"name": "BioData Catalyst"},
     "url": "https://bdc.example/ga4gh/wes/v1/", "environment": "production"},
]
DRS_SI = {"id": "s", "name": "Viral DRS", "type": {"artifact": "drs", "version": "1.2.0"}, "version": "1.2.0"}


async def _call(mcp, name, args):
    r = await mcp.call_tool(name, args)
    if isinstance(r, tuple):
        content, raw = r
        if raw is not None:
            return raw
        r = content
    return json.loads(r[0].text)


@respx.mock
async def test_registry_list_services_filter():
    respx.get(f"{BASE}/services").mock(return_value=httpx.Response(200, json=SERVICES))
    mcp, ctx = build_server(Settings(registry_url=BASE))
    try:
        res = await _call(mcp, "registry_list_services", {"artifact": "wes"})
        assert res["ok"] is True
        assert res["total_matched"] == 1
        assert res["data"][0]["id"] == "bdc.wes"
    finally:
        await ctx.aclose()


@respx.mock
async def test_registry_search():
    respx.get(f"{BASE}/services").mock(return_value=httpx.Response(200, json=SERVICES))
    respx.get(f"{BASE}/implementations").mock(return_value=httpx.Response(200, json=[]))
    mcp, ctx = build_server(Settings(registry_url=BASE))
    try:
        res = await _call(mcp, "registry_search", {"query": "viral"})
        assert res["ok"] is True
        assert any(s["id"] == "ai.viral" for s in res["data"]["services"])
    finally:
        await ctx.aclose()


@respx.mock
async def test_service_get_info_version_reconcile_warning():
    respx.get(f"{BASE}/services").mock(return_value=httpx.Response(200, json=SERVICES))
    # Registry declares 1.3.0 but the service reports 1.2.0 -> expect a warning.
    respx.get("https://viral.ai/service-info").mock(return_value=httpx.Response(200, json=DRS_SI))
    mcp, ctx = build_server(Settings(registry_url=BASE))
    try:
        res = await _call(mcp, "service_get_info", {"service_id_or_url": "ai.viral"})
        assert res["ok"] is True
        assert res["data"]["reported_version"] == "1.2.0"
        assert res["data"]["declared_version"] == "1.3.0"
        assert any("declares version" in w for w in res.get("warnings", []))
    finally:
        await ctx.aclose()


@respx.mock
async def test_drs_get_object_auth_required_structured_error():
    respx.get(f"{BASE}/services").mock(return_value=httpx.Response(200, json=SERVICES))
    respx.get("https://viral.ai/ga4gh/drs/v1/objects/obj1").mock(
        return_value=httpx.Response(401, headers={"WWW-Authenticate": 'Bearer realm="x"'}))
    mcp, ctx = build_server(Settings(registry_url=BASE))
    try:
        res = await _call(mcp, "drs_get_object", {"service_id_or_url": "ai.viral", "object_id": "obj1"})
        assert res["ok"] is False
        assert res["error"]["kind"] == "auth_required"
        assert res["auth_challenge"]["scheme"] == "Bearer"
    finally:
        await ctx.aclose()


@respx.mock
async def test_unknown_service_id_error():
    respx.get(f"{BASE}/services").mock(return_value=httpx.Response(200, json=SERVICES))
    mcp, ctx = build_server(Settings(registry_url=BASE))
    try:
        res = await _call(mcp, "registry_get_service", {"service_id": "does.not.exist"})
        assert res["ok"] is False
        assert res["error"]["kind"] == "not_found"
    finally:
        await ctx.aclose()
