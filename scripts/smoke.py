#!/usr/bin/env python3
"""End-to-end smoke test: spawn the server over stdio AND HTTP via the real MCP SDK client,
list tools, and exercise the registry tools. This is the non-interactive MCP-Inspector
equivalent — a true client<->server round trip over each transport.

    python scripts/smoke.py

Exit code 0 = both transports round-trip and all tools load. Registry reachability is
reported separately (so this still passes offline; tool calls just return clean error
envelopes instead of data).
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import socket
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client

EXPECTED_TOOLS = 18
PASS, FAIL, WARN = "\033[32mok\033[0m", "\033[31mFAIL\033[0m", "\033[33mwarn\033[0m"


def _envelope(result):
    if getattr(result, "structuredContent", None):
        return result.structuredContent
    for block in getattr(result, "content", []) or []:
        text = getattr(block, "text", None)
        if text:
            import json
            with contextlib.suppress(Exception):
                return json.loads(text)
    return None


async def _exercise(session: ClientSession, label: str, registry_ok: list[bool]) -> bool:
    ok = True
    await session.initialize()
    tools = (await session.list_tools()).tools
    names = [t.name for t in tools]
    print(f"[{label}] list_tools: {len(names)} tools "
          f"({PASS if len(names) == EXPECTED_TOOLS else FAIL})")
    if len(names) != EXPECTED_TOOLS:
        ok = False

    # every tool must carry a description + schema (schema-load check)
    bad = [t.name for t in tools if not t.description or not isinstance(t.inputSchema, dict)]
    print(f"[{label}] tool schemas valid: {PASS if not bad else FAIL} "
          f"{('missing: ' + ', '.join(bad)) if bad else ''}")
    ok = ok and not bad

    # ---- exercise registry tools end-to-end ----
    types = _envelope(await session.call_tool("list_service_types", {}))
    reachable = bool(types and types.get("ok"))
    registry_ok.append(reachable)
    if reachable:
        counts = types["data"]["service_counts"]
        print(f"[{label}] list_service_types: {PASS} counts={counts}")
    else:
        print(f"[{label}] list_service_types: {WARN} registry unreachable "
              f"(envelope: {types and types.get('error', {}).get('type')})")

    listing = _envelope(await session.call_tool(
        "list_services", {"product": "DRS", "limit": 5}))
    if listing is None or "ok" not in listing:
        print(f"[{label}] list_services: {FAIL} (no well-formed envelope)")
        ok = False
    elif listing["ok"]:
        print(f"[{label}] list_services(product=DRS): {PASS} {listing['count']} services")
        if listing["data"]:
            sid = listing["data"][0]["id"]
            got = _envelope(await session.call_tool("get_service", {"service_id": sid}))
            print(f"[{label}] get_service({sid[:12]}…): "
                  f"{PASS if got and got.get('ok') else FAIL}")
            health = _envelope(await session.call_tool(
                "check_service_health", {"service_id": sid}))
            liveness = (health or {}).get("data", {}).get("liveness", "?")
            print(f"[{label}] check_service_health: liveness={liveness} "
                  f"({PASS if health and health.get('ok') else FAIL})")
            ok = ok and bool(got and got.get("ok")) and bool(health and health.get("ok"))
    else:
        print(f"[{label}] list_services: {WARN} registry unreachable "
              f"(round-trip ok, clean error envelope)")

    # search round-trip (envelope well-formed either way)
    search = _envelope(await session.call_tool("search_services", {"query": "drs"}))
    print(f"[{label}] search_services: {PASS if search and 'ok' in search else FAIL}")
    ok = ok and bool(search and "ok" in search)
    return ok


async def smoke_stdio() -> tuple[bool, list[bool]]:
    print("\n=== STDIO transport ===")
    registry_ok: list[bool] = []
    params = StdioServerParameters(command=sys.executable, args=["-m", "ga4gh_mcp"],
                                   env=os.environ.copy())
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            ok = await _exercise(session, "stdio", registry_ok)
    return ok, registry_ok


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def _wait_port(host: str, port: int, timeout: float = 15.0) -> bool:
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        try:
            r, w = await asyncio.open_connection(host, port)
            w.close()
            with contextlib.suppress(Exception):
                await w.wait_closed()
            return True
        except OSError:
            await asyncio.sleep(0.2)
    return False


async def smoke_http() -> tuple[bool, list[bool]]:
    print("\n=== STREAMABLE-HTTP transport ===")
    registry_ok: list[bool] = []
    host, port, path = "127.0.0.1", _free_port(), "/mcp"
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "ga4gh_mcp", "--transport", "streamable-http",
        "--host", host, "--port", str(port), "--path", path,
        env=os.environ.copy(), stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL)
    try:
        if not await _wait_port(host, port):
            print(f"[http] server did not start on {host}:{port} {FAIL}")
            return False, registry_ok
        url = f"http://{host}:{port}{path}"
        async with streamablehttp_client(url) as (read, write, _get_session_id):
            async with ClientSession(read, write) as session:
                ok = await _exercise(session, "http", registry_ok)
        return ok, registry_ok
    finally:
        proc.terminate()
        with contextlib.suppress(Exception):
            await asyncio.wait_for(proc.wait(), timeout=5)


async def main() -> int:
    stdio_ok, stdio_reg = await smoke_stdio()
    http_ok, http_reg = await smoke_http()

    registry_reachable = any(stdio_reg + http_reg)
    all_ok = stdio_ok and http_ok
    print("\n" + "=" * 56)
    print(f"stdio transport:   {PASS if stdio_ok else FAIL}")
    print(f"http transport:    {PASS if http_ok else FAIL}")
    print(f"registry reachable: {'yes' if registry_reachable else 'no (offline — tool round-trips still verified)'}")
    if all_ok:
        print(f"\n[smoke] ALL CHECKS PASSED (tools={EXPECTED_TOOLS})")
        return 0
    print("\n[smoke] FAILURES DETECTED")
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
