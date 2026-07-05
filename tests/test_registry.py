"""Registry client tests: tolerant parsing, filtering helpers, caching."""

from __future__ import annotations

import httpx
import pytest
import respx

from ga4gh_mcp.cache import TTLCache
from ga4gh_mcp.http import AsyncHttp
from ga4gh_mcp.registry import RegistryClient

pytestmark = pytest.mark.asyncio

BASE = "https://registry.example/v1"

SERVICES = [
    {"id": "ai.viral", "name": "Viral AI", "type": {"artifact": "drs", "version": "1.3.0"},
     "organization": {"name": "DNAstack"}, "url": "https://viral.ai", "environment": "Production"},
    {"id": "org.dockstore", "name": "Dockstore", "type": {"artifact": "trs", "version": "2.0.1"},
     "organization": {"name": "Dockstore"}, "url": "https://dockstore.org/api/ga4gh/trs/v2/"},
    {"name": "MALFORMED — no id"},  # should be skipped, not crash
]
IMPLS = [{"id": "impl.indexd", "name": "Indexd", "type": {"artifact": "drs", "version": "1.1.0"}}]
TYPES = [{"group": "org.ga4gh", "artifact": "drs", "version": "1.3.0"}]


def _client():
    http = AsyncHttp(timeout=5, max_retries=0)
    return RegistryClient(BASE, http, TTLCache(ttl=300)), http


@respx.mock
async def test_services_skip_malformed():
    respx.get(f"{BASE}/services").mock(return_value=httpx.Response(200, json=SERVICES))
    client, http = _client()
    services = await client.services()
    ids = {s.id for s in services}
    assert ids == {"ai.viral", "org.dockstore"}  # malformed dropped
    await http.close()


@respx.mock
async def test_get_service_and_summary_normalization():
    respx.get(f"{BASE}/services").mock(return_value=httpx.Response(200, json=SERVICES))
    client, http = _client()
    svc = await client.get_service("org.dockstore")
    summ = svc.summary()
    assert summ["artifact"] == "trs"
    assert summ["base_url"] == "https://dockstore.org/api/ga4gh/trs/v2"  # /tools not present, unchanged
    await http.close()


@respx.mock
async def test_find_services_by_host():
    respx.get(f"{BASE}/services").mock(return_value=httpx.Response(200, json=SERVICES))
    client, http = _client()
    matches = await client.find_services(host="viral.ai")
    assert [m.id for m in matches] == ["ai.viral"]
    await http.close()


@respx.mock
async def test_cache_avoids_second_call():
    route = respx.get(f"{BASE}/services").mock(return_value=httpx.Response(200, json=SERVICES))
    client, http = _client()
    await client.services()
    await client.services()
    assert route.call_count == 1  # second call served from cache
    await http.close()


@respx.mock
async def test_implementations_and_types():
    respx.get(f"{BASE}/implementations").mock(return_value=httpx.Response(200, json=IMPLS))
    respx.get(f"{BASE}/services/types").mock(return_value=httpx.Response(200, json=TYPES))
    client, http = _client()
    impls = await client.implementations()
    types = await client.service_types()
    assert impls[0].id == "impl.indexd"
    assert types[0].artifact == "drs"
    await http.close()
