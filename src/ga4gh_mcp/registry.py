"""Client for the GA4GH Implementation Registry API.

The registry does no server-side filtering and only supports detail-by-UUID, so this
client caches the full lists (TTL) and does all filtering / search / id-resolution locally.
"""

from __future__ import annotations

import time
from typing import Any

from .config import Settings
from .errors import ErrorType, ToolError
from .http_client import Ga4ghHttpClient


class _Cache:
    def __init__(self, ttl: float) -> None:
        self._ttl = ttl
        self._data: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        hit = self._data.get(key)
        if hit and (time.monotonic() - hit[0]) < self._ttl:
            return hit[1]
        return None

    def set(self, key: str, value: Any) -> None:
        self._data[key] = (time.monotonic(), value)

    def clear(self) -> None:
        self._data.clear()


def summarize(s: dict[str, Any]) -> dict[str, Any]:
    """Compact, model-friendly summary of a registry entry."""
    sv = s.get("standardVersion") or {}
    org = s.get("organisation") or {}
    return {
        "id": s.get("id"),
        "implementationId": s.get("implementationId"),
        "name": s.get("name"),
        "product": sv.get("ga4ghProduct"),
        "version": sv.get("version"),
        "implementationType": s.get("implementationType"),
        "environment": s.get("environment"),
        "organisation": org.get("name"),
        "url": s.get("url"),
        "serviceInfoUrl": s.get("serviceInfoUrl"),
        "has_service_info_url": bool(s.get("serviceInfoUrl")),
    }


class RegistryClient:
    def __init__(self, http: Ga4ghHttpClient, settings: Settings) -> None:
        self._http = http
        self._settings = settings
        self._cache = _Cache(settings.registry_cache_ttl)

    async def _get_list(self, endpoint: str) -> list[dict[str, Any]]:
        cached = self._cache.get(endpoint)
        if cached is not None:
            return cached
        url = self._settings.registry_base_url.rstrip("/") + "/" + endpoint
        res = await self._http.get_json(url)
        if res.liveness.value != "live" or not isinstance(res.json, list):
            raise ToolError(
                ErrorType.UPSTREAM,
                f"registry endpoint /{endpoint} unavailable "
                f"({res.status or res.liveness.value})",
                detail=res.error,
                hint="The GA4GH Implementation Registry may be down; retry shortly.",
            )
        self._cache.set(endpoint, res.json)
        return res.json

    async def services(self) -> list[dict[str, Any]]:
        return await self._get_list("services")

    async def deployments(self) -> list[dict[str, Any]]:
        return await self._get_list("deployments")

    async def organisations(self) -> list[dict[str, Any]]:
        return await self._get_list("organisations")

    async def standards(self) -> list[dict[str, Any]]:
        return await self._get_list("standards")

    async def implementations(self, include_deployments: bool = False) -> list[dict[str, Any]]:
        items = list(await self.services())
        if include_deployments:
            items += await self.deployments()
        return items

    def invalidate(self) -> None:
        self._cache.clear()

    # ---- filtering / search ----
    async def list_services(
        self,
        *,
        product: str | None = None,
        org: str | None = None,
        version: str | None = None,
        environment: str | None = None,
        implementation_type: str | None = None,
        query: str | None = None,
        include_deployments: bool = False,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        items = await self.implementations(include_deployments=include_deployments)
        out = [s for s in items if self._match(
            s, product, org, version, environment, implementation_type, query)]
        if limit is not None:
            out = out[:limit]
        return out

    @staticmethod
    def _match(s, product, org, version, environment, implementation_type, query) -> bool:
        sv = s.get("standardVersion") or {}
        o = s.get("organisation") or {}
        if product and (sv.get("ga4ghProduct") or "").lower() != product.lower():
            return False
        if version and not str(sv.get("version") or "").startswith(version):
            return False
        if environment and (s.get("environment") or "").lower() != environment.lower():
            return False
        if implementation_type and (s.get("implementationType") or "").lower() != implementation_type.lower():
            return False
        if org:
            hay = " ".join(str(o.get(k) or "") for k in ("name", "orgId", "shortName")).lower()
            if org.lower() not in hay:
                return False
        if query:
            blob = " ".join(str(s.get(k) or "") for k in (
                "name", "description", "implementationId", "url", "curiePrefix")).lower()
            blob += " " + str(o.get("name") or "").lower()
            if query.lower() not in blob:
                return False
        return True

    async def search(self, query: str, *, limit: int = 25,
                     include_deployments: bool = True) -> list[dict[str, Any]]:
        return await self.list_services(query=query, include_deployments=include_deployments,
                                        limit=limit)

    async def get_service(self, service_id: str) -> dict[str, Any]:
        """Resolve by UUID or implementationId, checking services then deployments."""
        items = await self.implementations(include_deployments=True)
        for s in items:
            if s.get("id") == service_id or s.get("implementationId") == service_id:
                return s
        # Fallback: direct UUID lookup (implementationId is unsupported by the API).
        if "-" in service_id and len(service_id) >= 32:
            url = self._settings.registry_base_url.rstrip("/") + "/services/" + service_id
            res = await self._http.get_json(url)
            if res.liveness.value == "live" and isinstance(res.json, dict):
                return res.json
        raise ToolError(
            ErrorType.NOT_FOUND,
            f"no registered service with id or implementationId '{service_id}'",
            hint="Use list_services or search_services to find a valid id.",
        )

    async def service_types(self) -> dict[str, Any]:
        services = await self.services()
        deployments = await self.deployments()
        standards = await self.standards()

        def tally(items):
            counts: dict[str, int] = {}
            for s in items:
                p = (s.get("standardVersion") or {}).get("ga4ghProduct") or "unknown"
                counts[p] = counts.get(p, 0) + 1
            return counts

        return {
            "service_counts": tally(services),
            "deployment_counts": tally(deployments),
            "known_standards": [
                {
                    "abbreviation": st.get("abbreviation"),
                    "name": st.get("name"),
                    "type": st.get("standardType"),
                    "versions": [v.get("version") for v in (st.get("versions") or [])],
                }
                for st in standards
            ],
        }
