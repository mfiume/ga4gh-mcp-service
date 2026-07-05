"""Service-type plugin registry — the extensibility point for new GA4GH types.

Adding a new type = create a module that builds a :class:`ServiceTypePlugin` and calls
``register(...)`` at import time, then import it in ``services/__init__.py``. Generic
service-info access works for *any* type even without a dedicated plugin.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from ..auth.base import AuthProvider
from ..http_client import Ga4ghHttpClient, HttpResult


@dataclass
class ServiceTypePlugin:
    product: str  # canonical registry product name, e.g. "DRS"
    artifacts: set[str]  # service-info type.artifact values, e.g. {"drs"}
    api_base_path: str  # default path under the host, e.g. "/ga4gh/drs/v1"
    capabilities: list[str] = field(default_factory=list)  # type-aware tools offered
    description: str = ""


_PLUGINS: dict[str, ServiceTypePlugin] = {}


def register(plugin: ServiceTypePlugin) -> None:
    _PLUGINS[plugin.product.upper()] = plugin


def get_plugin(product: str | None) -> ServiceTypePlugin | None:
    if not product:
        return None
    return _PLUGINS.get(product.upper())


def plugin_for_artifact(artifact: str | None) -> ServiceTypePlugin | None:
    if not artifact:
        return None
    a = artifact.lower()
    for p in _PLUGINS.values():
        if a in p.artifacts:
            return p
    return None


def all_plugins() -> dict[str, ServiceTypePlugin]:
    return dict(_PLUGINS)


def api_base(service: dict[str, Any], plugin: ServiceTypePlugin | None) -> str | None:
    """Best-effort base URL for a service's API (without the ``/service-info`` suffix)."""
    si = service.get("serviceInfoUrl")
    if si:
        u = si.rstrip("/")
        if u.lower().endswith("/service-info"):
            return u[: -len("/service-info")]
        return u
    base = service.get("url")
    if base and plugin:
        return base.rstrip("/") + plugin.api_base_path
    return base.rstrip("/") if base else None


async def call_api(
    http: Ga4ghHttpClient,
    service: dict[str, Any],
    auth: AuthProvider,
    method: str,
    subpath: str,
    *,
    plugin: ServiceTypePlugin | None = None,
    params: dict[str, Any] | None = None,
    json_body: Any = None,
) -> HttpResult:
    """Call ``{api_base}{subpath}`` with resolved auth headers. Never raises transport errors."""
    base = api_base(service, plugin)
    if not base:
        return HttpResult(url="", liveness=http_no_url(), error="no base URL for service")
    url = base + subpath
    headers = await auth.headers()
    return await http.request(method, url, headers=headers or None, params=params, json_body=json_body)


def http_no_url():
    from ..errors import Liveness

    return Liveness.NO_SERVICE_INFO_URL
