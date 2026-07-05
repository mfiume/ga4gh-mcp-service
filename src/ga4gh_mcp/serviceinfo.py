"""Generic, version-tolerant GA4GH ``service-info`` fetching and liveness probing.

This is the common denominator across *all* GA4GH services and the mechanism
that lets the server work against service types it has no bespoke code for.
"""

from __future__ import annotations

from typing import Any

from .http import AsyncHttp, HttpResult
from .normalize import (
    classify_liveness,
    looks_like_service_info,
    parse_version,
    parse_www_authenticate,
    service_info_candidates,
)


def _rank(res: HttpResult) -> int:
    """Prefer the most *informative* attempt when none returned a service-info."""
    if res.status in (401, 403):
        return 5  # auth challenge — very informative
    if res.status == 404:
        return 4  # reachable, just no service-info here
    if res.status == 200:
        return 3  # reachable but body wasn't a service-info (SPA/proxy)
    if res.status is not None and 400 <= res.status < 600:
        return 2  # some HTTP error — still reachable
    return 1  # connection/timeout/dns error


async def fetch_service_info(
    http: AsyncHttp,
    url: str,
    artifact: str | None = None,
    *,
    auth_headers: dict[str, str] | None = None,
    timeout: float | None = None,
) -> dict:
    """Try candidate service-info endpoints; return a structured, tolerant result.

    Returns a dict with keys: ``found`` (bool), ``service_info`` (dict|None),
    ``endpoint`` (the URL that worked), ``reported_type``/``reported_version``,
    ``attempts`` (per-candidate diagnostics), and ``warnings``.
    """
    candidates = service_info_candidates(url, artifact)
    attempts: list[dict[str, Any]] = []
    warnings: list[str] = []
    best: HttpResult | None = None

    for candidate in candidates:
        res = await http.get_json(candidate, headers=auth_headers, timeout=timeout)
        attempts.append(res.summary())
        if best is None or _rank(res) > _rank(best):
            best = res
        # Only accept a 200 that actually *looks like* a service-info document.
        if res.status == 200 and looks_like_service_info(res.json):
            si = res.json
            rtype = si.get("type") if isinstance(si.get("type"), dict) else {}
            return {
                "found": True,
                "endpoint": str(res.url),
                "service_info": si,
                "reported_type": rtype.get("artifact"),
                "reported_version": rtype.get("version") or si.get("version"),
                "reported_version_parsed": parse_version(rtype.get("version") or si.get("version")),
                "attempts": attempts,
                "warnings": warnings,
            }
        if res.status in (401, 403):
            break  # auth challenge — stop, it's the answer

    # Nothing returned a usable service-info. Summarize what we saw.
    status = best.status if best else None
    challenge = parse_www_authenticate(best.www_authenticate) if best else {}
    liveness = classify_liveness(status, best.error_kind if best else None)
    if status in (401, 403):
        warnings.append("service requires authentication for service-info")
    elif status == 404:
        liveness = "live_no_serviceinfo"
        warnings.append("reachable but no service-info at any known path (non-compliant or unusual layout)")
    elif status == 200:
        # Reachable, returned 200, but the body was not a valid service-info.
        liveness = "live_no_serviceinfo"
        warnings.append("endpoint returned HTTP 200 but the body was not a valid GA4GH service-info "
                        "(likely a web app, proxy or redirect — not a compliant service-info endpoint)")
    elif liveness == "unreachable":
        warnings.append(f"service unreachable: {best.error if best else 'unknown'}")

    return {
        "found": False,
        "endpoint": best.url if best else (candidates[0] if candidates else url),
        "service_info": None,
        "reported_type": None,
        "reported_version": None,
        "liveness": liveness,
        "auth_challenge": challenge or None,
        "attempts": attempts,
        "warnings": warnings,
    }


async def probe_liveness(
    http: AsyncHttp,
    url: str,
    artifact: str | None = None,
    *,
    auth_headers: dict[str, str] | None = None,
    timeout: float | None = None,
) -> dict:
    """Lightweight health/liveness probe of a service based on service-info."""
    info = await fetch_service_info(http, url, artifact, auth_headers=auth_headers, timeout=timeout)
    if info["found"]:
        si = info["service_info"] or {}
        first = info["attempts"][-1] if info["attempts"] else {}
        return {
            "reachable": True,
            "liveness": "live",
            "service_info_endpoint": info["endpoint"],
            "reported_version": info["reported_version"],
            "reported_version_parsed": info["reported_version_parsed"],
            "reported_artifact": info["reported_type"],
            "service_name": si.get("name"),
            "latency_ms": first.get("elapsed_ms"),
            "auth_required": False,
            "warnings": info["warnings"],
        }
    liveness = info.get("liveness", "unreachable")
    return {
        "reachable": liveness not in ("unreachable",),
        "liveness": liveness,
        "service_info_endpoint": info["endpoint"],
        "auth_required": liveness == "auth_required",
        "auth_challenge": info.get("auth_challenge"),
        "attempts": info["attempts"],
        "warnings": info["warnings"],
    }
