"""CLI entry point.

Usage:
  ga4gh-mcp serve [--transport stdio|http] [--host H] [--port P]   # run the server
  ga4gh-mcp tools [--json]                                          # list tools (headless)
  ga4gh-mcp call <tool> [--arg k=v ...] [--json '{...}']            # invoke a tool (headless)
  ga4gh-mcp auth login <service> [--artifact A]                     # device-code login
  ga4gh-mcp auth status [service]
  ga4gh-mcp auth revoke [service]

With no subcommand, ``serve`` is used with the transport from GA4GH_MCP_TRANSPORT.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from .config import load_settings
from .server import build_server, configure_logging


def _parse_args_kv(pairs: list[str]) -> dict:
    out: dict = {}
    for p in pairs or []:
        if "=" not in p:
            raise SystemExit(f"--arg must be key=value, got: {p}")
        k, v = p.split("=", 1)
        try:
            out[k] = json.loads(v)  # allow numbers/booleans/json
        except json.JSONDecodeError:
            out[k] = v
    return out


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))


def cmd_serve(args) -> None:
    settings = load_settings()
    if args.transport:
        settings.transport = args.transport
    if args.host:
        settings.host = args.host
    if args.port:
        settings.port = args.port
    configure_logging(settings.log_level)
    mcp, _ctx = build_server(settings)
    transport = settings.normalized_transport()
    print(f"[ga4gh-mcp] starting transport={transport} "
          f"{'(' + settings.host + ':' + str(settings.port) + ')' if transport != 'stdio' else ''}",
          file=sys.stderr)
    mcp.run(transport=transport)


async def _list_tools(as_json: bool) -> None:
    mcp, ctx = build_server()
    try:
        tools = await mcp.list_tools()
        if as_json:
            _print([{"name": t.name, "description": t.description,
                     "input_schema": t.inputSchema} for t in tools])
        else:
            print(f"{len(tools)} tools:\n")
            for t in tools:
                desc = (t.description or "").strip().split("\n")[0]
                print(f"  {t.name:<28} {desc}")
    finally:
        await ctx.aclose()


async def _call_tool(name: str, arguments: dict) -> None:
    mcp, ctx = build_server()
    try:
        result = await mcp.call_tool(name, arguments)
        # FastMCP.call_tool returns (content_list, raw_result) in recent versions,
        # or just content_list in older ones. Normalize to the structured payload.
        raw = None
        if isinstance(result, tuple) and len(result) == 2:
            _content, raw = result
        else:
            _content = result
        if raw is not None:
            _print(raw)
        else:
            for item in _content:
                text = getattr(item, "text", None)
                if text is not None:
                    try:
                        _print(json.loads(text))
                    except Exception:  # noqa: BLE001
                        print(text)
                else:
                    _print(item)
    finally:
        await ctx.aclose()


async def _auth(args) -> None:
    mcp, ctx = build_server()
    try:
        if args.auth_cmd == "status":
            url = None
            if args.service:
                url = (await ctx.resolve(args.service)).url
            _print(ctx.auth.status(url))
        elif args.auth_cmd == "revoke":
            target = (await ctx.resolve(args.service)).url if args.service else None
            _print({"revoked": ctx.auth.revoke(target)})
        elif args.auth_cmd == "login":
            resolved = await ctx.resolve(args.service, args.artifact)
            begin = await ctx.auth.begin_device_code(resolved.url, resolved.artifact)
            print(f"\nTo authenticate to {begin['host']}:")
            print(f"  1. Open: {begin.get('verification_uri_complete') or begin.get('verification_uri')}")
            print(f"  2. Enter code: {begin.get('user_code')}\n")
            print("Waiting for authorization...", file=sys.stderr)
            token = await ctx.auth.poll_device_code(
                resolved.url, begin["device_code"],
                interval=begin.get("interval", 5),
                timeout=float(begin.get("expires_in", 300) or 300),
                artifact=resolved.artifact,
            )
            _print({"status": "authenticated", **token})
    finally:
        await ctx.aclose()


def main() -> None:
    parser = argparse.ArgumentParser(prog="ga4gh-mcp", description="Universal GA4GH MCP service")
    sub = parser.add_subparsers(dest="cmd")

    p_serve = sub.add_parser("serve", help="Run the MCP server")
    p_serve.add_argument("--transport", choices=["stdio", "http", "streamable-http", "sse"])
    p_serve.add_argument("--host")
    p_serve.add_argument("--port", type=int)

    p_tools = sub.add_parser("tools", help="List available tools")
    p_tools.add_argument("--json", action="store_true")

    p_call = sub.add_parser("call", help="Invoke a tool and print JSON")
    p_call.add_argument("tool")
    p_call.add_argument("--arg", action="append", default=[], help="key=value (value may be JSON)")
    p_call.add_argument("--json", dest="json_args", help="full arguments as a JSON object")

    p_auth = sub.add_parser("auth", help="Manage authentication")
    p_auth.add_argument("auth_cmd", choices=["login", "status", "revoke"])
    p_auth.add_argument("service", nargs="?")
    p_auth.add_argument("--artifact")

    args = parser.parse_args()

    if args.cmd in (None, "serve"):
        if args.cmd is None:
            args = parser.parse_args(["serve"])
        cmd_serve(args)
    elif args.cmd == "tools":
        asyncio.run(_list_tools(args.json))
    elif args.cmd == "call":
        arguments = json.loads(args.json_args) if args.json_args else _parse_args_kv(args.arg)
        asyncio.run(_call_tool(args.tool, arguments))
    elif args.cmd == "auth":
        asyncio.run(_auth(args))


if __name__ == "__main__":
    main()
