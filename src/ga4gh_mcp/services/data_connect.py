"""GA4GH Data Connect type-aware helpers (list tables, table info, SQL search)."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from ..auth.base import AuthProvider
from ..http_client import Ga4ghHttpClient, HttpResult
from .base import ServiceTypePlugin, call_api, get_plugin, register

register(ServiceTypePlugin(
    product="DataConnect",
    artifacts={"data-connect"},
    api_base_path="/ga4gh/data-connect/v1",
    capabilities=["data_connect_list_tables", "data_connect_table_info", "data_connect_search"],
    description="Data Connect — list tables, read schemas, and run read-only SQL search over data.",
))
_PLUGIN = get_plugin("DataConnect")


async def list_tables(http: Ga4ghHttpClient, service: dict[str, Any],
                      auth: AuthProvider) -> HttpResult:
    return await call_api(http, service, auth, "GET", "/tables", plugin=_PLUGIN)


async def table_info(http: Ga4ghHttpClient, service: dict[str, Any], auth: AuthProvider,
                     table: str) -> HttpResult:
    return await call_api(http, service, auth, "GET", f"/table/{quote(table, safe='.')}/info",
                          plugin=_PLUGIN)


async def search(http: Ga4ghHttpClient, service: dict[str, Any], auth: AuthProvider,
                 sql: str) -> HttpResult:
    return await call_api(http, service, auth, "POST", "/search",
                          plugin=_PLUGIN, json_body={"query": sql})
