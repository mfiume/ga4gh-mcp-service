# PROGRESS LOG

Running log of work on `ga4gh-mcp-service`. Newest at bottom.

## 2026-07-05

- **Recon.** Scanned `mfiume` GitHub + local repos. `omics-ai-mcp-server` chosen as
  the pattern template (tolerant HTTP client, OAuth device-code, dual transport,
  respx tests, packaging). No prior `ga4gh-mcp-service`.
- **Registry reverse-engineered.** Frontend is a SPA; real API is
  `https://registry.ga4gh.org/v1` with `/service-info`, `/services` (36),
  `/implementations` (3), `/services/types` (13). Spec repo `ga4gh/ga4gh-registry`.
- **Empirical probe of all 36 services** (`scripts/probe_registry.py`). Discovered the
  key nuances that drive the design: inconsistent base URLs (DRS `/objects/`),
  version drift, SPA false-positives, unreachable/private hosts, `401 Bearer` auth
  challenges (Terra) vs public (NCI-CRDC). Types present: drs/wes/trs/rnaget/search/service-registry.
- **⚠ Disk-full incident.** During first `uv pip install`, the machine's APFS container
  hit 100% (`ENOSPC` on every write, incl. harness scratch — lost observability).
  Ruled out snapshots/caches; recovered by clearing this session's `/private/tmp`
  output files + system logs/diagnostics (with user's sudo). Root cause: Data volume
  genuinely ~419/460 GB full; freed ~9 GB headroom. Resumed. (Details in chat.)
- **Implemented v1.** Foundational modules (config/http/cache/errors/normalize/models),
  registry client, generic service-info+probe, auth layer (manager/discovery/store),
  typed clients (DRS/TRS/WES) + plugin registry, 23 MCP tools, FastMCP server with
  dual transport + `/healthz`, and a headless CLI (`serve|tools|call|auth`).
- **Fixed 2 real robustness bugs found via live testing:**
  1. SPA/redirect 200s were falsely "live" → added `looks_like_service_info()` guard →
     honest `live_no_serviceinfo`.
  2. `auth_discover` probed the un-prefixed base → missed DRS 401s → extracted
     `api_base_url()` (adds `/ga4gh/drs/v1`) and used it in discovery.
- **Verified live (headless):** registry list/types/search/health, DRS auth-required &
  not-found & unreachable, URL normalization (bloodpac), Dockstore TRS list, Terra auth discovery.
- **Tests:** 46 unit pass, 3 live skipped; `scripts/smoke.py` 15/15 across stdio + HTTP.
- **Compat matrix generated** with the server's own logic: 24 live / 5 no-service-info /
  6 unreachable / 1 server-error → `docs/compatibility.md`.
- **Docs + packaging:** PLAN.md, README, `docs/clients/*` (Desktop/Code/Vertex/Bedrock),
  `docs/auth.md`, config example, Dockerfile, docker-compose.
- **Next:** commit + push to `mfiume/ga4gh-mcp-service`.

## 2026-07-05 (cont.)

- Lint clean (ruff), 46 unit tests pass, smoke 15/15.
- **Pushed to https://github.com/mfiume/ga4gh-mcp-service** (public, branch `main`).
- v1 Definition of Done fully met.
