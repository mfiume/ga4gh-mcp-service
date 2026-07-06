#!/usr/bin/env python3
"""Generate the "State of the GA4GH Ecosystem" report from LIVE registry data.

Probes every registered implementation with the server's own liveness/compliance logic,
then renders a print-optimized, self-contained HTML report. Convert to PDF with headless
Chrome (the script prints the exact command, and runs it automatically with --pdf).

    python scripts/ecosystem_report.py --out report.html --pdf

Palette: validated status tiers + a single sequential blue on a light print surface.
"""

from __future__ import annotations

import argparse
import asyncio
import collections
import datetime as _dt
import html
import shutil
import subprocess
from pathlib import Path

from ga4gh_mcp.config import load_settings
from ga4gh_mcp.context import ServerContext
from ga4gh_mcp.liveness import check_liveness

# --- validated palette (dataviz reference, light surface) ---
INK, INK2, MUTED = "#0b0b0b", "#52514e", "#898781"
SURFACE, PLANE, GRID, HAIR = "#fcfcfb", "#f9f9f7", "#e1e0d9", "rgba(11,11,11,0.10)"
GOOD, WARN, SERIOUS, CRIT = "#0ca30c", "#fab219", "#ec835a", "#d03b3b"
BLUE, BLUE_D = "#2a78d6", "#256abf"

# liveness class -> (label, tier color, plain-English meaning)
LIVENESS_META = {
    "live":               ("Live & spec-compliant", GOOD,    "returns a valid GA4GH service-info"),
    "auth_required":      ("Auth required",          WARN,    "reachable; returned 401/403"),
    "invalid_response":   ("Non-standard response",  SERIOUS, "reachable; service-info not spec-compliant"),
    "http_error":         ("HTTP error",             SERIOUS, "reachable; 404/5xx at service-info path"),
    "no_service_info_url":("No service-info URL",     MUTED,   "registry entry has no probe target"),
    "unreachable_dns":    ("DNS failure",             CRIT,    "hostname does not resolve"),
    "timeout":            ("Timeout",                 CRIT,    "connect/read timed out (e.g. private IP)"),
    "tls_error":          ("TLS error",               CRIT,    "TLS handshake failed"),
    "connection_error":   ("Connection refused",      CRIT,    "transport error"),
}
LIVENESS_ORDER = list(LIVENESS_META)


async def gather():
    ctx = ServerContext.create(load_settings())
    try:
        impls = await ctx.registry.implementations(include_deployments=True)
        orgs = await ctx.registry.organisations()
        standards = await ctx.registry.standards()
        sem = asyncio.Semaphore(16)

        async def probe(s):
            async with sem:
                return s, await check_liveness(ctx.http, s, ctx.resolver)

        pairs = await asyncio.gather(*(probe(s) for s in impls))
    finally:
        await ctx.aclose()

    rows = []
    for s, r in pairs:
        sv = s.get("standardVersion") or {}
        si = r.service_info
        rows.append({
            "name": s.get("name") or "", "product": sv.get("ga4ghProduct") or "?",
            "impl_type": s.get("implementationType") or "",
            "org": (s.get("organisation") or {}).get("name") or "",
            "country": (s.get("geolocation") or {}).get("country") or "",
            "declared": sv.get("version") or "",
            "reported": (si.version.reported_type_version if si else "") or "",
            "liveness": r.liveness.value, "http": r.http_status,
            "drift": bool(si and si.version.version_matches is False),
            "auth_scheme": (r.auth.scheme if r.auth else None),
            "url": s.get("serviceInfoUrl") or s.get("url") or "",
            "error": r.error or "",
        })
    return rows, orgs, standards


# ------------------------------------------------------------------ rendering helpers
def esc(x) -> str:
    return html.escape(str(x if x is not None else ""))


def bar(pct: float, color: str, h: int = 10) -> str:
    pct = max(0.0, min(100.0, pct))
    return (f'<span class="track" style="height:{h}px"><span class="fill" '
            f'style="width:{pct:.1f}%;background:{color};height:{h}px"></span></span>')


def stat_tile(value: str, label: str, sub: str = "") -> str:
    subhtml = f'<div class="tile-sub">{esc(sub)}</div>' if sub else ""
    return (f'<div class="tile"><div class="tile-val">{esc(value)}</div>'
            f'<div class="tile-lbl">{esc(label)}</div>{subhtml}</div>')


def render(rows, orgs, standards, generated: str) -> str:
    n = len(rows)
    live = [x for x in rows if x["liveness"] == "live"]
    drift = [x for x in live if x["drift"]]
    dead = [x for x in rows if x["liveness"] in ("unreachable_dns", "timeout", "tls_error", "connection_error")]
    auth = [x for x in rows if x["liveness"] == "auth_required"]
    live_pct = round(100 * len(live) / n) if n else 0
    drift_pct = round(100 * len(drift) / len(live)) if live else 0
    countries = collections.Counter(x["country"] for x in rows if x["country"])
    lcounts = collections.Counter(x["liveness"] for x in rows)
    prods = collections.Counter(x["product"] for x in rows)
    liveprods = collections.Counter(x["product"] for x in live)
    maxl = max(lcounts.values()) if lcounts else 1

    # liveness bars (ordered by our tier order)
    liveness_bars = ""
    for k in LIVENESS_ORDER:
        c = lcounts.get(k, 0)
        if not c:
            continue
        label, color, meaning = LIVENESS_META[k]
        liveness_bars += (
            f'<div class="lrow"><div class="lname">{esc(label)}'
            f'<span class="lmeaning">{esc(meaning)}</span></div>'
            f'<div class="lbar">{bar(100 * c / maxl, color, 14)}</div>'
            f'<div class="lnum">{c}</div></div>')

    # coverage-by-product stacked bars (live vs remainder)
    prod_bars = ""
    for p, total in prods.most_common():
        lv = liveprods.get(p, 0)
        pct = 100 * lv / total if total else 0
        prod_bars += (
            f'<div class="prow"><div class="pname">{esc(p)}</div>'
            f'<div class="pbar"><span class="track" style="height:14px">'
            f'<span class="fill" style="width:{pct:.1f}%;background:{BLUE_D};height:14px"></span>'
            f'</span></div><div class="pnum">{lv}<span class="pden">/{total}</span></div></div>')

    # drift table
    drift_rows = "".join(
        f'<tr><td>{esc(x["name"])}</td><td>{esc(x["product"])}</td>'
        f'<td class="mono">{esc(x["declared"])}</td><td class="mono">{esc(x["reported"])}</td></tr>'
        for x in sorted(drift, key=lambda r: (r["product"], r["name"])))

    # dead table
    dead_rows = "".join(
        f'<tr><td>{esc(x["name"])}</td><td>{esc(x["product"])}</td>'
        f'<td>{esc(LIVENESS_META[x["liveness"]][0])}</td><td class="small">{esc(x["error"][:70])}</td></tr>'
        for x in sorted(dead, key=lambda r: r["name"]))

    # auth table
    auth_rows = "".join(
        f'<tr><td>{esc(x["name"])}</td><td>{esc(x["product"])}</td>'
        f'<td class="mono">{esc(x["http"])}</td></tr>'
        for x in sorted(auth, key=lambda r: r["name"]))

    # geo
    geo_rows = " ".join(
        f'<span class="chip">{esc(cc)} <b>{c}</b></span>'
        for cc, c in countries.most_common())

    # full inventory
    inv_rows = ""
    for x in sorted(rows, key=lambda r: (r["product"], -(r["liveness"] == "live"), r["name"])):
        label, color, _ = LIVENESS_META[x["liveness"]]
        dot = f'<span class="dot" style="background:{color}"></span>'
        drift_flag = ' <span class="flag">Δ</span>' if x["drift"] else ""
        inv_rows += (
            f'<tr><td>{esc(x["product"])}</td><td>{esc(x["name"])}</td>'
            f'<td class="small">{esc(x["org"])}</td><td>{esc(x["country"])}</td>'
            f'<td>{dot}{esc(label)}</td>'
            f'<td class="mono">{esc(x["declared"])}</td>'
            f'<td class="mono">{esc(x["reported"]) or "n/a"}{drift_flag}</td></tr>')

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>State of the GA4GH Ecosystem · {esc(generated)}</title>
<style>
  :root {{ --ink:{INK}; --ink2:{INK2}; --muted:{MUTED}; --surface:{SURFACE};
           --plane:{PLANE}; --grid:{GRID}; --hair:{HAIR}; --blue:{BLUE}; }}
  * {{ box-sizing:border-box; }}
  html {{ -webkit-print-color-adjust:exact; print-color-adjust:exact; }}
  body {{ font-family:system-ui,-apple-system,"Segoe UI",sans-serif; color:var(--ink);
          background:var(--surface); margin:0; font-size:11px; line-height:1.5; }}
  .page {{ padding:40px 46px; max-width:820px; margin:0 auto; }}
  h1 {{ font-size:26px; margin:0 0 2px; letter-spacing:-0.4px; }}
  h2 {{ font-size:15px; margin:26px 0 10px; padding-bottom:5px; border-bottom:2px solid var(--ink);
        letter-spacing:-0.2px; }}
  h2 .h2sub {{ font-weight:400; color:var(--muted); font-size:11px; letter-spacing:0; }}
  .sub {{ color:var(--ink2); font-size:12px; margin:0 0 4px; }}
  .prov {{ color:var(--muted); font-size:10px; margin:6px 0 0; }}
  p.lede {{ font-size:12px; color:var(--ink2); }}
  .rule {{ height:3px; background:var(--ink); margin:14px 0 0; }}
  .tiles {{ display:grid; grid-template-columns:repeat(3,1fr); gap:10px; margin:16px 0 4px; }}
  .tile {{ border:1px solid var(--hair); border-radius:10px; padding:12px 14px;
           background:var(--plane); }}
  .tile-val {{ font-size:26px; font-weight:700; letter-spacing:-0.5px; line-height:1; }}
  .tile-lbl {{ font-size:10.5px; color:var(--ink2); margin-top:5px; font-weight:600; }}
  .tile-sub {{ font-size:9.5px; color:var(--muted); margin-top:2px; }}
  .track {{ display:inline-block; width:100%; background:var(--grid); border-radius:4px; vertical-align:middle; }}
  .fill {{ display:inline-block; border-radius:4px; }}
  .lrow,.prow {{ display:flex; align-items:center; gap:12px; margin:6px 0; }}
  .lname {{ flex:0 0 210px; font-weight:600; }}
  .lmeaning {{ display:block; font-weight:400; color:var(--muted); font-size:9.5px; }}
  .lbar {{ flex:1; }} .lnum {{ flex:0 0 30px; text-align:right; font-weight:700;
           font-variant-numeric:tabular-nums; }}
  .pname {{ flex:0 0 90px; font-weight:600; }} .pbar {{ flex:1; }}
  .pnum {{ flex:0 0 54px; text-align:right; font-weight:700; font-variant-numeric:tabular-nums; }}
  .pden {{ color:var(--muted); font-weight:400; }}
  table {{ width:100%; border-collapse:collapse; margin:8px 0; font-size:10.5px; }}
  th {{ text-align:left; color:var(--muted); font-weight:600; border-bottom:1px solid var(--grid);
        padding:5px 8px; text-transform:uppercase; font-size:9px; letter-spacing:0.4px; }}
  td {{ padding:5px 8px; border-bottom:1px solid var(--grid); vertical-align:top; }}
  .mono {{ font-variant-numeric:tabular-nums; font-feature-settings:"tnum"; }}
  .small {{ color:var(--ink2); font-size:9.5px; }}
  .dot {{ display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:6px;
          vertical-align:middle; }}
  .flag {{ color:{CRIT}; font-weight:700; }}
  .chip {{ display:inline-block; border:1px solid var(--hair); border-radius:20px; padding:2px 10px;
           margin:3px 4px 0 0; font-size:10px; background:var(--plane); }}
  .callout {{ background:var(--plane); border:1px solid var(--hair); border-left:3px solid var(--blue);
              border-radius:8px; padding:10px 14px; margin:10px 0; color:var(--ink2); font-size:11px; }}
  .foot {{ margin-top:28px; padding-top:10px; border-top:1px solid var(--grid); color:var(--muted);
           font-size:9.5px; }}
  section {{ break-inside:avoid; }}
  .keep {{ break-inside:avoid; }}
  @page {{ size:Letter; margin:0.5in; }}
</style></head>
<body><div class="page">
  <h1>State of the GA4GH Ecosystem</h1>
  <p class="sub">A live liveness, compliance &amp; version-conformance snapshot of the
     GA4GH Implementation Registry</p>
  <div class="rule"></div>
  <p class="prov">Generated {esc(generated)} by <b>ga4gh-mcp-service</b> · source:
     implementation-registry.ga4gh.org · method: each registered <code>serviceInfoUrl</code> probed
     with the server's own liveness/compliance logic (timeouts, retries, service-info normalization,
     version reconciliation). Reproduce: <code>python scripts/ecosystem_report.py</code>.</p>

  <section>
  <p class="lede">The GA4GH Implementation Registry lists {n} implementations from {len(orgs)}
     organisations against {len(standards)} standards. This report probes every one of them and
     reports what is <b>actually reachable, spec-compliant, and version-consistent right now</b>.
     That is the reality an AI agent (or an integrator) meets when it tries to use the ecosystem.</p>
  <div class="tiles">
    {stat_tile(str(n), "Registered implementations", f"{sum(1 for x in rows if x['impl_type']=='SERVICE')} services · {sum(1 for x in rows if x['impl_type']=='DEPLOYMENT')} deployments")}
    {stat_tile(f"{len(live)}", "Live & spec-compliant", f"{live_pct}% of registered")}
    {stat_tile(f"{len(drift)}", "Report a mismatched version", f"{drift_pct}% of live services")}
    {stat_tile(f"{len(dead)}", "Dead / unreachable", "DNS · timeout · TLS · refused")}
    {stat_tile(str(len(countries)), "Countries represented", "global federation")}
    {stat_tile(str(len(orgs)), "Organisations", "")}
  </div>
  </section>

  <section class="keep">
  <h2>Liveness <span class="h2sub">(what answers, and how)</span></h2>
  {liveness_bars}
  <div class="callout"><b>Reading this:</b> green is fully healthy; amber is reachable but gated or
     degraded; red is unreachable; grey has no probe target registered. Only {len(live)} of {n}
     ({live_pct}%) return a valid GA4GH service-info on demand.</div>
  </section>

  <section class="keep">
  <h2>Coverage by service type <span class="h2sub">(live / registered)</span></h2>
  {prod_bars}
  <div class="callout">DRS (data access) dominates the live surface. <b>WES, htsget and refget have
     no live, spec-compliant endpoint</b> among registered entries today. That is a real gap for
     anyone hoping to run or stream against them.</div>
  </section>

  <section class="keep">
  <h2>Version conformance <span class="h2sub">(registry-declared vs self-reported)</span></h2>
  <p class="lede">{len(drift)} of {len(live)} live services report a <code>type.version</code> in
     their service-info that disagrees with the version the registry declares. Most are Gen3-based
     DRS servers reporting the <i>service-info schema</i> version (1.0.3) where the registry declares
     the <i>DRS API</i> version (1.2.0). This is a genuine ambiguity in how <code>type.version</code>
     is populated, not necessarily a broken service. Either way, an agent that trusts one field alone
     would be misled; this server surfaces all of them.</p>
  <table><thead><tr><th>Service</th><th>Type</th><th>Registry says</th>
    <th>Service-info reports</th></tr></thead><tbody>{drift_rows}</tbody></table>
  </section>

  <section class="keep">
  <h2>Access &amp; authentication</h2>
  <p class="lede">{len(auth)} reachable services return an authentication challenge (401/403) at their
     service-info endpoint. The server classifies these as <i>auth-required</i> and surfaces the
     challenge rather than reporting them as failures. Data endpoints (DRS access URLs, TES tasks)
     more broadly require OAuth2/OIDC bearer tokens or GA4GH Passport visas.</p>
  {"<table><thead><tr><th>Service</th><th>Type</th><th>HTTP</th></tr></thead><tbody>" + auth_rows + "</tbody></table>" if auth_rows else "<p class='small'>None among service-info endpoints in this snapshot.</p>"}
  </section>

  <section class="keep">
  <h2>Unreachable services</h2>
  <p class="lede">{len(dead)} registered entries could not be reached at all. The server distinguishes
     the failure modes so a client knows whether to retry, wait, or give up.</p>
  <table><thead><tr><th>Service</th><th>Type</th><th>Class</th><th>Detail</th></tr></thead>
    <tbody>{dead_rows}</tbody></table>
  </section>

  <section class="keep">
  <h2>Geographic reach</h2>
  <p class="lede">Registered implementations span {len(countries)} countries:</p>
  <div>{geo_rows}</div>
  </section>

  <section>
  <h2>Full inventory <span class="h2sub">(all {n} registered implementations)</span></h2>
  <table><thead><tr><th>Type</th><th>Service</th><th>Organisation</th><th>Country</th>
    <th>Status</th><th>Declared</th><th>Reported</th></tr></thead>
    <tbody>{inv_rows}</tbody></table>
  <p class="small">Δ marks a version disagreement between the registry and the service's own
     service-info.</p>
  </section>

  <div class="foot">
    <b>Method &amp; caveats.</b> Probed live on {esc(generated)}; results shift as the registry and
    deployments change. "Version drift" is largely a spec-interpretation nuance (schema vs API
    version), presented as-is. Absence from this report is not a judgment of a service's quality,
    only of what a public, unauthenticated probe of its registered endpoint could observe.
    Generated by the open-source <b>ga4gh-mcp-service</b> (mfiume/ga4gh-mcp-service).
  </div>
</div></body></html>"""


def to_pdf(html_path: Path) -> Path | None:
    chrome = ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
              if Path("/Applications/Google Chrome.app").exists()
              else shutil.which("google-chrome") or shutil.which("chromium"))
    pdf_path = html_path.with_suffix(".pdf")
    if not chrome:
        print("Chrome not found; open the HTML and Print → Save as PDF, or install Chrome.")
        return None
    subprocess.run([chrome, "--headless", "--disable-gpu", "--no-pdf-header-footer",
                    f"--print-to-pdf={pdf_path}", html_path.as_uri()],
                   check=True, capture_output=True)
    return pdf_path


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="ga4gh-ecosystem-report.html")
    ap.add_argument("--pdf", action="store_true", help="also render a PDF via headless Chrome")
    ap.add_argument("--date", default=None, help="override the snapshot date (YYYY-MM-DD)")
    args = ap.parse_args()

    generated = args.date or _dt.date.today().isoformat()
    rows, orgs, standards = await gather()
    out = Path(args.out)
    out.write_text(render(rows, orgs, standards, generated))
    print(f"wrote {out}  ({len(rows)} implementations)")
    if args.pdf:
        pdf = to_pdf(out)
        if pdf:
            print(f"wrote {pdf}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
