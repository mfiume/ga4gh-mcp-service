"""HTTP client: failure classification + retry behaviour."""

from __future__ import annotations

import httpx
import pytest
import respx

from ga4gh_mcp.config import load_settings
from ga4gh_mcp.errors import Liveness
from ga4gh_mcp.http_client import Ga4ghHttpClient

URL = "https://svc.test/service-info"


def _client():
    return Ga4ghHttpClient(load_settings(max_retries=1, retry_backoff=0.0,
                                         connect_timeout=1.0, read_timeout=1.0))


@respx.mock
async def test_live_json():
    respx.get(URL).mock(return_value=httpx.Response(200, json={"id": "x", "name": "y"}))
    c = _client()
    r = await c.get_json(URL)
    assert r.liveness == Liveness.LIVE and r.status == 200 and r.json["id"] == "x"
    await c.aclose()


@respx.mock
async def test_auth_required_carries_www_authenticate():
    respx.get(URL).mock(return_value=httpx.Response(
        401, headers={"WWW-Authenticate": 'Bearer realm="ga4gh", scope="drs"'}))
    c = _client()
    r = await c.get_json(URL)
    assert r.liveness == Liveness.AUTH_REQUIRED
    assert "bearer" in r.headers["www-authenticate"].lower()
    await c.aclose()


@respx.mock
async def test_http_error_404():
    respx.get(URL).mock(return_value=httpx.Response(404, text="not found"))
    c = _client()
    r = await c.get_json(URL)
    assert r.liveness == Liveness.HTTP_ERROR and r.status == 404
    await c.aclose()


@respx.mock
async def test_non_json_is_invalid_response():
    respx.get(URL).mock(return_value=httpx.Response(200, text="<html>hi</html>"))
    c = _client()
    r = await c.get_json(URL)
    assert r.liveness == Liveness.INVALID_RESPONSE and r.json is None
    await c.aclose()


@respx.mock
async def test_dns_failure():
    respx.get(URL).mock(side_effect=httpx.ConnectError(
        "[Errno 8] nodename nor servname provided, or not known"))
    c = _client()
    r = await c.get_json(URL)
    assert r.liveness == Liveness.UNREACHABLE_DNS
    await c.aclose()


@respx.mock
async def test_tls_error():
    respx.get(URL).mock(side_effect=httpx.ConnectError("[SSL: WRONG_VERSION_NUMBER] wrong version number"))
    c = _client()
    r = await c.get_json(URL)
    assert r.liveness == Liveness.TLS_ERROR
    await c.aclose()


@respx.mock
async def test_timeout():
    respx.get(URL).mock(side_effect=httpx.ConnectTimeout("timed out"))
    c = _client()
    r = await c.get_json(URL)
    assert r.liveness == Liveness.TIMEOUT
    await c.aclose()


@respx.mock
async def test_connection_refused():
    respx.get(URL).mock(side_effect=httpx.ConnectError("Connection refused"))
    c = _client()
    r = await c.get_json(URL)
    assert r.liveness == Liveness.CONNECTION_ERROR
    await c.aclose()


@respx.mock
async def test_retry_on_503_then_success():
    route = respx.get(URL).mock(side_effect=[
        httpx.Response(503), httpx.Response(200, json={"ok": True})])
    c = _client()
    r = await c.get_json(URL)
    assert r.status == 200 and r.json["ok"] is True
    assert route.call_count == 2  # retried once
    await c.aclose()


@respx.mock
async def test_dns_not_retried():
    route = respx.get(URL).mock(side_effect=httpx.ConnectError("getaddrinfo failed"))
    c = _client()
    r = await c.get_json(URL)
    assert r.liveness == Liveness.UNREACHABLE_DNS
    assert route.call_count == 1  # deterministic failure, not retried
    await c.aclose()
