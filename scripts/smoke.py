#!/usr/bin/env python3
"""End-to-end smoke test for the GA4GH MCP service (CLI, no UI required).

Verifies BOTH transports with a real MCP client handshake:

  * stdio            — spawns `ga4gh-mcp serve --transport stdio` and connects.
  * streamable HTTP  — spawns `ga4gh-mcp serve --transport http` and connects,
                       plus checks the /healthz route.

For each transport it initializes a session, lists tools, and calls a couple of
registry tools against the LIVE registry. Prints a PASS/FAIL summary and exits
non-zero on any failure.

Usage:
    python scripts/smoke.py [--http-only | --stdio-only] [--port 8791]
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

try:
    from mcp.client.streamable_http import streamablehttp_client
except Exception:  # noqa: BLE001
    streamablehttp_client = None

PY = sys.executable
EXPECTED_MIN_TOOLS = 20
results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {name}{(' — ' + detail) if detail else ''}")


async def _exercise(session: ClientSession, transport: str) -> None:
    await session.initialize()
    record(f"{transport}: initialize", True)

    tools = (await session.list_tools()).tools
    names = {t.name for t in tools}
    record(f"{transport}: list_tools ({len(tools)})", len(tools) >= EXPECTED_MIN_TOOLS,
           f"{len(tools)} tools")
    for required in ("registry_list_services", "drs_get_object", "auth_discover"):
        record(f"{transport}: has {required}", required in names)

    res = await session.call_tool("registry_list_service_types", {})
    text = res.content[0].text if res.content else ""
    record(f"{transport}: call registry_list_service_types",
           '"ok": true' in text and "drs" in text, "returned live types")

    res = await session.call_tool("registry_list_services", {"artifact": "wes", "limit": 3})
    text = res.content[0].text if res.content else ""
    record(f"{transport}: call registry_list_services(wes)", '"ok": true' in text and "wes" in text)


async def test_stdio() -> None:
    print("\n== stdio transport ==")
    params = StdioServerParameters(
        command=PY, args=["-m", "ga4gh_mcp", "serve", "--transport", "stdio"],
        env={**os.environ, "GA4GH_MCP_LOG_LEVEL": "WARNING"},
    )
    try:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await asyncio.wait_for(_exercise(session, "stdio"), timeout=90)
    except Exception as e:  # noqa: BLE001
        record("stdio: session", False, f"{type(e).__name__}: {e}")


async def _wait_healthz(url: str, tries: int = 40) -> bool:
    import httpx

    async with httpx.AsyncClient() as client:
        for _ in range(tries):
            try:
                r = await client.get(url, timeout=2)
                if r.status_code == 200:
                    return True
            except Exception:  # noqa: BLE001
                pass
            await asyncio.sleep(0.25)
    return False


async def test_http(port: int) -> None:
    print("\n== streamable HTTP transport ==")
    if streamablehttp_client is None:
        record("http: client import", False, "streamablehttp_client unavailable")
        return
    env = {**os.environ, "GA4GH_MCP_LOG_LEVEL": "WARNING",
           "GA4GH_MCP_TRANSPORT": "http", "GA4GH_MCP_PORT": str(port),
           "GA4GH_MCP_HOST": "127.0.0.1"}
    proc = await asyncio.create_subprocess_exec(
        PY, "-m", "ga4gh_mcp", "serve", env=env,
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        healthy = await _wait_healthz(f"http://127.0.0.1:{port}/healthz")
        record("http: /healthz", healthy)
        if not healthy:
            return
        async with streamablehttp_client(f"http://127.0.0.1:{port}/mcp") as (read, write, _):
            async with ClientSession(read, write) as session:
                await asyncio.wait_for(_exercise(session, "http"), timeout=90)
    except Exception as e:  # noqa: BLE001
        record("http: session", False, f"{type(e).__name__}: {e}")
    finally:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            proc.kill()


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--http-only", action="store_true")
    ap.add_argument("--stdio-only", action="store_true")
    ap.add_argument("--port", type=int, default=8791)
    args = ap.parse_args()

    print("GA4GH MCP service — smoke test")
    if not args.http_only:
        await test_stdio()
    if not args.stdio_only:
        await test_http(args.port)

    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print(f"\nSummary: {passed}/{total} checks passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
