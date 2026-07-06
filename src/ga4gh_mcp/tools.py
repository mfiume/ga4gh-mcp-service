"""Tool implementations (transport-agnostic).

Each function returns a structured envelope (see ``errors.ok`` / ``errors.err``) and is
wrapped by ``guarded`` so no upstream failure or bug can crash the MCP server.
``server.py`` registers thin ``@mcp.tool()`` wrappers around these.
"""

from __future__ import annotations

from functools import wraps
from typing import Any

from .auth.resolver import parse_www_authenticate
from .context import ServerContext
from .errors import ErrorType, Liveness, ToolError, err, ok
from .http_client import HttpResult
from .liveness import check_liveness
from .registry import summarize
from .serviceinfo import analyze_service_info
from .services import all_plugins, api_base, get_plugin
from .services import beacon as beacon_mod
from .services import data_connect as dc_mod
from .services import drs as drs_mod
from .services import tes as tes_mod
from .services import trs as trs_mod


def guarded(fn):
    @wraps(fn)
    async def wrapper(*args, **kwargs):
        try:
            return await fn(*args, **kwargs)
        except ToolError as e:
            return err(e.error_type, e.message, detail=e.detail, hint=e.hint)
        except Exception as e:  # noqa: BLE001 - final safety net; never crash the transport
            return err(ErrorType.INTERNAL, f"unexpected error: {e}", detail=type(e).__name__)

    return wrapper


def _upstream_meta(res: HttpResult) -> dict[str, Any]:
    return {"url": res.url, "liveness": res.liveness.value,
            "http_status": res.status, "latency_ms": res.latency_ms}


def _res_envelope(res: HttpResult, *, warnings: list[str] | None = None) -> dict[str, Any]:
    """Convert an HttpResult from a type-aware/generic call into a tool envelope."""
    warnings = warnings or []
    if res.liveness == Liveness.AUTH_REQUIRED:
        hint = parse_www_authenticate(res.headers.get("www-authenticate"))
        return err(ErrorType.AUTH, "service requires authentication",
                   detail={"auth": hint.model_dump(exclude_none=True), **_upstream_meta(res)},
                   hint=hint.guidance or "See docs/auth.md to configure credentials.",
                   warnings=warnings)
    if res.liveness == Liveness.LIVE and res.json is not None:
        return ok(res.json, warnings=warnings, upstream=_upstream_meta(res))
    if res.reachable and res.json is not None:
        return ok(res.json, warnings=warnings + ["upstream response may be non-standard"],
                  upstream=_upstream_meta(res))
    return err(ErrorType.UPSTREAM,
               f"upstream call failed ({res.status or res.liveness.value})",
               detail={"error": res.error, **_upstream_meta(res)}, warnings=warnings)


# --------------------------------------------------------------------------- registry

@guarded
async def list_services(ctx: ServerContext, *, product: str | None = None, org: str | None = None,
                        version: str | None = None, environment: str | None = None,
                        implementation_type: str | None = None, query: str | None = None,
                        include_deployments: bool = False, limit: int = 100) -> dict[str, Any]:
    items = await ctx.registry.list_services(
        product=product, org=org, version=version, environment=environment,
        implementation_type=implementation_type, query=query,
        include_deployments=include_deployments, limit=limit)
    return ok([summarize(s) for s in items], count=len(items),
              filters={"product": product, "org": org, "version": version,
                       "environment": environment, "implementation_type": implementation_type,
                       "query": query, "include_deployments": include_deployments})


@guarded
async def get_service(ctx: ServerContext, *, service_id: str) -> dict[str, Any]:
    s = await ctx.registry.get_service(service_id)
    return ok(s)


@guarded
async def search_services(ctx: ServerContext, *, query: str, limit: int = 25) -> dict[str, Any]:
    items = await ctx.registry.search(query, limit=limit)
    return ok([summarize(s) for s in items], count=len(items), query=query)


@guarded
async def list_service_types(ctx: ServerContext) -> dict[str, Any]:
    data = await ctx.registry.service_types()
    plugins = {pl.product: {"artifacts": sorted(pl.artifacts), "capabilities": pl.capabilities,
                            "description": pl.description}
               for pl in all_plugins().values()}
    data["type_aware_plugins"] = plugins
    return ok(data)


@guarded
async def list_standards(ctx: ServerContext) -> dict[str, Any]:
    st = await ctx.registry.standards()
    return ok(st, count=len(st))


@guarded
async def list_organisations(ctx: ServerContext, *, query: str | None = None) -> dict[str, Any]:
    orgs = await ctx.registry.organisations()
    if query:
        q = query.lower()
        orgs = [o for o in orgs if q in " ".join(
            str(o.get(k) or "") for k in ("name", "orgId", "shortName", "description")).lower()]
    return ok(orgs, count=len(orgs))


@guarded
async def check_service_health(ctx: ServerContext, *, service_id: str) -> dict[str, Any]:
    s = await ctx.registry.get_service(service_id)
    report = await check_liveness(ctx.http, s, ctx.resolver)
    return ok(report.to_dict(), warnings=report.warnings)


# ------------------------------------------------------------------------ generic access

@guarded
async def get_service_info(ctx: ServerContext, *, service_id: str | None = None,
                           url: str | None = None) -> dict[str, Any]:
    if not service_id and not url:
        raise ToolError(ErrorType.VALIDATION, "provide either service_id or url")
    if url and not service_id:
        res = await ctx.http.get_json(url)
        if not res.reachable or res.json is None:
            return _res_envelope(res)
        analysis = analyze_service_info(res.json)
        return ok(analysis.model_dump(exclude_none=True), warnings=analysis.warnings,
                  upstream=_upstream_meta(res))
    s = await ctx.registry.get_service(service_id)  # type: ignore[arg-type]
    report = await check_liveness(ctx.http, s, ctx.resolver)
    payload = report.service_info.model_dump(exclude_none=True) if report.service_info else None
    if payload is None:
        return err(ErrorType.UPSTREAM,
                   f"could not retrieve service-info ({report.liveness.value})",
                   detail={"liveness": report.liveness.value, "http_status": report.http_status,
                           "error": report.error,
                           "auth": report.auth.model_dump(exclude_none=True) if report.auth else None},
                   warnings=report.warnings)
    return ok(payload, warnings=report.warnings, liveness=report.liveness.value)


@guarded
async def call_service_endpoint(ctx: ServerContext, *, service_id: str, path: str,
                                method: str = "GET", query: dict[str, Any] | None = None,
                                json_body: Any = None) -> dict[str, Any]:
    method = method.upper()
    if method not in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"}:
        raise ToolError(ErrorType.VALIDATION, f"unsupported method: {method}")
    s = await ctx.registry.get_service(service_id)
    product = (s.get("standardVersion") or {}).get("ga4ghProduct")
    plugin = get_plugin(product)
    base = api_base(s, plugin)
    if not base:
        raise ToolError(ErrorType.UPSTREAM, "no base URL for this service",
                        hint="Service has no serviceInfoUrl or url in the registry.")
    if not path.startswith("/"):
        path = "/" + path
    auth = ctx.resolver.resolve(s)
    headers = await auth.headers()
    res = await ctx.http.request(method, base + path, headers=headers or None,
                                 params=query, json_body=json_body)
    warnings = []
    if method not in {"GET", "HEAD"}:
        warnings.append(f"executed a {method} request against a live service.")
    return _res_envelope(res, warnings=warnings)


# ------------------------------------------------------------------------- type-aware

async def _service_and_auth(ctx: ServerContext, service_id: str, expected_product: str):
    s = await ctx.registry.get_service(service_id)
    product = (s.get("standardVersion") or {}).get("ga4ghProduct") or ""
    if product.upper() != expected_product.upper():
        raise ToolError(
            ErrorType.UNSUPPORTED,
            f"service '{service_id}' is a {product or 'unknown'} service, not {expected_product}",
            hint=f"Use the {product}-appropriate tool, or call_service_endpoint for generic access.",
        )
    return s, ctx.resolver.resolve(s)


@guarded
async def drs_get_object(ctx: ServerContext, *, service_id: str, object_id: str) -> dict[str, Any]:
    s, auth = await _service_and_auth(ctx, service_id, "DRS")
    return _res_envelope(await drs_mod.get_object(ctx.http, s, auth, object_id))


@guarded
async def drs_get_access_url(ctx: ServerContext, *, service_id: str, object_id: str,
                             access_id: str | None = None) -> dict[str, Any]:
    s, auth = await _service_and_auth(ctx, service_id, "DRS")
    data = await drs_mod.get_access_url(ctx.http, s, auth, object_id, access_id)
    return ok(data)


@guarded
async def trs_list_tools(ctx: ServerContext, *, service_id: str, limit: int = 20) -> dict[str, Any]:
    s, auth = await _service_and_auth(ctx, service_id, "TRS")
    return _res_envelope(await trs_mod.list_tools(ctx.http, s, auth, limit))


@guarded
async def trs_get_tool(ctx: ServerContext, *, service_id: str, tool_id: str) -> dict[str, Any]:
    s, auth = await _service_and_auth(ctx, service_id, "TRS")
    return _res_envelope(await trs_mod.get_tool(ctx.http, s, auth, tool_id))


@guarded
async def tes_list_tasks(ctx: ServerContext, *, service_id: str, limit: int = 20) -> dict[str, Any]:
    s, auth = await _service_and_auth(ctx, service_id, "TES")
    return _res_envelope(await tes_mod.list_tasks(ctx.http, s, auth, limit))


@guarded
async def tes_get_task(ctx: ServerContext, *, service_id: str, task_id: str) -> dict[str, Any]:
    s, auth = await _service_and_auth(ctx, service_id, "TES")
    return _res_envelope(await tes_mod.get_task(ctx.http, s, auth, task_id))


@guarded
async def beacon_info(ctx: ServerContext, *, service_id: str) -> dict[str, Any]:
    s, auth = await _service_and_auth(ctx, service_id, "Beacon")
    return _res_envelope(await beacon_mod.beacon_info(ctx.http, s, auth))


@guarded
async def data_connect_list_tables(ctx: ServerContext, *, service_id: str) -> dict[str, Any]:
    s, auth = await _service_and_auth(ctx, service_id, "DataConnect")
    return _res_envelope(await dc_mod.list_tables(ctx.http, s, auth))


@guarded
async def data_connect_table_info(ctx: ServerContext, *, service_id: str,
                                  table: str) -> dict[str, Any]:
    s, auth = await _service_and_auth(ctx, service_id, "DataConnect")
    return _res_envelope(await dc_mod.table_info(ctx.http, s, auth, table))


@guarded
async def data_connect_search(ctx: ServerContext, *, service_id: str, sql: str) -> dict[str, Any]:
    s, auth = await _service_and_auth(ctx, service_id, "DataConnect")
    return _res_envelope(await dc_mod.search(ctx.http, s, auth, sql))


# ------------------------------------------------------------------------------- auth

@guarded
async def auth_status(ctx: ServerContext) -> dict[str, Any]:
    return ok(ctx.resolver.describe())


@guarded
async def auth_device_login(ctx: ServerContext, *, service_id: str,
                            wait: bool = False) -> dict[str, Any]:
    s = await ctx.registry.get_service(service_id)
    provider = ctx.resolver.resolve(s)
    if provider.kind != "oauth2_device_code":
        raise ToolError(
            ErrorType.VALIDATION,
            f"service '{service_id}' is not configured for the device-code flow "
            f"(resolved provider: {provider.kind})",
            hint="Add an oauth2_device_code entry for this service in the auth config; see docs/auth.md.",
        )
    start = await provider.start()  # type: ignore[attr-defined]
    result = {"instructions": "Open the verification URI and enter the user code to authorize.",
              **start}
    if wait:
        authorized = await provider.poll_until_authorized()  # type: ignore[attr-defined]
        result["authorized"] = authorized
    return ok(result)
