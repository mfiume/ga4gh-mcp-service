# ga4gh-mcp-service — PLAN

A universal **MCP server for GA4GH services**. v1 capability: list & access services in the
[GA4GH Implementation Registry](https://implementation-registry.ga4gh.org/), built to tolerate the
real-world variance in liveness, spec compliance, and version across registered implementations.

- **Repo:** `mfiume/ga4gh-mcp-service`
- **Stack:** Python ≥3.10, official MCP Python SDK (`mcp` 1.28.1), `httpx`, `pydantic`.
- **Transports:** `stdio` (Claude Desktop/Code) and `streamable-http` (Vertex, Bedrock, remote).
- **Status:** 🟢 shipping — see Progress log at bottom.

---

## Phase 0 — Prior work reviewed

Scanned `mfiume/*`. Relevant repos: `omics-ai-mcp` (JS MCP server), `omics-ai-python-library`
(Python client), plus GA4GH `search`, `data-object-schemas` (DRS protos), `beacon-network`.

**Carried over (patterns, not code):**
- Exception taxonomy (`AuthenticationError`/`NetworkError`/`ValidationError`) and 401/403→auth mapping.
- Tool-design conventions: stateless tools, structured/markdown-friendly results, catch-and-return
  errors rather than throwing to crash the transport.
- Sane HTTP defaults (timeout, bounded polling) awareness.

**Explicitly NOT reused** (confirmed absent in prior repos): OAuth2/device-code/client-credentials,
GA4GH Passport, service-info parsing, version detection, DRS/service-registry clients, retries,
caching. All of these are **net-new** here.

## Phase 1 — Registry research (DONE, empirical)

Full findings in [`docs/compatibility.md`](docs/compatibility.md). Highlights:
- Registry API is public JSON at `/api` with `/services`, `/deployments`, `/organisations`,
  `/standards`, `/service-info`. **No server-side filtering, no OpenAPI, detail-by-UUID only.**
- 40 services (25 DRS, 8 TES, 4 TRS, 1 each Beacon/WES/htsget) + 6 deployments; 11 known standards.
- Probed all 46 `serviceInfoUrl`s: **21 live+valid, 5 live+nonstandard, 13 no-url, 2 http-error,
  3 dns-fail, 1 timeout, 1 tls-error.**
- **Load-bearing insight:** `type.version` in service-info ≠ the API spec version (Gen3 DRS reports
  `1.0.3` while declared `1.2.0`; Terra "Jade" returns non-compliant `0.0.1`; TESK reports `1.0` vs
  `1.0.0`; Yevis TRS reports `2.0.1` vs declared `2.0.0`). → surface all sources, flag mismatches.

## Phase 2 — Architecture

### Module layout (`src/ga4gh_mcp/`)

| Module | Responsibility |
|---|---|
| `config.py` | `Settings` (pydantic-settings, env prefix `GA4GH_MCP_`): registry URL, transport, host/port, timeouts, retries, cache TTLs, auth config path. |
| `errors.py` | Typed errors + `ok()`/`err()` structured-envelope helpers. Liveness/compliance enums. |
| `models.py` | Pydantic models: `ServiceSummary`, `ServiceDetail`, `ServiceInfoAnalysis`, `HealthReport`, `VersionAnalysis`, `AuthHint`. |
| `http_client.py` | `Ga4ghHttpClient` over `httpx.AsyncClient`: timeouts, bounded retries+backoff (429/5xx/connect, Retry-After), exception→typed-status classification (dns/timeout/tls/connect/http). |
| `serviceinfo.py` | `analyze_service_info()`: detect the 5 shapes, normalize versions, compare declared-vs-reported, produce warnings. |
| `liveness.py` | `check_liveness()`: fetch service-info (with URL fallback/inference), classify into a structured `HealthReport`, extract `WWW-Authenticate` auth hint. |
| `registry.py` | `RegistryClient`: cached fetch of services/deployments/orgs/standards; client-side filter/search; `implementationId`→UUID resolution; type aggregation. |
| `auth/base.py` | `AuthProvider` protocol (`async headers()`, `describe()`), `AuthSpec`. |
| `auth/providers.py` | `NoAuth`, `StaticBearerAuth`, `ApiKeyAuth`, `OAuth2ClientCredentialsAuth`, `OAuth2DeviceCodeAuth` (token caching + refresh). |
| `auth/resolver.py` | `AuthResolver`: pick a provider per service from config (by implementationId/host) + safe defaults; parse `WWW-Authenticate` into an `AuthHint`. |
| `services/base.py` | `ServiceTypePlugin` + `PLUGINS` registry (extensibility point). |
| `services/{drs,trs,tes,beacon,generic}.py` | Type-aware access + capability metadata; self-register. |
| `tools.py` | Thin MCP tool functions calling the above; each returns a structured envelope. |
| `server.py` | `build_server(settings)` → `FastMCP`; wires shared client/registry/auth container; registers tools. |
| `__main__.py` | CLI: `--transport/--host/--port/--path`, `--list-tools`, `auth-device` helper. Entrypoint `ga4gh-mcp`. |

### Tool surface (v1)

**Registry**
- `list_services(product?, org?, version?, environment?, implementation_type?, query?, include_deployments?, limit?)`
- `get_service(service_id)` — by UUID or implementationId (resolved locally)
- `search_services(query, limit?)`
- `list_service_types()` — products + counts + which standards
- `list_standards()` — GA4GH standards catalog + versions
- `list_organisations(query?)`
- `check_service_health(service_id)` — liveness + version/compliance analysis (structured)

**Generic (service-info driven, works across all types)**
- `get_service_info(service_id | url)` — fetch+normalize+analyze
- `call_service_endpoint(service_id, path, method=GET, query?, json_body?)` — authenticated generic call, guarded, structured result + auth hint on 401

**Type-aware helpers** (highest-value live types)
- DRS: `drs_get_object(service_id, object_id)`, `drs_get_access_url(service_id, object_id, access_id?)`
- TRS: `trs_list_tools(service_id, limit?)`, `trs_get_tool(service_id, tool_id)`
- TES: `tes_list_tasks(service_id, limit?)`, `tes_get_task(service_id, task_id)`
- Beacon: `beacon_info(service_id)`

**Auth**
- `auth_status()` — configured providers + per-service requirements discovered
- `auth_device_login(service_id | token_url,...)` — start device-code flow, return verification URI + user code (CLI-testable path)

### Transport design
Single server; `settings.transport` ∈ {`stdio`, `streamable-http`}. HTTP binds `host:port` at
`--path` (default `/mcp`), `stateless_http=True` for serverless (Vertex/Bedrock/Cloud Run).

### Auth strategy (see `docs/auth.md`)
Pluggable `AuthProvider`s selected by an `AuthResolver` from a JSON config
(`GA4GH_MCP_AUTH_CONFIG`) keyed by `implementationId` or host, with a safe default of **no auth**.
Secrets are **referenced by env-var name**, never stored literally. `WWW-Authenticate` on a 401 is
parsed into an `AuthHint` telling the model exactly what to configure. Fully testable headless:
`none` + `bearer` end-to-end now; `oauth2_client_credentials` against a mock token endpoint in unit
tests; `device_code` implemented with a CLI/tool entry path + documented.

### Version/compliance tolerance strategy
`analyze_service_info()` returns `{shape, reported_artifact, reported_type_version,
declared_product, declared_version, matches: bool, warnings: [...]}`. Liveness never throws; each
service is isolated. Registry data cached with TTL; per-service probes cached briefly.

## Phase 3 — Implementation checklist

- [x] Scaffold repo, venv, pinned deps, verify MCP SDK API
- [x] `docs/compatibility.md` (empirical matrix)
- [x] `config.py`, `errors.py`, `models.py`
- [x] `http_client.py` (timeouts/retries/classification)
- [x] `serviceinfo.py` (shape detection + version analysis)
- [x] `liveness.py` (structured health)
- [x] `registry.py` (cache + filter + search + resolve)
- [x] `auth/*` (providers + resolver + WWW-Authenticate parsing)
- [x] `services/*` (plugin base + DRS/TRS/TES/Beacon/generic)
- [x] `tools.py` + `server.py` + `__main__.py`
- [x] `scripts/probe_registry.py`, `scripts/smoke.py`, `scripts/smoke.sh`
- [x] pyproject entrypoints, Dockerfile, `.env.example`, `.gitignore`

## Phase 4 — Testing checklist

- [x] Unit tests (pytest, mocked via `respx`): registry filters, service-info shapes/versions,
      liveness edge cases (dns/timeout/tls/401/404/nonstandard), auth providers+resolver, tools.
- [x] Live integration smoke tests (guarded by `GA4GH_MCP_LIVE=1`, skippable offline) with pass/fail table.
- [x] `scripts/smoke.py` — starts server, lists tools, exercises registry tools end-to-end.
- [x] MCP Inspector-style tool-schema load check (non-interactive, via SDK `list_tools`).
- [x] Exact verification commands + expected output in README + here.

## Definition of Done

- [x] Server runs on **stdio** and **streamable-http**; all v1 tools implemented + documented.
- [x] Registry surface covered (list/detail/search/health) + every registered type accounted for
      (type-aware DRS/TRS/TES/Beacon; generic service-info for the rest); documented in compatibility.md.
- [x] Compatibility verified vs a representative live sample; down/non-compliant/version-mismatched
      handling proven by tests.
- [x] Pluggable auth implemented; **public + static-token verified headless**; other flows implemented + documented.
- [x] Copy-paste client configs for Claude Desktop, Claude Code, Vertex AI, Bedrock (each w/ a verify step).
- [x] PLAN.md / PROGRESS.md current; code committed + pushed to `mfiume/ga4gh-mcp-service`.

---

## Progress log

- **2026-07-05** — Phase 0 & 1 complete. Reverse-engineered registry API, probed all 46 endpoints,
  wrote `docs/compatibility.md`. Verified MCP SDK 1.28.1 API. Scaffolded repo + venv.
- **2026-07-05** — Phases 2–4 complete. Implemented full package (`config`, `errors`, `models`,
  `http_client`, `serviceinfo`, `liveness`, `registry`, `auth/*`, `services/*`, `tools`, `server`,
  CLI). 18 tools across stdio + streamable-http.
  - **Tests:** 63 unit tests pass (mocked via `respx`); 3 live tests skipped by default.
  - **Live smoke:** `scripts/smoke.py` round-trips **both stdio and HTTP** via the real MCP SDK
    client (Inspector-equivalent) against the live registry — ALL CHECKS PASSED (18 tools).
  - **Live integration:** `GA4GH_MCP_LIVE=1 pytest tests/test_live_integration.py` probes a
    representative sample; proves graceful handling (live / auth_required / http_error /
    unreachable_dns / tls_error / invalid_response) with no crashes.
  - **Robustness proof:** server probe classifies **24 live vs 21 for a naive probe** — it infers
    missing serviceInfoUrls and discovers `auth_required` (403) endpoints. See
    `docs/compatibility_probe.json`.
  - **Packaging:** wheel builds cleanly; entry point verified from a fresh non-editable install
    (mirrors the Dockerfile). Docker image can't be built locally (no docker daemon) but the
    `pip install .` path it uses is verified.
  - **Docs:** `docs/auth.md` + 4 client configs (Claude Desktop/Code, Vertex AI, Bedrock).
- **Known gaps / future:** Data Connect / Beacon-query / htsget-ticket / WES-run type-aware tools
  not yet added (generic `call_service_endpoint` covers them today); Docker image unbuilt locally;
  no server-side pagination for very large TRS listings (limit-capped).
- **2026-07-05 — prior attempt discovered on push.** `mfiume/ga4gh-mcp-service` already had a
  complete prior v1 on `main` (23 tools; DRS/TRS/**WES**; OAuth device-code + client-creds +
  Passport pass-through; 46 tests; pushed public). This session was a fresh, independent rebuild
  (18 tools; DRS/TRS/**TES/Beacon**; 63 tests; dual-transport SDK smoke). **Decision: do NOT
  overwrite `main`.** Pushed this rebuild to branch **`fable5-rebuild`** so Marc can compare and
  choose. PR creation is blocked by unrelated histories; compare here:
  `https://github.com/mfiume/ga4gh-mcp-service/compare/main...fable5-rebuild`.
  Both runs independently converged on the same reality (~24 live; `type.version` ≠ spec version;
  Terra/Beacon non-standard). Options for Marc: (a) keep `main`, cherry-pick TES/Beacon + smoke +
  matrix; (b) replace `main` with this branch; (c) merge best of both.
- **2026-07-06 — federation + Data Connect (ga4gh-aws-opendata integration).** Added
  `GA4GH_MCP_EXTRA_REGISTRIES` (comma-separated GA4GH Service Registry `/services` URLs): the client
  fetches + normalizes their service-info entries and merges them into `implementations()`, resilient
  to either the core or a federated registry being down. Added a `DataConnect` plugin + tools
  `data_connect_list_tables` / `data_connect_table_info` / `data_connect_search` (tool count 18→21).
  Verified end-to-end against a live `ga4gh-aws-opendata` deployment (discovery + gnomAD SQL + DRS).
  Suite: 70 passed, 3 skipped. See the sibling repo `mfiume/ga4gh-aws-opendata`.
