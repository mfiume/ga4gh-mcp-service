#!/usr/bin/env python3
"""Probe every registered serviceInfoUrl and (re)generate the compatibility matrix.

Uses the server's own RegistryClient + liveness logic, so this doubles as an end-to-end
check of the live-service handling. Writes docs/compatibility_probe.json and prints a table.

    python scripts/probe_registry.py
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from ga4gh_mcp.config import load_settings
from ga4gh_mcp.context import ServerContext
from ga4gh_mcp.liveness import check_liveness

ROOT = Path(__file__).resolve().parent.parent


async def main() -> int:
    ctx = ServerContext.create(load_settings())
    try:
        services = await ctx.registry.implementations(include_deployments=True)
        results = []
        # bounded concurrency
        sem = asyncio.Semaphore(16)

        async def probe(s):
            async with sem:
                rep = await check_liveness(ctx.http, s, ctx.resolver)
                return rep

        reports = await asyncio.gather(*(probe(s) for s in services))
        for rep in reports:
            results.append(rep.to_dict())

        out = ROOT / "docs" / "compatibility_probe.json"
        out.write_text(json.dumps(results, indent=2))

        counts: dict[str, int] = {}
        for r in results:
            counts[r["liveness"]] = counts.get(r["liveness"], 0) + 1

        print(f"probed {len(results)} implementations -> {out.relative_to(ROOT)}")
        print("liveness:", json.dumps(counts))
        print(f"\n{'PRODUCT':9}{'LIVENESS':18}{'HTTP':6}{'NAME'}")
        for r in sorted(results, key=lambda x: (x.get('product') or 'zz', x.get('name') or '')):
            print(f"{(r.get('product') or '?'):9}{r['liveness']:18}"
                  f"{str(r.get('http_status') or '-'):6}{(r.get('name') or '')[:44]}")
        return 0
    finally:
        await ctx.aclose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
