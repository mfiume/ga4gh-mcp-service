"""Selects the right auth provider per service and interprets 401 challenges."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from ..config import Settings
from ..http_client import Ga4ghHttpClient
from ..models import AuthHint
from .base import AuthProvider, AuthSpec
from .providers import NoAuth, StaticBearerAuth, build_provider

_TOKEN_STORE_DIR = os.path.expanduser("~/.ga4gh-mcp/tokens")


def _host(url: str | None) -> str | None:
    if not url:
        return None
    try:
        return (urlparse(url).hostname or "").lower() or None
    except Exception:  # noqa: BLE001
        return None


# WWW-Authenticate token = token68 or key="quoted" / key=token pairs.
_PARAM_RE = re.compile(r'(\w+)\s*=\s*(?:"([^"]*)"|([^\s,]+))')


def parse_www_authenticate(header: str | None) -> AuthHint:
    """Parse a ``WWW-Authenticate`` header into an actionable :class:`AuthHint`."""
    if not header:
        return AuthHint(required=False)
    scheme = header.split(" ", 1)[0].strip() or None
    params: dict[str, str] = {}
    for m in _PARAM_RE.finditer(header):
        params[m.group(1).lower()] = m.group(2) if m.group(2) is not None else m.group(3)
    hint = AuthHint(
        required=True,
        scheme=scheme,
        realm=params.get("realm"),
        scope=params.get("scope"),
        authorization_uri=params.get("authorization_uri")
        or params.get("as_uri")
        or params.get("authorization_endpoint"),
        www_authenticate=header,
    )
    if scheme and scheme.lower() == "bearer":
        hint.guidance = (
            "Service requires an OAuth2/OIDC bearer token. Configure a provider in the auth "
            "config (kind=bearer with token_env, or kind=oauth2_client_credentials / "
            "oauth2_device_code). See docs/auth.md."
        )
    elif scheme:
        hint.guidance = f"Service requires '{scheme}' authentication. See docs/auth.md."
    return hint


class AuthResolver:
    """Maps a registry service entry to an :class:`AuthProvider`.

    Resolution order: explicit config match (by implementationId, then host) → global
    static bearer (only for allow-listed hosts) → NoAuth. Providers are cached so OAuth
    token caches survive across calls.
    """

    def __init__(self, settings: Settings, http: Ga4ghHttpClient) -> None:
        self._settings = settings
        self._http = http
        self._specs: list[AuthSpec] = self._load_specs(settings.auth_config)
        self._cache: dict[str, AuthProvider] = {}

    @staticmethod
    def _load_specs(path: str | None) -> list[AuthSpec]:
        if not path:
            return []
        p = Path(path)
        if not p.exists():
            return []
        data = json.loads(p.read_text())
        raw = data.get("services", data) if isinstance(data, dict) else data
        specs: list[AuthSpec] = []
        if isinstance(raw, dict):  # {match: spec}
            for match, spec in raw.items():
                s = AuthSpec.from_dict(spec)
                s.match = s.match or match
                specs.append(s)
        elif isinstance(raw, list):
            specs = [AuthSpec.from_dict(s) for s in raw]
        return specs

    def _find_spec(self, impl_id: str | None, host: str | None) -> AuthSpec | None:
        for s in self._specs:
            if s.match and impl_id and s.match == impl_id:
                return s
        for s in self._specs:
            if s.match and host and s.match.lower() == host:
                return s
        return None

    def resolve(self, service: dict[str, Any]) -> AuthProvider:
        impl_id = service.get("implementationId")
        host = _host(service.get("serviceInfoUrl") or service.get("url"))
        key = impl_id or host or "default"
        if key in self._cache:
            return self._cache[key]

        spec = self._find_spec(impl_id, host)
        if spec is not None:
            provider = build_provider(spec, self._http, token_store_dir=_TOKEN_STORE_DIR)
        elif self._settings.bearer_token and host in self._settings.bearer_host_set():
            provider = StaticBearerAuth(self._settings.bearer_token)
        else:
            provider = NoAuth()
        self._cache[key] = provider
        return provider

    def describe(self) -> dict[str, Any]:
        return {
            "configured_specs": [
                {"match": s.match, "kind": s.kind} for s in self._specs
            ],
            "global_bearer_configured": bool(self._settings.bearer_token),
            "global_bearer_hosts": sorted(self._settings.bearer_host_set()),
            "auth_config_path": self._settings.auth_config,
            "token_store_dir": _TOKEN_STORE_DIR,
        }
