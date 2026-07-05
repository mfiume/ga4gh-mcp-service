"""Registry client: fetch/cache, client-side filtering, search, id resolution."""

from __future__ import annotations

import httpx
import pytest
import respx

from ga4gh_mcp.errors import ErrorType, ToolError
from ga4gh_mcp.registry import RegistryClient, summarize

REGISTRY_BASE = "https://registry.test/api"  # matches conftest.settings fixture


async def test_filter_by_product(ctx):
    drs = await ctx.registry.list_services(product="DRS")
    assert len(drs) == 25  # from empirical fixture
    assert all((s.get("standardVersion") or {}).get("ga4ghProduct") == "DRS" for s in drs)


async def test_filter_by_product_case_insensitive(ctx):
    assert len(await ctx.registry.list_services(product="drs")) == 25


async def test_filter_by_version_prefix(ctx):
    v12 = await ctx.registry.list_services(product="DRS", version="1.2")
    assert v12 and all(
        (s["standardVersion"]["version"]).startswith("1.2") for s in v12)


async def test_include_deployments(ctx):
    only_services = await ctx.registry.list_services()
    with_deployments = await ctx.registry.list_services(include_deployments=True)
    assert len(with_deployments) > len(only_services)


async def test_search_freetext(ctx):
    hits = await ctx.registry.search("dockstore")
    assert any("dockstore" in (s.get("name") or "").lower()
               or "dockstore" in (s.get("implementationId") or "").lower() for s in hits)


async def test_get_service_by_uuid_and_impl_id(ctx, registry_data):
    sample = registry_data["services"][0]
    by_uuid = await ctx.registry.get_service(sample["id"])
    by_impl = await ctx.registry.get_service(sample["implementationId"])
    assert by_uuid["id"] == by_impl["id"] == sample["id"]


async def test_get_service_not_found(ctx):
    with pytest.raises(ToolError) as e:
        await ctx.registry.get_service("does.not.exist")
    assert e.value.error_type == ErrorType.NOT_FOUND


async def test_service_types_counts(ctx):
    types = await ctx.registry.service_types()
    assert types["service_counts"]["DRS"] == 25
    assert types["service_counts"]["TES"] == 8
    assert any(s["abbreviation"] == "DRS" for s in types["known_standards"])


async def test_summarize_shape(registry_data):
    s = summarize(registry_data["services"][0])
    assert set(s) >= {"id", "implementationId", "name", "product", "version",
                      "has_service_info_url"}


@respx.mock
async def test_fetch_and_cache(settings, registry_data):
    # Fresh client (not the preloaded ctx) to exercise the HTTP fetch + cache path.
    from ga4gh_mcp.context import ServerContext
    route = respx.get(f"{REGISTRY_BASE}/services").mock(
        return_value=httpx.Response(200, json=registry_data["services"]))
    c = ServerContext.create(settings)
    try:
        a = await c.registry.services()
        b = await c.registry.services()  # served from cache
        assert len(a) == len(b) == len(registry_data["services"])
        assert route.call_count == 1  # second call cached
    finally:
        await c.aclose()


@respx.mock
async def test_registry_down_raises_upstream(settings):
    from ga4gh_mcp.context import ServerContext
    respx.get(f"{REGISTRY_BASE}/services").mock(return_value=httpx.Response(503))
    c = ServerContext.create(settings)
    try:
        with pytest.raises(ToolError) as e:
            await c.registry.services()
        assert e.value.error_type == ErrorType.UPSTREAM
    finally:
        await c.aclose()
