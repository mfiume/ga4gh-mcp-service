#!/usr/bin/env python3
"""Empirical probe of the GA4GH Implementation Registry and every registered service.

Fetches /services and /implementations from https://registry.ga4gh.org/v1, then for
each *service* (live deployment) probes candidate service-info endpoints to record:
  - liveness (HTTP status / connection error class)
  - reported spec version (from the returned service-info, if any)
  - auth challenge (WWW-Authenticate header on 401/403)
  - content-type / whether valid JSON

Writes raw results to docs/compatibility-raw.json and prints a summary matrix.
Pure stdlib (urllib) so it runs anywhere with no deps.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

REGISTRY = "https://registry.ga4gh.org/v1"
TIMEOUT = 8
WORKERS = 12

# Candidate service-info paths by artifact. service-info 1.0 standardizes {url}/service-info,
# but older DRS/TRS/WES deployments nest under a versioned prefix.
CANDIDATE_PATHS = {
    "drs": ["/service-info", "/ga4gh/drs/v1/service-info"],
    "trs": ["/service-info", "/ga4gh/trs/v2/service-info"],
    "wes": ["/service-info", "/ga4gh/wes/v1/service-info"],
    "tes": ["/service-info", "/ga4gh/tes/v1/service-info"],
    "htsget": ["/service-info", "/ga4gh/htsget/v1/service-info", "/reads/service-info"],
    "refget": ["/service-info", "/sequence/service-info"],
    "rnaget": ["/service-info"],
    "beacon": ["/service-info", "/info"],
    "search": ["/service-info"],
    "service-registry": ["/service-info"],
    "_default": ["/service-info"],
}


def fetch_json(url: str, timeout: int = 20):
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "ga4gh-probe/0.2"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def probe_one(base_url: str, artifact: str):
    """Try candidate service-info paths; return the first informative result."""
    paths = CANDIDATE_PATHS.get(artifact, CANDIDATE_PATHS["_default"])
    attempts = []
    base = base_url.rstrip("/")
    for p in paths:
        url = base + p
        rec = {"url": url, "status": None, "error": None, "www_authenticate": None,
               "content_type": None, "reported_type": None, "reported_version": None, "json_ok": False}
        req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "ga4gh-probe/0.2"})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                rec["status"] = r.status
                rec["content_type"] = r.headers.get("content-type", "")
                body = r.read().decode("utf-8", "replace")
                try:
                    data = json.loads(body)
                    rec["json_ok"] = True
                    t = data.get("type") if isinstance(data, dict) else None
                    if isinstance(t, dict):
                        rec["reported_type"] = t.get("artifact")
                        rec["reported_version"] = t.get("version")
                    rec["service_version"] = data.get("version") if isinstance(data, dict) else None
                except Exception:
                    pass
        except urllib.error.HTTPError as e:
            rec["status"] = e.code
            rec["www_authenticate"] = e.headers.get("WWW-Authenticate")
            rec["content_type"] = e.headers.get("content-type", "")
        except Exception as e:
            rec["error"] = f"{type(e).__name__}: {e}"[:120]
        attempts.append(rec)
        # Stop early on a clearly informative outcome
        if rec["status"] in (200, 401, 403):
            break
    # pick the "best" attempt: prefer 200, then 401/403, then any status, then error
    def score(r):
        if r["status"] == 200:
            return 3
        if r["status"] in (401, 403):
            return 2
        if r["status"] is not None:
            return 1
        return 0
    best = max(attempts, key=score)
    return best, attempts


def classify(svc, best):
    """Human-readable liveness/auth verdict."""
    st = best["status"]
    if st == 200:
        return "LIVE"
    if st in (401, 403):
        return "AUTH_REQUIRED"
    if st is None:
        return "UNREACHABLE"
    if st == 404:
        return "LIVE_NO_SERVICEINFO"
    if 500 <= st < 600:
        return "SERVER_ERROR"
    return f"HTTP_{st}"


def main():
    services = fetch_json(f"{REGISTRY}/services")
    implementations = fetch_json(f"{REGISTRY}/implementations")
    types = fetch_json(f"{REGISTRY}/services/types")

    print(f"Registry: {len(services)} services, {len(implementations)} implementations, "
          f"{len(types)} distinct service types\n")

    results = []
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {}
        for svc in services:
            url = svc.get("url")
            artifact = (svc.get("type") or {}).get("artifact", "_default")
            if not url:
                results.append({"svc": svc, "best": {"status": None, "error": "no url"},
                                "verdict": "NO_URL", "attempts": []})
                continue
            futs[ex.submit(probe_one, url, artifact)] = svc
        for fut in as_completed(futs):
            svc = futs[fut]
            try:
                best, attempts = fut.result()
            except Exception as e:
                best, attempts = {"status": None, "error": str(e)}, []
            results.append({"svc": svc, "best": best, "verdict": classify(svc, best), "attempts": attempts})

    # Sort by artifact then name for stable output
    results.sort(key=lambda r: ((r["svc"].get("type") or {}).get("artifact", ""), r["svc"].get("name", "")))

    raw = {
        "registry": REGISTRY,
        "counts": {"services": len(services), "implementations": len(implementations), "types": len(types)},
        "service_types": types,
        "services_probe": results,
        "implementations": implementations,
    }
    with open("docs/compatibility-raw.json", "w") as f:
        json.dump(raw, f, indent=2, default=str)

    # Summary matrix
    print(f"{'ARTIFACT':<16}{'VERDICT':<20}{'VER(reg)':<12}{'ENV':<12}{'NAME':<34}URL")
    print("-" * 140)
    verdict_counts = {}
    type_counts = {}
    for r in results:
        svc = r["svc"]
        t = (svc.get("type") or {})
        art = t.get("artifact", "?")
        ver = t.get("version", "?")
        env = svc.get("environment", "?")
        name = (svc.get("name") or "")[:32]
        url = svc.get("url", "")
        v = r["verdict"]
        verdict_counts[v] = verdict_counts.get(v, 0) + 1
        type_counts[art] = type_counts.get(art, 0) + 1
        auth = ""
        if r["best"].get("www_authenticate"):
            auth = f"  WWW-Auth: {r['best']['www_authenticate'][:50]}"
        print(f"{art:<16}{v:<20}{ver:<12}{env:<12}{name:<34}{url}{auth}")

    print("\n=== Verdict counts ===")
    for k, v in sorted(verdict_counts.items(), key=lambda x: -x[1]):
        print(f"  {k:<22}{v}")
    print("\n=== Service type counts (live services) ===")
    for k, v in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"  {k:<22}{v}")
    print("\nRaw results -> docs/compatibility-raw.json")


if __name__ == "__main__":
    main()
