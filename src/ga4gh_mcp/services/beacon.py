"""Beacon (v2) type-aware helper.

Beacon publishes a framework 'info' document (``/api/info`` or ``/info``) rather than a
GA4GH service-info. We fetch the registered ``serviceInfoUrl`` directly and hand the raw
document back; ``analyze_service_info`` maps it best-effort.
"""

from __future__ import annotations

from typing import Any

from ..auth.base import AuthProvider
from ..http_client import Ga4ghHttpClient, HttpResult
from .base import ServiceTypePlugin, register

register(ServiceTypePlugin(
    product="Beacon",
    artifacts={"beacon"},
    api_base_path="",
    capabilities=["beacon_info"],
    description="GA4GH Beacon v2 — genomic variant discovery; framework 'info' document.",
))


async def beacon_info(http: Ga4ghHttpClient, service: dict[str, Any],
                      auth: AuthProvider) -> HttpResult:
    url = service.get("serviceInfoUrl")
    if not url:
        base = (service.get("url") or "").rstrip("/")
        url = f"{base}/info" if base else ""
    headers = await auth.headers()
    return await http.request("GET", url, headers=headers or None)
