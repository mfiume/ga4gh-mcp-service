"""Liveness / version / compliance edge cases, mocked with respx.

These prove the server degrades gracefully against the messy reality of
registered services (down, non-compliant, SPA false-positives, auth-gated,
inconsistent URLs)."""

from __future__ import annotations

import httpx
import pytest
import respx

from ga4gh_mcp.http import AsyncHttp
from ga4gh_mcp.serviceinfo import fetch_service_info, probe_liveness

pytestmark = pytest.mark.asyncio

SI = {"id": "x", "name": "Test DRS", "type": {"group": "org.ga4gh", "artifact": "drs",
                                              "version": "1.2.0"}, "version": "1.2.0"}


async def _http():
    return AsyncHttp(timeout=5, max_retries=0)


@respx.mock
async def test_live_valid_service_info():
    respx.get("https://x.org/service-info").mock(return_value=httpx.Response(200, json=SI))
    http = await _http()
    info = await fetch_service_info(http, "https://x.org")
    assert info["found"] is True
    assert info["reported_version"] == "1.2.0"
    await http.close()


@respx.mock
async def test_spa_false_positive_rejected():
    # 200 but HTML body — must NOT be treated as a live service-info.
    respx.get("https://x.org/service-info").mock(
        return_value=httpx.Response(200, text="<!doctype html><html></html>",
                                    headers={"content-type": "text/html"}))
    http = await _http()
    info = await fetch_service_info(http, "https://x.org")
    assert info["found"] is False
    assert info["liveness"] == "live_no_serviceinfo"
    assert any("not a valid" in w for w in info["warnings"])
    await http.close()


@respx.mock
async def test_404_no_service_info():
    respx.get("https://x.org/service-info").mock(return_value=httpx.Response(404, text="not found"))
    http = await _http()
    info = await fetch_service_info(http, "https://x.org")
    assert info["found"] is False
    assert info["liveness"] == "live_no_serviceinfo"
    await http.close()


@respx.mock
async def test_auth_required_challenge():
    respx.get("https://x.org/service-info").mock(
        return_value=httpx.Response(401, headers={"WWW-Authenticate": 'Bearer realm="https://issuer"'}))
    http = await _http()
    probe = await probe_liveness(http, "https://x.org")
    assert probe["liveness"] == "auth_required"
    assert probe["auth_required"] is True
    assert probe["auth_challenge"]["scheme"] == "Bearer"
    await http.close()


@respx.mock
async def test_unreachable_connection_error():
    respx.get("https://dead.example/service-info").mock(side_effect=httpx.ConnectError("boom"))
    http = await _http()
    probe = await probe_liveness(http, "https://dead.example")
    assert probe["liveness"] == "unreachable"
    assert probe["reachable"] is False
    await http.close()


@respx.mock
async def test_drs_url_normalization_recovers_service_info():
    # Registered URL points at the object collection; service-info lives at the base.
    respx.get("https://data.bloodpac.org/ga4gh/drs/v1/service-info").mock(
        return_value=httpx.Response(200, json=SI))
    http = await _http()
    info = await fetch_service_info(http, "https://data.bloodpac.org/ga4gh/drs/v1/objects/", "drs")
    assert info["found"] is True
    assert info["endpoint"].endswith("/ga4gh/drs/v1/service-info")
    await http.close()


@respx.mock
async def test_server_error_is_not_live():
    respx.get("https://x.org/service-info").mock(return_value=httpx.Response(503, text="down"))
    http = await _http()
    probe = await probe_liveness(http, "https://x.org")
    assert probe["liveness"] == "server_error"
    await http.close()
