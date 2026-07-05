"""Auth providers, resolver selection, and WWW-Authenticate parsing."""

from __future__ import annotations

import json

import httpx
import respx

from ga4gh_mcp.auth.providers import (
    ApiKeyAuth,
    NoAuth,
    OAuth2ClientCredentialsAuth,
    OAuth2DeviceCodeAuth,
    StaticBearerAuth,
)
from ga4gh_mcp.auth.resolver import AuthResolver, parse_www_authenticate
from ga4gh_mcp.config import load_settings
from ga4gh_mcp.http_client import Ga4ghHttpClient


async def test_no_auth_and_static_bearer():
    assert await NoAuth().headers() == {}
    assert await StaticBearerAuth("tok").headers() == {"Authorization": "Bearer tok"}
    assert await StaticBearerAuth("").headers() == {}


async def test_api_key():
    p = ApiKeyAuth("X-API-Key", "secret")
    assert await p.headers() == {"X-API-Key": "secret"}


@respx.mock
async def test_client_credentials_fetches_and_caches_token():
    respx.post("https://idp.test/token").mock(return_value=httpx.Response(
        200, json={"access_token": "abc", "expires_in": 3600, "token_type": "Bearer"}))
    http = Ga4ghHttpClient(load_settings(max_retries=0, retry_backoff=0.0))
    p = OAuth2ClientCredentialsAuth(http, token_url="https://idp.test/token",
                                    client_id="cid", client_secret="csecret", scope="openid")
    h1 = await p.headers()
    h2 = await p.headers()  # cached; no second token call
    assert h1 == {"Authorization": "Bearer abc"} == h2
    assert respx.routes[0].call_count == 1
    await http.aclose()


@respx.mock
async def test_device_code_flow_start_and_poll():
    respx.post("https://idp.test/device").mock(return_value=httpx.Response(200, json={
        "device_code": "DC", "user_code": "WXYZ-1234",
        "verification_uri": "https://idp.test/activate",
        "verification_uri_complete": "https://idp.test/activate?user_code=WXYZ-1234",
        "expires_in": 600, "interval": 0}))
    # first poll: pending, second: success
    respx.post("https://idp.test/token").mock(side_effect=[
        httpx.Response(400, json={"error": "authorization_pending"}),
        httpx.Response(200, json={"access_token": "TOK", "expires_in": 3600}),
    ])
    http = Ga4ghHttpClient(load_settings(max_retries=0, retry_backoff=0.0))
    p = OAuth2DeviceCodeAuth(http, device_authorization_url="https://idp.test/device",
                             token_url="https://idp.test/token", client_id="cid")
    start = await p.start()
    assert start["user_code"] == "WXYZ-1234"
    ok = await p.poll_until_authorized(max_wait=5)
    assert ok is True
    assert await p.headers() == {"Authorization": "Bearer TOK"}
    await http.aclose()


def test_parse_www_authenticate_bearer():
    h = parse_www_authenticate('Bearer realm="ga4gh", scope="openid profile", '
                               'authorization_uri="https://idp/authorize"')
    assert h.required and h.scheme == "Bearer"
    assert h.realm == "ga4gh" and h.scope == "openid profile"
    assert h.authorization_uri == "https://idp/authorize"
    assert "bearer token" in (h.guidance or "").lower()


def test_parse_www_authenticate_none():
    assert parse_www_authenticate(None).required is False


async def test_resolver_picks_config_spec(tmp_path, monkeypatch):
    monkeypatch.setenv("MY_TERRA_TOKEN", "terra-secret")
    cfg = tmp_path / "auth.json"
    cfg.write_text(json.dumps({"services": {
        "org.test.drs": {"kind": "bearer", "token_env": "MY_TERRA_TOKEN"}}}))
    settings = load_settings(auth_config=str(cfg))
    http = Ga4ghHttpClient(settings)
    resolver = AuthResolver(settings, http)
    provider = resolver.resolve({"implementationId": "org.test.drs",
                                 "serviceInfoUrl": "https://x/service-info"})
    assert provider.kind == "bearer"
    assert await provider.headers() == {"Authorization": "Bearer terra-secret"}
    await http.aclose()


async def test_resolver_global_bearer_host_allowlist():
    settings = load_settings(bearer_token="glob", bearer_hosts="allowed.test")
    http = Ga4ghHttpClient(settings)
    resolver = AuthResolver(settings, http)
    on = resolver.resolve({"implementationId": "a", "serviceInfoUrl": "https://allowed.test/x"})
    off = resolver.resolve({"implementationId": "b", "serviceInfoUrl": "https://other.test/x"})
    assert on.kind == "bearer" and await on.headers() == {"Authorization": "Bearer glob"}
    assert off.kind == "none"  # not on the allow-list -> no token leaked
    await http.aclose()


async def test_resolver_default_no_auth():
    settings = load_settings()
    http = Ga4ghHttpClient(settings)
    resolver = AuthResolver(settings, http)
    p = resolver.resolve({"implementationId": "x", "serviceInfoUrl": "https://y/z"})
    assert p.kind == "none"
    await http.aclose()
