"""Liveness reporting across the real-world edge cases from docs/compatibility.md."""

from __future__ import annotations

import httpx
import respx

from ga4gh_mcp.errors import Liveness
from ga4gh_mcp.liveness import check_liveness

SI = "https://svc.test/ga4gh/drs/v1/service-info"


def _svc(**over):
    s = {
        "id": "s1", "implementationId": "org.test.drs", "name": "Test DRS",
        "url": "https://svc.test", "serviceInfoUrl": SI,
        "standardVersion": {"ga4ghProduct": "DRS", "version": "1.2.0"},
    }
    s.update(over)
    return s


@respx.mock
async def test_live_valid(ctx):
    respx.get(SI).mock(return_value=httpx.Response(200, json={
        "id": "x", "name": "DRS", "type": {"artifact": "drs", "version": "1.2.0"},
        "version": "1.2.0", "organization": {"name": "o", "url": "https://o"}}))
    rep = await check_liveness(ctx.http, _svc(), ctx.resolver)
    assert rep.liveness == Liveness.LIVE
    assert rep.service_info.compliant is True


@respx.mock
async def test_auth_required_extracts_hint(ctx):
    respx.get(SI).mock(return_value=httpx.Response(
        401, headers={"WWW-Authenticate": 'Bearer realm="ga4gh", scope="openid"'}))
    rep = await check_liveness(ctx.http, _svc(), ctx.resolver)
    assert rep.liveness == Liveness.AUTH_REQUIRED
    assert rep.auth and rep.auth.required and rep.auth.scheme == "Bearer"
    assert rep.auth.scope == "openid"


@respx.mock
async def test_gen3_version_mismatch_still_live_with_warning(ctx):
    respx.get(SI).mock(return_value=httpx.Response(200, json={
        "id": "indexd-xyz", "name": "DRS System",
        "type": {"artifact": "drs", "version": "1.0.3"}, "version": "1.0.3",
        "organization": {"name": "Gen3", "url": "https://gen3.org"}}))
    rep = await check_liveness(ctx.http, _svc(), ctx.resolver)
    assert rep.liveness == Liveness.LIVE
    assert rep.service_info.version.version_matches is False
    assert any("version discrepancy" in w for w in rep.warnings)


@respx.mock
async def test_nonstandard_service_info_marked_invalid(ctx):
    respx.get(SI).mock(return_value=httpx.Response(200, json={
        "version": "0.0.1", "title": "Terra Data Repository"}))
    rep = await check_liveness(ctx.http, _svc(standardVersion={"ga4ghProduct": "DRS", "version": "1.3.0"}), ctx.resolver)
    assert rep.liveness == Liveness.INVALID_RESPONSE
    assert rep.service_info.compliant is False


@respx.mock
async def test_404(ctx):
    respx.get(SI).mock(return_value=httpx.Response(404, text="nope"))
    rep = await check_liveness(ctx.http, _svc(), ctx.resolver)
    assert rep.liveness == Liveness.HTTP_ERROR and rep.http_status == 404


@respx.mock
async def test_dns_fail(ctx):
    respx.get(SI).mock(side_effect=httpx.ConnectError("nodename nor servname provided, or not known"))
    rep = await check_liveness(ctx.http, _svc(), ctx.resolver)
    assert rep.liveness == Liveness.UNREACHABLE_DNS


@respx.mock
async def test_timeout(ctx):
    respx.get(SI).mock(side_effect=httpx.ConnectTimeout("timed out"))
    rep = await check_liveness(ctx.http, _svc(), ctx.resolver)
    assert rep.liveness == Liveness.TIMEOUT


async def test_no_service_info_url(ctx):
    # DEPLOYMENT-style entry with no serviceInfoUrl and no inferable base for its product.
    rep = await check_liveness(ctx.http, _svc(serviceInfoUrl=None, url=None), ctx.resolver)
    assert rep.liveness == Liveness.NO_SERVICE_INFO_URL


@respx.mock
async def test_infers_service_info_url_from_base(ctx):
    # No serviceInfoUrl, but a DRS base url -> infer /ga4gh/drs/v1/service-info.
    inferred = "https://svc.test/ga4gh/drs/v1/service-info"
    respx.get(inferred).mock(return_value=httpx.Response(200, json={
        "id": "x", "name": "DRS", "type": {"artifact": "drs", "version": "1.2.0"},
        "version": "1.2.0", "organization": {"name": "o", "url": "https://o"}}))
    rep = await check_liveness(ctx.http, _svc(serviceInfoUrl=None), ctx.resolver)
    assert rep.liveness == Liveness.LIVE
    assert any("inferred" in w for w in rep.warnings)
