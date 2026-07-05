"""Client for the GA4GH Implementation Registry (https://registry.ga4gh.org/v1).

Wraps the three core collections — ``/services``, ``/implementations`` and
``/services/types`` — plus the registry's own ``/service-info``, with TTL
caching and tolerant parsing.
"""

from __future__ import annotations

import logging

from .cache import TTLCache
from .errors import ERR_UPSTREAM, ToolError
from .http import AsyncHttp
from .models import Implementation, Service, ServiceTypeInfo

logger = logging.getLogger("ga4gh_mcp.registry")


class RegistryClient:
    def __init__(self, base_url: str, http: AsyncHttp, cache: TTLCache) -> None:
        self._base = base_url.rstrip("/")
        self._http = http
        self._cache = cache

    @property
    def base_url(self) -> str:
        return self._base

    async def _get(self, path: str):
        res = await self._http.get_json(f"{self._base}{path}")
        if res.error_kind or res.json is None:
            raise ToolError(
                ERR_UPSTREAM,
                f"registry request {path} failed: {res.error or 'no JSON body'} "
                f"(status={res.status})",
            )
        return res.json

    async def raw_services(self) -> list[dict]:
        return await self._cache.get_or_set("services", lambda: self._get("/services"))

    async def raw_implementations(self) -> list[dict]:
        return await self._cache.get_or_set("implementations", lambda: self._get("/implementations"))

    async def raw_types(self) -> list[dict]:
        return await self._cache.get_or_set("types", lambda: self._get("/services/types"))

    async def service_info(self) -> dict:
        return await self._cache.get_or_set("service-info", lambda: self._get("/service-info"))

    async def services(self) -> list[Service]:
        out: list[Service] = []
        for raw in await self.raw_services():
            try:
                out.append(Service.model_validate(raw))
            except Exception:  # noqa: BLE001 — keep going on a malformed record
                logger.warning("skipping malformed service record: %s", raw.get("id"))
        return out

    async def implementations(self) -> list[Implementation]:
        out: list[Implementation] = []
        for raw in await self.raw_implementations():
            try:
                out.append(Implementation.model_validate(raw))
            except Exception:  # noqa: BLE001
                logger.warning("skipping malformed implementation record: %s", raw.get("id"))
        return out

    async def service_types(self) -> list[ServiceTypeInfo]:
        return [ServiceTypeInfo.model_validate(t) for t in await self.raw_types()]

    async def get_service(self, service_id: str) -> Service | None:
        for svc in await self.services():
            if svc.id == service_id:
                return svc
        return None

    async def find_services(self, *, url: str | None = None, host: str | None = None) -> list[Service]:
        """Find services by exact URL or by host (several services can share a host)."""
        from .normalize import host_of

        matches: list[Service] = []
        for svc in await self.services():
            if not svc.url:
                continue
            if url and svc.url.rstrip("/") == url.rstrip("/"):
                matches.append(svc)
            elif host and host_of(svc.url) == host.lower():
                matches.append(svc)
        return matches

    def invalidate(self) -> None:
        self._cache.invalidate()
