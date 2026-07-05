"""Liveness + compliance probing for a single registered service.

Produces a structured :class:`HealthReport` and never raises: every failure mode becomes
a classified status so one bad service can't take down a listing or the server.
"""

from __future__ import annotations

from typing import Any

from .auth.resolver import AuthResolver, parse_www_authenticate
from .errors import Liveness
from .http_client import Ga4ghHttpClient
from .models import HealthReport
from .serviceinfo import analyze_service_info
from .services import get_plugin


def _service_info_url(service: dict[str, Any]) -> tuple[str | None, bool]:
    """Return (url, inferred?). Infers from base url + plugin path when not registered."""
    si = service.get("serviceInfoUrl")
    if si:
        return si, False
    product = (service.get("standardVersion") or {}).get("ga4ghProduct")
    plugin = get_plugin(product)
    base = service.get("url")
    if plugin and base and plugin.api_base_path:
        return base.rstrip("/") + plugin.api_base_path + "/service-info", True
    return None, False


async def check_liveness(
    http: Ga4ghHttpClient,
    service: dict[str, Any],
    resolver: AuthResolver,
) -> HealthReport:
    sv = service.get("standardVersion") or {}
    product = sv.get("ga4ghProduct")
    report = HealthReport(
        service_id=service.get("id"),
        implementation_id=service.get("implementationId"),
        name=service.get("name"),
        product=product,
        service_info_url=service.get("serviceInfoUrl"),
        liveness=Liveness.NO_SERVICE_INFO_URL,
    )

    url, inferred = _service_info_url(service)
    if not url:
        report.warnings.append(
            "registry entry has no serviceInfoUrl and none could be inferred from its base url."
        )
        return report
    report.probed_url = url
    if inferred:
        report.warnings.append(f"serviceInfoUrl not registered; inferred as {url}")

    auth = resolver.resolve(service)
    headers = await auth.headers()
    res = await http.get_json(url, headers=headers or None)

    report.liveness = res.liveness
    report.http_status = res.status
    report.latency_ms = res.latency_ms
    report.error = res.error

    if res.liveness == Liveness.AUTH_REQUIRED:
        report.auth = parse_www_authenticate(res.headers.get("www-authenticate"))
        if not report.auth.required:
            report.auth.required = True
            report.auth.guidance = (
                "Service returned 401/403 without a WWW-Authenticate header; credentials are "
                "required. See docs/auth.md to configure a provider."
            )
        return report

    if res.reachable and isinstance(res.json, dict):
        analysis = analyze_service_info(
            res.json,
            declared_product=product,
            declared_version=sv.get("version"),
        )
        report.service_info = analysis
        report.warnings.extend(analysis.warnings)
        if analysis.compliant or analysis.shape == "beacon":
            # Beacon publishes a valid framework 'info' doc (not GA4GH service-info) — still live.
            report.liveness = Liveness.LIVE
        elif res.liveness == Liveness.LIVE:
            # Reachable + JSON but non-compliant, non-Beacon service-info.
            report.liveness = Liveness.INVALID_RESPONSE
            report.warnings.append(
                "service returned JSON but it is not a spec-compliant GA4GH service-info."
            )
    return report
