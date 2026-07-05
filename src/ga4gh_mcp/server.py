"""Assemble the FastMCP server: context, tools, transports, health route."""

from __future__ import annotations

import logging

from mcp.server.fastmcp import FastMCP

from .config import Settings, load_settings
from .context import AppContext, set_context
from .tools import register_all

logger = logging.getLogger("ga4gh_mcp")

INSTRUCTIONS = """\
Universal MCP server for GA4GH services and the GA4GH Implementation Registry
(https://registry.ga4gh.org/v1).

Start with the registry tools to discover services:
  - registry_list_services / registry_get_service / registry_search
  - registry_list_service_types / registry_list_implementations
  - registry_check_health (liveness + version + auth of a service)

Access services generically (any type) with service_get_info and service_request,
or use type-aware tools: drs_* (data objects), trs_* (tools/workflows), wes_* (runs).

Services vary in liveness, spec version and auth. Tools return structured results
{ok, data|error, warnings}; they never crash the server. When a tool returns
error.kind == "auth_required", use auth_discover then auth_set_token or auth_login.
"""


def build_server(settings: Settings | None = None) -> tuple[FastMCP, AppContext]:
    settings = settings or load_settings()
    mcp = FastMCP(
        name="ga4gh-mcp-service",
        instructions=INSTRUCTIONS,
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.upper(),
    )
    context = AppContext(settings)
    set_context(context)
    register_all(mcp)

    @mcp.custom_route("/healthz", methods=["GET"])
    async def healthz(_request):  # noqa: ANN001
        from starlette.responses import JSONResponse

        return JSONResponse({"status": "ok", "service": "ga4gh-mcp-service",
                             "registry": settings.registry_url})

    return mcp, context


def configure_logging(level: str) -> None:
    import sys

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        stream=sys.stderr,
    )
