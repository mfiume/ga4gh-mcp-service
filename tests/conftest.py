"""Shared test fixtures: registry data + a ready-to-use ServerContext."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ga4gh_mcp.config import load_settings
from ga4gh_mcp.context import ServerContext

FIXTURES = Path(__file__).parent / "fixtures"
REGISTRY_BASE = "https://registry.test/api"


def _load(name: str) -> list[dict[str, Any]]:
    return json.loads((FIXTURES / "registry" / f"{name}.json").read_text())


@pytest.fixture
def registry_data() -> dict[str, list[dict[str, Any]]]:
    return {n: _load(n) for n in ("services", "deployments", "organisations", "standards")}


@pytest.fixture
def settings():
    # Fast + deterministic for tests.
    return load_settings(
        registry_base_url=REGISTRY_BASE,
        max_retries=1,
        retry_backoff=0.0,
        connect_timeout=2.0,
        read_timeout=2.0,
        auth_config=None,
        bearer_token=None,
    )


@pytest.fixture
async def ctx(settings, registry_data):
    """A ServerContext with the registry cache pre-populated (no registry HTTP needed)."""
    c = ServerContext.create(settings)
    for name, data in registry_data.items():
        c.registry._cache.set(name, data)
    try:
        yield c
    finally:
        await c.aclose()


def find_service(registry_data, product: str) -> dict[str, Any]:
    for s in registry_data["services"]:
        if (s.get("standardVersion") or {}).get("ga4ghProduct") == product and s.get("serviceInfoUrl"):
            return s
    raise AssertionError(f"no fixture service for {product}")
