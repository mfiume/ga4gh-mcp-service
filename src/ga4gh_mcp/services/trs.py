"""TRS (Tool Registry Service) type-aware helpers."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from ..auth.base import AuthProvider
from ..http_client import Ga4ghHttpClient, HttpResult
from .base import ServiceTypePlugin, call_api, get_plugin, register

register(ServiceTypePlugin(
    product="TRS",
    artifacts={"trs"},
    api_base_path="/ga4gh/trs/v2",
    capabilities=["trs_list_tools", "trs_get_tool"],
    description="Tool Registry Service — list and inspect registered workflows/tools.",
))
_PLUGIN = get_plugin("TRS")


async def list_tools(http: Ga4ghHttpClient, service: dict[str, Any], auth: AuthProvider,
                     limit: int = 20) -> HttpResult:
    return await call_api(http, service, auth, "GET", "/tools",
                          plugin=_PLUGIN, params={"limit": limit})


async def get_tool(http: Ga4ghHttpClient, service: dict[str, Any], auth: AuthProvider,
                   tool_id: str) -> HttpResult:
    return await call_api(http, service, auth, "GET", f"/tools/{quote(tool_id, safe='')}",
                          plugin=_PLUGIN)
