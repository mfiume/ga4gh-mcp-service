"""TES (Task Execution Service) type-aware helpers."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from ..auth.base import AuthProvider
from ..http_client import Ga4ghHttpClient, HttpResult
from .base import ServiceTypePlugin, call_api, get_plugin, register

register(ServiceTypePlugin(
    product="TES",
    artifacts={"tes"},
    api_base_path="/ga4gh/tes/v1",
    capabilities=["tes_list_tasks", "tes_get_task"],
    description="Task Execution Service — list and inspect batch execution tasks.",
))
_PLUGIN = get_plugin("TES")


async def list_tasks(http: Ga4ghHttpClient, service: dict[str, Any], auth: AuthProvider,
                     limit: int = 20) -> HttpResult:
    return await call_api(http, service, auth, "GET", "/tasks",
                          plugin=_PLUGIN, params={"view": "BASIC", "page_size": limit})


async def get_task(http: Ga4ghHttpClient, service: dict[str, Any], auth: AuthProvider,
                   task_id: str) -> HttpResult:
    return await call_api(http, service, auth, "GET", f"/tasks/{quote(task_id, safe='')}",
                          plugin=_PLUGIN, params={"view": "FULL"})
