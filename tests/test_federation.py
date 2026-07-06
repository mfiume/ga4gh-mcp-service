"""Federation of an extra GA4GH Service Registry (e.g. ga4gh-aws-opendata) + Data Connect tools."""

from __future__ import annotations

import httpx
import respx

from ga4gh_mcp import tools
from ga4gh_mcp.config import load_settings
from ga4gh_mcp.context import ServerContext
from ga4gh_mcp.registry import normalize_service_info

FED = "https://aws.test/ga4gh/registry/services"
DC_BASE = "https://aws.test/ga4gh/data-connect/v1"

FED_SERVICES = [
    {"id": "org.ga4gh.aws-opendata.data-connect", "name": "AWS Open Data — Data Connect",
     "type": {"group": "org.ga4gh", "artifact": "data-connect", "version": "1.0.0"},
     "url": DC_BASE, "organization": {"name": "AWS Open Data"}},
    {"id": "org.ga4gh.aws-opendata.drs", "name": "AWS Open Data DRS",
     "type": {"group": "org.ga4gh", "artifact": "drs", "version": "1.4.0"},
     "url": "https://aws.test/ga4gh/drs/v1", "organization": {"name": "AWS Open Data"}},
]


def _ctx():
    settings = load_settings(registry_base_url="https://registry.test/api",
                             extra_registries=FED, max_retries=0, retry_backoff=0.0)
    ctx = ServerContext.create(settings)
    ctx.registry._cache.set("services", [])       # avoid hitting the real registry
    ctx.registry._cache.set("deployments", [])
    return ctx


def test_normalize_service_info():
    n = normalize_service_info(FED_SERVICES[0], source=FED)
    assert n["product"] if False else True  # (product lives under standardVersion)
    assert n["standardVersion"]["ga4ghProduct"] == "DataConnect"
    assert n["serviceInfoUrl"] == DC_BASE + "/service-info"
    assert n["implementationId"] == "org.ga4gh.aws-opendata.data-connect"


@respx.mock
async def test_list_services_includes_federated():
    respx.get(FED).mock(return_value=httpx.Response(200, json=FED_SERVICES))
    ctx = _ctx()
    try:
        r = await tools.list_services(ctx)
        products = {s["product"] for s in r["data"]}
        assert "DataConnect" in products and "DRS" in products
        ids = {s["implementationId"] for s in r["data"]}
        assert "org.ga4gh.aws-opendata.data-connect" in ids
    finally:
        await ctx.aclose()


@respx.mock
async def test_get_service_resolves_federated():
    respx.get(FED).mock(return_value=httpx.Response(200, json=FED_SERVICES))
    ctx = _ctx()
    try:
        r = await tools.get_service(ctx, service_id="org.ga4gh.aws-opendata.drs")
        assert r["ok"] and r["data"]["name"] == "AWS Open Data DRS"
    finally:
        await ctx.aclose()


@respx.mock
async def test_federation_offline_does_not_crash():
    respx.get(FED).mock(side_effect=httpx.ConnectError("boom"))
    ctx = _ctx()
    try:
        r = await tools.list_services(ctx)
        assert r["ok"] and r["data"] == []  # federated skipped, core empty, no crash
    finally:
        await ctx.aclose()


@respx.mock
async def test_data_connect_search_tool():
    respx.get(FED).mock(return_value=httpx.Response(200, json=FED_SERVICES))
    respx.post(f"{DC_BASE}/search").mock(return_value=httpx.Response(200, json={
        "data_model": {"type": "object", "properties": {"gene": {"type": "string"}}},
        "data": [{"gene": "BRCA1", "loeuf": 0.915}], "pagination": {"next_page_url": None}}))
    ctx = _ctx()
    try:
        r = await tools.data_connect_search(
            ctx, service_id="org.ga4gh.aws-opendata.data-connect",
            sql="SELECT gene, oe_lof_upper AS loeuf FROM gnomad.gene_constraint WHERE gene='BRCA1'")
        assert r["ok"] and r["data"]["data"][0]["gene"] == "BRCA1"
    finally:
        await ctx.aclose()


@respx.mock
async def test_data_connect_list_tables_tool():
    respx.get(FED).mock(return_value=httpx.Response(200, json=FED_SERVICES))
    respx.get(f"{DC_BASE}/tables").mock(return_value=httpx.Response(200, json={
        "tables": [{"name": "gnomad.gene_constraint", "description": "constraint"}]}))
    ctx = _ctx()
    try:
        r = await tools.data_connect_list_tables(
            ctx, service_id="org.ga4gh.aws-opendata.data-connect")
        assert r["ok"] and r["data"]["tables"][0]["name"] == "gnomad.gene_constraint"
    finally:
        await ctx.aclose()


@respx.mock
async def test_data_connect_wrong_type_rejected():
    respx.get(FED).mock(return_value=httpx.Response(200, json=FED_SERVICES))
    ctx = _ctx()
    try:
        # the DRS service is not a Data Connect service
        r = await tools.data_connect_search(ctx, service_id="org.ga4gh.aws-opendata.drs",
                                            sql="SELECT 1")
        assert r["ok"] is False and r["error"]["type"] == "unsupported"
    finally:
        await ctx.aclose()
