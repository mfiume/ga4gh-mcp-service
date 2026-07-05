"""Auth layer tests: token store, resolution order, discovery."""

from __future__ import annotations

import time

import httpx
import pytest
import respx

from ga4gh_mcp.auth.manager import AuthManager, host_env_slug
from ga4gh_mcp.auth.store import TokenStore
from ga4gh_mcp.config import Settings
from ga4gh_mcp.http import AsyncHttp

pytestmark = pytest.mark.asyncio


def _mgr(tmp_path):
    settings = Settings()
    http = AsyncHttp(timeout=5, max_retries=0)
    store = TokenStore(path=tmp_path / "tokens.json")
    return AuthManager(settings, http, store), http, store


async def test_host_env_slug():
    assert host_env_slug("data.terra.bio") == "DATA_TERRA_BIO"
    assert host_env_slug("host:8080") == "HOST_8080"


async def test_token_store_roundtrip_and_expiry(tmp_path):
    store = TokenStore(path=tmp_path / "t.json")
    store.set("h1", access_token="abc", expires_at=time.time() + 100)
    assert store.valid_access_token("h1") == "abc"
    store.set("h2", access_token="old", expires_at=time.time() - 10)
    assert store.valid_access_token("h2") is None  # expired
    # persisted mode is 0600
    assert (tmp_path / "t.json").exists()


async def test_resolution_order_session_over_env(tmp_path, monkeypatch):
    mgr, http, _ = _mgr(tmp_path)
    monkeypatch.setenv("GA4GH_MCP_TOKEN_DATA_TERRA_BIO", "env-token")
    # env token applies
    headers = await mgr.resolve_headers("https://data.terra.bio/ga4gh/drs/v1")
    assert headers["Authorization"] == "Bearer env-token"
    # session token overrides
    mgr.set_static_token("https://data.terra.bio", "session-token")
    headers = await mgr.resolve_headers("https://data.terra.bio/x")
    assert headers["Authorization"] == "Bearer session-token"
    await http.close()


async def test_oauth_token_preferred(tmp_path):
    mgr, http, store = _mgr(tmp_path)
    store.set("host.org", access_token="oauth-tok", expires_at=time.time() + 500, source="device_code")
    headers = await mgr.resolve_headers("https://host.org/api")
    assert headers["Authorization"] == "Bearer oauth-tok"
    await http.close()


async def test_no_auth_when_nothing_configured(tmp_path):
    mgr, http, _ = _mgr(tmp_path)
    headers = await mgr.resolve_headers("https://public.org/x")
    assert headers == {}
    await http.close()


@respx.mock
async def test_discover_bearer_challenge_and_oidc(tmp_path):
    mgr, http, _ = _mgr(tmp_path)
    # protected DRS probe returns 401 with a realm pointing at the issuer
    respx.get("https://svc.org/ga4gh/drs/v1/objects/_ga4gh_mcp_auth_probe").mock(
        return_value=httpx.Response(401, headers={"WWW-Authenticate": 'Bearer realm="https://issuer.org"'}))
    respx.get("https://issuer.org/.well-known/openid-configuration").mock(
        return_value=httpx.Response(200, json={
            "issuer": "https://issuer.org",
            "token_endpoint": "https://issuer.org/token",
            "device_authorization_endpoint": "https://issuer.org/device",
            "grant_types_supported": ["urn:ietf:params:oauth:grant-type:device_code"],
        }))
    result = await mgr.discover("https://svc.org", "drs")
    assert result["requires_auth"] is True
    assert result["challenge"]["scheme"] == "Bearer"
    assert "device_code" in result["available_flows"]
    assert result["recommended_flow"] == "device_code"
    await http.close()


async def test_revoke(tmp_path):
    mgr, http, store = _mgr(tmp_path)
    store.set("host.org", access_token="x")
    mgr.set_static_token("https://host.org", "y")
    revoked = mgr.revoke("https://host.org")
    assert "host.org" in revoked
    assert store.get("host.org") is None
    await http.close()
