"""Live integration smoke tests against the REAL GA4GH Implementation Registry.

Skipped unless GA4GH_MCP_LIVE=1 (so the default suite stays hermetic + offline-safe).
Prints a pass/fail table so a human can eyeball real-world liveness/compliance.

    GA4GH_MCP_LIVE=1 pytest -q -s tests/test_live_integration.py
"""

from __future__ import annotations

import os

import pytest

from ga4gh_mcp.config import load_settings
from ga4gh_mcp.context import ServerContext
from ga4gh_mcp import tools

pytestmark = pytest.mark.skipif(
    not os.getenv("GA4GH_MCP_LIVE"),
    reason="set GA4GH_MCP_LIVE=1 to run live integration tests",
)


@pytest.fixture
async def live_ctx():
    c = ServerContext.create(load_settings())
    try:
        yield c
    finally:
        await c.aclose()


async def test_registry_loads(live_ctx):
    r = await tools.list_services(live_ctx, include_deployments=True, limit=1000)
    assert r["ok"] and r["count"] >= 30, "registry should return the full catalog"
    print(f"\n[live] registry returned {r['count']} implementations")


async def test_service_types_live(live_ctx):
    r = await tools.list_service_types(live_ctx)
    assert r["ok"]
    print(f"[live] service type counts: {r['data']['service_counts']}")


async def test_representative_health_matrix(live_ctx):
    """Probe a representative sample across every live service type; print pass/fail table."""
    listing = await tools.list_services(live_ctx, include_deployments=True, limit=1000)
    services = listing["data"]

    # one representative per product that has a serviceInfoUrl, up to 3 per product
    picked: list[dict] = []
    seen: dict[str, int] = {}
    for s in services:
        p = s.get("product") or "?"
        if s.get("has_service_info_url") and seen.get(p, 0) < 3:
            picked.append(s)
            seen[p] = seen.get(p, 0) + 1

    rows = []
    live_count = 0
    for s in picked:
        health = await tools.check_service_health(live_ctx, service_id=s["id"])
        data = health.get("data", {})
        liveness = data.get("liveness", "error")
        si = data.get("service_info") or {}
        ver = (si.get("version") or {})
        if liveness == "live":
            live_count += 1
        rows.append((s.get("product"), (s.get("name") or "")[:34], liveness,
                     str(data.get("http_status") or "-"),
                     str(ver.get("reported_type_version") or "-"),
                     str(ver.get("declared_version") or "-")))
        # never crashes: liveness is always a known class
        assert liveness in {
            "live", "auth_required", "http_error", "invalid_response", "timeout",
            "unreachable_dns", "tls_error", "connection_error", "no_service_info_url", "error"}

    print(f"\n{'PRODUCT':8}{'NAME':36}{'LIVENESS':18}{'HTTP':6}{'si.ver':10}{'declared'}")
    for r in rows:
        print(f"{r[0]:8}{r[1]:36}{r[2]:18}{r[3]:6}{r[4]:10}{r[5]}")
    print(f"\n[live] {live_count}/{len(rows)} probed services returned a compliant service-info")
    assert live_count >= 5, "expected several live+compliant services in the real registry"
