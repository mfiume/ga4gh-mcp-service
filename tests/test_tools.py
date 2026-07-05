"""Tool envelopes end-to-end (registry preloaded; upstream services mocked)."""

from __future__ import annotations

import httpx
import respx

from ga4gh_mcp import tools

DRS_SI = "https://drs.test/ga4gh/drs/v1/service-info"
DRS_BASE = "https://drs.test/ga4gh/drs/v1"
TRS_SI = "https://trs.test/ga4gh/trs/v2/service-info"

DRS_SVC = {
    "id": "uuid-drs", "implementationId": "org.test.drs", "name": "Test DRS",
    "url": "https://drs.test", "serviceInfoUrl": DRS_SI, "implementationType": "SERVICE",
    "environment": "PRODUCTION", "organisation": {"name": "Test Org", "orgId": "org.test"},
    "standardVersion": {"ga4ghProduct": "DRS", "version": "1.2.0"},
}
TRS_SVC = {
    "id": "uuid-trs", "implementationId": "org.test.trs", "name": "Test TRS",
    "url": "https://trs.test", "serviceInfoUrl": TRS_SI, "implementationType": "SERVICE",
    "standardVersion": {"ga4ghProduct": "TRS", "version": "2.0.1"},
}


def _preload(ctx):
    ctx.registry._cache.set("services", [DRS_SVC, TRS_SVC])
    ctx.registry._cache.set("deployments", [])


async def test_list_services_envelope(ctx):
    _preload(ctx)
    r = await tools.list_services(ctx, product="DRS")
    assert r["ok"] is True and r["count"] == 1
    assert r["data"][0]["implementationId"] == "org.test.drs"


async def test_get_service_ok_and_not_found(ctx):
    _preload(ctx)
    ok = await tools.get_service(ctx, service_id="org.test.drs")
    assert ok["ok"] and ok["data"]["id"] == "uuid-drs"
    missing = await tools.get_service(ctx, service_id="nope")
    assert missing["ok"] is False and missing["error"]["type"] == "not_found"


async def test_list_service_types_includes_plugins(ctx):
    r = await tools.list_service_types(ctx)
    assert r["ok"]
    assert "DRS" in r["data"]["type_aware_plugins"]
    assert "drs_get_object" in r["data"]["type_aware_plugins"]["DRS"]["capabilities"]


async def test_list_organisations_filter(ctx):
    r = await tools.list_organisations(ctx, query="translational")
    assert r["ok"] and r["count"] >= 1


@respx.mock
async def test_check_service_health_live(ctx):
    _preload(ctx)
    respx.get(DRS_SI).mock(return_value=httpx.Response(200, json={
        "id": "x", "name": "DRS", "type": {"artifact": "drs", "version": "1.2.0"},
        "version": "1.2.0", "organization": {"name": "o", "url": "https://o"}}))
    r = await tools.check_service_health(ctx, service_id="org.test.drs")
    assert r["ok"] and r["data"]["liveness"] == "live"


@respx.mock
async def test_get_service_info_by_url(ctx):
    respx.get("https://raw.test/service-info").mock(return_value=httpx.Response(200, json={
        "id": "x", "name": "S", "type": {"artifact": "drs", "version": "1.5.0"},
        "version": "1.5.0", "organization": {"name": "o", "url": "https://o"}}))
    r = await tools.get_service_info(ctx, url="https://raw.test/service-info")
    assert r["ok"] and r["data"]["shape"] == "ga4gh"


@respx.mock
async def test_call_service_endpoint_generic(ctx):
    _preload(ctx)
    respx.get(f"{DRS_BASE}/objects/abc").mock(return_value=httpx.Response(200, json={"id": "abc"}))
    r = await tools.call_service_endpoint(ctx, service_id="org.test.drs", path="/objects/abc")
    assert r["ok"] and r["data"]["id"] == "abc"
    assert r["upstream"]["http_status"] == 200


@respx.mock
async def test_call_service_endpoint_auth_hint(ctx):
    _preload(ctx)
    respx.get(f"{DRS_BASE}/objects/x").mock(return_value=httpx.Response(
        401, headers={"WWW-Authenticate": 'Bearer realm="r"'}))
    r = await tools.call_service_endpoint(ctx, service_id="org.test.drs", path="/objects/x")
    assert r["ok"] is False and r["error"]["type"] == "auth"
    assert r["error"]["detail"]["auth"]["scheme"] == "Bearer"


@respx.mock
async def test_drs_get_object(ctx):
    _preload(ctx)
    respx.get(f"{DRS_BASE}/objects/obj1").mock(return_value=httpx.Response(200, json={
        "id": "obj1", "size": 123, "checksums": [{"type": "md5", "checksum": "abc"}]}))
    r = await tools.drs_get_object(ctx, service_id="org.test.drs", object_id="obj1")
    assert r["ok"] and r["data"]["size"] == 123


@respx.mock
async def test_drs_get_access_url_inline(ctx):
    _preload(ctx)
    respx.get(f"{DRS_BASE}/objects/obj1").mock(return_value=httpx.Response(200, json={
        "id": "obj1", "access_methods": [
            {"type": "https", "access_url": {"url": "https://data.test/file"}}]}))
    r = await tools.drs_get_access_url(ctx, service_id="org.test.drs", object_id="obj1")
    assert r["ok"] and r["data"]["access_url"]["url"] == "https://data.test/file"


@respx.mock
async def test_drs_get_access_url_dereference(ctx):
    _preload(ctx)
    respx.get(f"{DRS_BASE}/objects/obj2").mock(return_value=httpx.Response(200, json={
        "id": "obj2", "access_methods": [{"type": "s3", "access_id": "aid1"}]}))
    respx.get(f"{DRS_BASE}/objects/obj2/access/aid1").mock(return_value=httpx.Response(
        200, json={"url": "https://s3.test/obj2"}))
    r = await tools.drs_get_access_url(ctx, service_id="org.test.drs", object_id="obj2")
    assert r["ok"] and r["data"]["access_url"]["url"] == "https://s3.test/obj2"


async def test_type_mismatch_is_unsupported(ctx):
    _preload(ctx)
    r = await tools.drs_get_object(ctx, service_id="org.test.trs", object_id="x")
    assert r["ok"] is False and r["error"]["type"] == "unsupported"


async def test_auth_status(ctx):
    r = await tools.auth_status(ctx)
    assert r["ok"] and "token_store_dir" in r["data"]


async def test_auth_device_login_requires_config(ctx):
    _preload(ctx)
    r = await tools.auth_device_login(ctx, service_id="org.test.drs")
    assert r["ok"] is False and r["error"]["type"] == "validation"
