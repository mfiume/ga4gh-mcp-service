"""Live integration tests against the real GA4GH Implementation Registry.

Skipped by default (they need network). Enable with:  GA4GH_MCP_LIVE=1 pytest
"""

from __future__ import annotations

import os

import pytest

from ga4gh_mcp.cache import TTLCache
from ga4gh_mcp.config import Settings
from ga4gh_mcp.http import AsyncHttp
from ga4gh_mcp.registry import RegistryClient
from ga4gh_mcp.serviceinfo import probe_liveness

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(os.environ.get("GA4GH_MCP_LIVE") != "1",
                       reason="live tests disabled (set GA4GH_MCP_LIVE=1 to enable)"),
]


def _client():
    http = AsyncHttp(timeout=15, max_retries=1)
    return RegistryClient(Settings().registry_url, http, TTLCache()), http


async def test_registry_reachable_and_has_services():
    client, http = _client()
    try:
        services = await client.services()
        assert len(services) >= 10
        artifacts = {s.artifact for s in services}
        assert "drs" in artifacts
    finally:
        await http.close()


async def test_registry_service_info():
    client, http = _client()
    try:
        si = await client.service_info()
        assert si.get("type", {}).get("artifact") == "service-registry"
    finally:
        await http.close()


async def test_a_live_drs_service_info():
    client, http = _client()
    try:
        # Dockstore's TRS is reliably public and compliant.
        probe = await probe_liveness(http, "https://dockstore.org/api/ga4gh/trs/v2/", "trs")
        assert probe["reachable"] is True
    finally:
        await http.close()
