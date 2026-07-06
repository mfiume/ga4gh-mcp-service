"""Builds the FastMCP server and registers the tool surface.

Tool bodies live in ``tools.py`` (transport-agnostic, unit-testable). Here we register
thin wrappers whose signatures/docstrings become each tool's MCP schema + description.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from mcp.server.fastmcp import FastMCP

from . import tools
from .config import Settings, load_settings
from .context import ServerContext

INSTRUCTIONS = """\
Universal MCP server for GA4GH services. It surfaces the GA4GH Implementation Registry
(list/detail/search/health across DRS, TES, TRS, Beacon, WES, htsget and more) and provides
generic (service-info driven) plus type-aware access to registered services.

Registered implementations vary in liveness, spec compliance, and version. Every tool returns
a structured envelope: {"ok": bool, "data"|"error", "warnings": [...]}. Start with
list_services / search_services to find a service id, then get_service / check_service_health /
get_service_info, then type-aware tools (drs_*, trs_*, tes_*, beacon_info) or the generic
call_service_endpoint. Auth is discovered per service; see auth_status.
"""


def build_server(settings: Settings | None = None,
                 ctx: ServerContext | None = None) -> FastMCP:
    settings = settings or load_settings()
    context = ctx or ServerContext.create(settings)

    @asynccontextmanager
    async def lifespan(_server: FastMCP):
        try:
            yield {}
        finally:
            await context.aclose()

    mcp = FastMCP(
        name="ga4gh-mcp-service",
        instructions=INSTRUCTIONS,
        host=settings.host,
        port=settings.port,
        streamable_http_path=settings.http_path,
        stateless_http=settings.stateless_http,
        lifespan=lifespan,
    )

    # ---------------------------------------------------------------- registry tools
    @mcp.tool()
    async def list_services(
        product: str | None = None,
        org: str | None = None,
        version: str | None = None,
        environment: str | None = None,
        implementation_type: str | None = None,
        query: str | None = None,
        include_deployments: bool = False,
        limit: int = 100,
    ) -> dict[str, Any]:
        """List services in the GA4GH Implementation Registry, with optional filters.

        Args:
            product: GA4GH product/type, e.g. "DRS", "TES", "TRS", "Beacon", "WES", "htsget".
            org: substring match on the organisation name / id / short name.
            version: match services whose declared spec version starts with this (e.g. "1.2").
            environment: e.g. "PRODUCTION".
            implementation_type: "SERVICE" or "DEPLOYMENT".
            query: free-text across name/description/implementationId/url/organisation.
            include_deployments: also include DEPLOYMENT entries (default: only SERVICE).
            limit: max results (default 100).
        """
        return await tools.list_services(
            context, product=product, org=org, version=version, environment=environment,
            implementation_type=implementation_type, query=query,
            include_deployments=include_deployments, limit=limit)

    @mcp.tool()
    async def get_service(service_id: str) -> dict[str, Any]:
        """Get the full registry entry for a service by UUID or implementationId."""
        return await tools.get_service(context, service_id=service_id)

    @mcp.tool()
    async def search_services(query: str, limit: int = 25) -> dict[str, Any]:
        """Free-text search across all registered services and deployments."""
        return await tools.search_services(context, query=query, limit=limit)

    @mcp.tool()
    async def list_service_types() -> dict[str, Any]:
        """Summarize service types present (counts) + the GA4GH standards the registry knows +
        which types have type-aware helpers here."""
        return await tools.list_service_types(context)

    @mcp.tool()
    async def list_standards() -> dict[str, Any]:
        """List the GA4GH standards catalog (DRS, WES, TES, TRS, htsget, Beacon, …) with versions."""
        return await tools.list_standards(context)

    @mcp.tool()
    async def list_organisations(query: str | None = None) -> dict[str, Any]:
        """List organisations registered in the registry (optionally filtered by substring)."""
        return await tools.list_organisations(context, query=query)

    @mcp.tool()
    async def check_service_health(service_id: str) -> dict[str, Any]:
        """Probe a registered service and return a structured liveness + compliance report:
        reachability class, HTTP status, latency, service-info version reconciliation, and any
        auth requirement discovered. Tolerates down/non-compliant/version-mismatched services."""
        return await tools.check_service_health(context, service_id=service_id)

    # ------------------------------------------------------------- generic access tools
    @mcp.tool()
    async def get_service_info(service_id: str | None = None,
                               url: str | None = None) -> dict[str, Any]:
        """Fetch and normalize a service's /service-info (by registry service_id, or a raw url).
        Returns a shape-tolerant analysis with version reconciliation and compliance warnings."""
        return await tools.get_service_info(context, service_id=service_id, url=url)

    @mcp.tool()
    async def call_service_endpoint(service_id: str, path: str, method: str = "GET",
                                    query: dict[str, Any] | None = None,
                                    json_body: Any = None) -> dict[str, Any]:
        """Generic authenticated call to any registered service (works across all types via the
        service's base URL). `path` is relative to the service API base (e.g. "/objects/{id}").
        Returns the structured envelope; on 401 it includes an auth hint."""
        return await tools.call_service_endpoint(
            context, service_id=service_id, path=path, method=method,
            query=query, json_body=json_body)

    # -------------------------------------------------------------- type-aware helpers
    @mcp.tool()
    async def drs_get_object(service_id: str, object_id: str) -> dict[str, Any]:
        """DRS: fetch a data object's metadata (bundles, checksums, access methods)."""
        return await tools.drs_get_object(context, service_id=service_id, object_id=object_id)

    @mcp.tool()
    async def drs_get_access_url(service_id: str, object_id: str,
                                 access_id: str | None = None) -> dict[str, Any]:
        """DRS: resolve a concrete access URL for a data object (dereferences access_id if needed)."""
        return await tools.drs_get_access_url(
            context, service_id=service_id, object_id=object_id, access_id=access_id)

    @mcp.tool()
    async def trs_list_tools(service_id: str, limit: int = 20) -> dict[str, Any]:
        """TRS: list registered tools/workflows."""
        return await tools.trs_list_tools(context, service_id=service_id, limit=limit)

    @mcp.tool()
    async def trs_get_tool(service_id: str, tool_id: str) -> dict[str, Any]:
        """TRS: get a single tool/workflow by id."""
        return await tools.trs_get_tool(context, service_id=service_id, tool_id=tool_id)

    @mcp.tool()
    async def tes_list_tasks(service_id: str, limit: int = 20) -> dict[str, Any]:
        """TES: list execution tasks (BASIC view)."""
        return await tools.tes_list_tasks(context, service_id=service_id, limit=limit)

    @mcp.tool()
    async def tes_get_task(service_id: str, task_id: str) -> dict[str, Any]:
        """TES: get a single task (FULL view)."""
        return await tools.tes_get_task(context, service_id=service_id, task_id=task_id)

    @mcp.tool()
    async def beacon_info(service_id: str) -> dict[str, Any]:
        """Beacon: fetch the Beacon v2 framework info document."""
        return await tools.beacon_info(context, service_id=service_id)

    @mcp.tool()
    async def data_connect_list_tables(service_id: str) -> dict[str, Any]:
        """Data Connect: list the tables a service exposes (e.g. AWS Open Data variant tables)."""
        return await tools.data_connect_list_tables(context, service_id=service_id)

    @mcp.tool()
    async def data_connect_table_info(service_id: str, table: str) -> dict[str, Any]:
        """Data Connect: get a table's JSON-Schema data model (columns + types)."""
        return await tools.data_connect_table_info(context, service_id=service_id, table=table)

    @mcp.tool()
    async def data_connect_search(service_id: str, sql: str) -> dict[str, Any]:
        """Data Connect: run a read-only SQL query against a service's tables and return rows.
        Example: SELECT gene, oe_lof_upper AS loeuf FROM gnomad.gene_constraint WHERE gene='BRCA1'."""
        return await tools.data_connect_search(context, service_id=service_id, sql=sql)

    # ------------------------------------------------------------------------ auth tools
    @mcp.tool()
    async def auth_status() -> dict[str, Any]:
        """Report configured auth providers, the global bearer allow-list, and token store path."""
        return await tools.auth_status(context)

    @mcp.tool()
    async def auth_device_login(service_id: str, wait: bool = False) -> dict[str, Any]:
        """Start the OAuth2 device-code flow for a service configured with it. Returns a
        verification URI + user code. Set wait=true to block until authorized (CLI-friendly)."""
        return await tools.auth_device_login(context, service_id=service_id, wait=wait)

    mcp._ga4gh_context = context  # type: ignore[attr-defined]  # handle for tests/shutdown
    return mcp


TOOL_NAMES = [
    "list_services", "get_service", "search_services", "list_service_types", "list_standards",
    "list_organisations", "check_service_health", "get_service_info", "call_service_endpoint",
    "drs_get_object", "drs_get_access_url", "trs_list_tools", "trs_get_tool",
    "tes_list_tasks", "tes_get_task", "beacon_info",
    "data_connect_list_tables", "data_connect_table_info", "data_connect_search",
    "auth_status", "auth_device_login",
]
