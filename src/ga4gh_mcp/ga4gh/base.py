"""Base for type-aware GA4GH service clients.

Handles the two cross-cutting concerns every typed client needs: recovering the
correct API base URL (accounting for the registry's inconsistent URLs and each
spec's nested prefix) and attaching the right auth headers.
"""

from __future__ import annotations

from ..auth.manager import AuthManager
from ..http import AsyncHttp, HttpResult
from ..normalize import api_base_url


class TypedClient:
    #: Artifact name this client serves (e.g. "drs").
    artifact: str = ""

    def __init__(self, http: AsyncHttp, auth: AuthManager, timeout: float | None = None) -> None:
        self._http = http
        self._auth = auth
        self._timeout = timeout

    def api_base(self, url: str) -> str:
        """Return the API base including the spec's nested prefix if needed."""
        return api_base_url(url, self.artifact)

    async def _get(self, url: str, path: str, params: dict | None = None) -> HttpResult:
        full = f"{self.api_base(url)}{path}"
        headers = await self._auth.resolve_headers(full)
        return await self._http.get_json(full, params=params, headers=headers, timeout=self._timeout)

    async def _post(self, url: str, path: str, json: dict | None = None) -> HttpResult:
        full = f"{self.api_base(url)}{path}"
        headers = await self._auth.resolve_headers(full)
        return await self._http.request("POST", full, json=json, headers=headers, timeout=self._timeout)
