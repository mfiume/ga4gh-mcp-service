"""Concrete auth providers.

- ``NoAuth`` / ``StaticBearerAuth`` / ``ApiKeyAuth`` — synchronous, fully testable headless.
- ``OAuth2ClientCredentialsAuth`` — machine-to-machine; testable against a mock token endpoint.
- ``OAuth2DeviceCodeAuth`` — interactive device-code flow with a file token cache; the CLI-testable
  path for humans (see ``docs/auth.md`` and the ``auth_device_login`` tool).

Secrets come only from environment variables. Tokens are never logged or returned to the model.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from ..errors import ErrorType, ToolError
from ..http_client import Ga4ghHttpClient
from .base import AuthSpec

_FORM = {"Content-Type": "application/x-www-form-urlencoded"}


class NoAuth:
    kind = "none"

    async def headers(self) -> dict[str, str]:
        return {}

    def describe(self) -> dict[str, Any]:
        return {"kind": "none"}


class StaticBearerAuth:
    kind = "bearer"

    def __init__(self, token: str) -> None:
        self._token = token

    async def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"} if self._token else {}

    def describe(self) -> dict[str, Any]:
        return {"kind": "bearer", "token_present": bool(self._token)}


class ApiKeyAuth:
    kind = "api_key"

    def __init__(self, header: str, value: str, prefix: str = "") -> None:
        self._header = header or "Authorization"
        self._value = value
        self._prefix = prefix

    async def headers(self) -> dict[str, str]:
        return {self._header: f"{self._prefix}{self._value}"} if self._value else {}

    def describe(self) -> dict[str, Any]:
        return {"kind": "api_key", "header": self._header, "value_present": bool(self._value)}


class OAuth2ClientCredentialsAuth:
    kind = "oauth2_client_credentials"

    def __init__(
        self,
        http: Ga4ghHttpClient,
        *,
        token_url: str,
        client_id: str,
        client_secret: str,
        scope: str | None = None,
        audience: str | None = None,
    ) -> None:
        self._http = http
        self._token_url = token_url
        self._client_id = client_id
        self._client_secret = client_secret
        self._scope = scope
        self._audience = audience
        self._token: str | None = None
        self._expires_at: float = 0.0

    async def headers(self) -> dict[str, str]:
        if not self._token or time.time() >= self._expires_at:
            await self._fetch()
        return {"Authorization": f"Bearer {self._token}"} if self._token else {}

    async def _fetch(self) -> None:
        form: dict[str, Any] = {
            "grant_type": "client_credentials",
            "client_id": self._client_id,
            "client_secret": self._client_secret,
        }
        if self._scope:
            form["scope"] = self._scope
        if self._audience:
            form["audience"] = self._audience
        res = await self._http.request("POST", self._token_url, data=form, headers=_FORM)
        if res.liveness.value != "live" or not isinstance(res.json, dict):
            raise ToolError(
                ErrorType.AUTH,
                f"client-credentials token request failed ({res.status or res.liveness.value})",
                detail=res.error,
                hint=f"Check token_url and client credentials for {self._token_url}",
            )
        self._token = res.json.get("access_token")
        expires_in = float(res.json.get("expires_in", 3600))
        self._expires_at = time.time() + max(expires_in - 30, 30)

    def describe(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "token_url": self._token_url,
            "client_id_present": bool(self._client_id),
            "scope": self._scope,
            "token_cached": bool(self._token and time.time() < self._expires_at),
        }


class OAuth2DeviceCodeAuth:
    """RFC 8628 device authorization grant. Interactive but CLI/headless-friendly.

    ``start()`` returns a verification URI + user code the human enters in any browser;
    ``poll_until_authorized()`` blocks until the grant completes; the token is cached to
    ``token_store``. ``headers()`` returns the cached bearer if present/valid (refreshing
    when possible), else ``{}`` so the call proceeds and surfaces a 401 auth hint.
    """

    kind = "oauth2_device_code"

    def __init__(
        self,
        http: Ga4ghHttpClient,
        *,
        device_authorization_url: str,
        token_url: str,
        client_id: str,
        scope: str | None = None,
        token_store: str | None = None,
    ) -> None:
        self._http = http
        self._device_url = device_authorization_url
        self._token_url = token_url
        self._client_id = client_id
        self._scope = scope
        self._store = Path(token_store) if token_store else None
        self._pending: dict[str, Any] | None = None
        self._token, self._refresh, self._expires_at = self._load()

    # ---- persistence ----
    def _load(self) -> tuple[str | None, str | None, float]:
        if self._store and self._store.exists():
            try:
                d = json.loads(self._store.read_text())
                return d.get("access_token"), d.get("refresh_token"), float(d.get("expires_at", 0))
            except Exception:  # noqa: BLE001
                return None, None, 0.0
        return None, None, 0.0

    def _save(self) -> None:
        if not self._store:
            return
        self._store.parent.mkdir(parents=True, exist_ok=True)
        self._store.write_text(json.dumps(
            {"access_token": self._token, "refresh_token": self._refresh,
             "expires_at": self._expires_at}))
        try:
            self._store.chmod(0o600)
        except OSError:
            pass

    # ---- flow ----
    async def start(self) -> dict[str, Any]:
        form: dict[str, Any] = {"client_id": self._client_id}
        if self._scope:
            form["scope"] = self._scope
        res = await self._http.request("POST", self._device_url, data=form, headers=_FORM)
        if not isinstance(res.json, dict) or "device_code" not in res.json:
            raise ToolError(
                ErrorType.AUTH, "device authorization request failed",
                detail=res.error or res.json, hint=f"Check device_authorization_url {self._device_url}",
            )
        self._pending = res.json
        return {
            "verification_uri": res.json.get("verification_uri"),
            "verification_uri_complete": res.json.get("verification_uri_complete"),
            "user_code": res.json.get("user_code"),
            "expires_in": res.json.get("expires_in"),
            "interval": res.json.get("interval", 5),
        }

    async def poll_until_authorized(self, *, max_wait: float = 300.0) -> bool:
        import asyncio

        if not self._pending:
            raise ToolError(ErrorType.AUTH, "device flow not started; call start() first")
        device_code = self._pending["device_code"]
        interval = float(self._pending.get("interval", 5))
        deadline = time.time() + max_wait
        while time.time() < deadline:
            form = {
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device_code,
                "client_id": self._client_id,
            }
            res = await self._http.request("POST", self._token_url, data=form, headers=_FORM)
            body = res.json if isinstance(res.json, dict) else {}
            if body.get("access_token"):
                self._store_tokens(body)
                return True
            error = body.get("error")
            if error == "authorization_pending":
                await asyncio.sleep(interval)
            elif error == "slow_down":
                interval += 5
                await asyncio.sleep(interval)
            else:
                raise ToolError(ErrorType.AUTH, f"device flow failed: {error or res.status}",
                                detail=body)
        return False

    def _store_tokens(self, body: dict[str, Any]) -> None:
        self._token = body.get("access_token")
        self._refresh = body.get("refresh_token") or self._refresh
        self._expires_at = time.time() + max(float(body.get("expires_in", 3600)) - 30, 30)
        self._save()

    async def _refresh_token(self) -> bool:
        if not self._refresh:
            return False
        form = {"grant_type": "refresh_token", "refresh_token": self._refresh,
                "client_id": self._client_id}
        res = await self._http.request("POST", self._token_url, data=form, headers=_FORM)
        if isinstance(res.json, dict) and res.json.get("access_token"):
            self._store_tokens(res.json)
            return True
        return False

    async def headers(self) -> dict[str, str]:
        if self._token and time.time() >= self._expires_at:
            await self._refresh_token()
        return {"Authorization": f"Bearer {self._token}"} if self._token else {}

    def describe(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "token_url": self._token_url,
            "device_authorization_url": self._device_url,
            "client_id_present": bool(self._client_id),
            "scope": self._scope,
            "token_cached": bool(self._token and time.time() < self._expires_at),
            "token_store": str(self._store) if self._store else None,
        }


def build_provider(spec: AuthSpec, http: Ga4ghHttpClient, *, token_store_dir: str | None = None):
    """Instantiate a provider from an :class:`AuthSpec`, resolving env-var references."""
    kind = spec.kind
    if kind == "none":
        return NoAuth()
    if kind == "bearer":
        token = os.getenv(spec.token_env or "", "")
        return StaticBearerAuth(token)
    if kind == "api_key":
        return ApiKeyAuth(spec.header or "Authorization",
                          os.getenv(spec.value_env or "", ""), spec.value_prefix)
    if kind == "oauth2_client_credentials":
        return OAuth2ClientCredentialsAuth(
            http,
            token_url=spec.token_url or "",
            client_id=spec.client_id or os.getenv(spec.client_id_env or "", ""),
            client_secret=os.getenv(spec.client_secret_env or "", ""),
            scope=spec.scope,
            audience=spec.audience,
        )
    if kind == "oauth2_device_code":
        store = None
        if token_store_dir and spec.match:
            safe = "".join(c if c.isalnum() else "_" for c in spec.match)
            store = str(Path(token_store_dir) / f"{safe}.json")
        return OAuth2DeviceCodeAuth(
            http,
            device_authorization_url=spec.device_authorization_url or "",
            token_url=spec.token_url or "",
            client_id=spec.client_id or os.getenv(spec.client_id_env or "", ""),
            scope=spec.scope,
            token_store=store,
        )
    raise ToolError(ErrorType.VALIDATION, f"unknown auth kind: {kind}")
