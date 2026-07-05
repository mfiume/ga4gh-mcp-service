"""DRS (Data Repository Service) type-aware helpers."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from ..auth.base import AuthProvider
from ..errors import ErrorType, ToolError
from ..http_client import Ga4ghHttpClient, HttpResult
from .base import ServiceTypePlugin, call_api, get_plugin, register

register(ServiceTypePlugin(
    product="DRS",
    artifacts={"drs"},
    api_base_path="/ga4gh/drs/v1",
    capabilities=["drs_get_object", "drs_get_access_url"],
    description="Data Repository Service — resolve data object metadata and access URLs.",
))
_PLUGIN = get_plugin("DRS")


async def get_object(http: Ga4ghHttpClient, service: dict[str, Any], auth: AuthProvider,
                     object_id: str) -> HttpResult:
    return await call_api(http, service, auth, "GET", f"/objects/{quote(object_id, safe='')}",
                          plugin=_PLUGIN)


async def get_access_url(http: Ga4ghHttpClient, service: dict[str, Any], auth: AuthProvider,
                         object_id: str, access_id: str | None = None) -> dict[str, Any]:
    """Return a concrete access URL for a DRS object.

    If ``access_id`` is omitted, fetch the object and pick the first access method,
    returning any inline ``access_url`` directly or dereferencing its ``access_id``.
    """
    if access_id is None:
        obj = await get_object(http, service, auth, object_id)
        if not isinstance(obj.json, dict):
            raise ToolError(ErrorType.UPSTREAM,
                            f"could not fetch DRS object ({obj.status or obj.liveness.value})",
                            detail=obj.error)
        methods = obj.json.get("access_methods") or []
        if not methods:
            raise ToolError(ErrorType.UPSTREAM, "DRS object has no access_methods",
                            detail={"object_id": object_id})
        m = methods[0]
        if m.get("access_url"):
            return {"access_url": m["access_url"], "access_method": m,
                    "source": "inline access_url"}
        access_id = m.get("access_id")
        if not access_id:
            raise ToolError(ErrorType.UPSTREAM,
                            "first access_method has neither access_url nor access_id",
                            detail=m)
    res = await call_api(http, service, auth, "GET",
                         f"/objects/{quote(object_id, safe='')}/access/{quote(access_id, safe='')}",
                         plugin=_PLUGIN)
    if not isinstance(res.json, dict):
        raise ToolError(ErrorType.UPSTREAM,
                        f"could not fetch DRS access URL ({res.status or res.liveness.value})",
                        detail=res.error)
    return {"access_url": res.json, "access_id": access_id, "source": "access endpoint"}
