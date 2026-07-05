# PLAN — Universal GA4GH MCP Service

**Repo:** `mfiume/ga4gh-mcp-service`  ·  **Status:** v1 implemented, tested (both transports), documented.
**Source of truth for progress.** See `PROGRESS.md` for the running log.

---

## Mission

A universal MCP server for GA4GH services whose first capability is listing and
accessing services in the **GA4GH Implementation Registry**
(`https://registry.ga4gh.org/v1`), built to tolerate the reality that registered
implementations vary in **liveness, spec compliance, and version**. Works over
stdio (Claude Desktop / Claude Code) and streamable HTTP (Vertex AI, Amazon
Bedrock, remote). Everything is verifiable from the CLI (no UI).

## Definition of Done  → status

- [x] Server runs on **stdio** and **streamable HTTP** (single codebase, selectable).
- [x] v1 tool surface implemented (23 tools), tested, documented.
- [x] Registry surface covered: list / details / search / types / implementations / health / service-info.
- [x] Every registered **service type** accounted for: DRS/TRS/WES type-aware; refget/htsget/rnaget/search/service-registry/beacon/tes generic via service-info (plugin registry).
- [x] Robustness proven: down / non-compliant / version-mismatched / auth-gated services handled gracefully by tests + live matrix.
- [x] Pluggable **auth** layer: no-auth + static bearer verified headless; OAuth device-code, client-credentials, refresh, and discovery implemented + documented.
- [x] Copy-paste client configs for Claude Desktop, Claude Code, Vertex, Bedrock (`docs/clients/`).
- [x] Unit tests (mocked) + skippable live integration tests + `scripts/smoke.py` (both transports).
- [x] `pyproject.toml` (uvx/pipx runnable), `Dockerfile`, `docker-compose.yml`.
- [x] Pushed to `mfiume/ga4gh-mcp-service` — https://github.com/mfiume/ga4gh-mcp-service ✅

---

## Phase 0 — Prior art (mfiume repos)

- **`omics-ai-mcp-server`** (local + `mfiume/omics-ai-mcp`): the strongest template. Carried over the *patterns* (not code, to stay dependency-clean): tolerant `BaseClient` with retries/timeouts → `http.py`; OAuth **device-code** flow → `auth/manager.py`; dual-transport + tool-registration shape; pytest+respx test style; `pyproject`/Docker layout.
- Older GA4GH repos (`ga4gh-discovery-search-service`, `data-object-schemas` (DRS), `search`) — historical context only.
- No pre-existing `ga4gh-mcp-service`; the empty local `~/Development/ga4gh-mcp` was unused.

## Phase 1 — Registry, empirically understood

The frontend `implementation-registry.ga4gh.org` is a SPA backed by the API at
**`https://registry.ga4gh.org/v1`** (spec repo `ga4gh/ga4gh-registry`, follows
GA4GH **service-registry** + **service-info** standards):

| Endpoint | Meaning |
|---|---|
| `/service-info` | the registry's own GA4GH service-info |
| `/services` | **live web-service deployments** (36) — has `url`, `environment`, `curiePrefix` |
| `/implementations` | reusable **codebases** (3), no live URL |
| `/services/types` | distinct `{group, artifact, version}` combos (13) |

**Types present (live services):** `drs`(22), `service-registry`(4), `wes`(4),
`rnaget`(2), `search`(2), `trs`(2). No live `tes`/`beacon` currently (plugins
still accept them).

**Empirically-discovered nuances → design responses** (see `docs/compatibility.md`):

1. **Inconsistent registered URLs** — many DRS `url`s are `.../ga4gh/drs/v1/objects/`
   (a collection), not the base → `normalize_base_url()` strips the suffix; `api_base_url()`
   re-adds the spec's nested prefix. (Recovered 7+ "dead" services to live.)
2. **Version drift** — service-reported `type.version` (e.g. Gen3 → `1.0.3`) often ≠ registry's
   declared version (e.g. `1.2.0`) → reconciled and surfaced as a `warning`.
3. **SPA false positives** — `/service-info` may 200 with an HTML homepage (e.g. viral.ai) →
   `looks_like_service_info()` guard; classified `live_no_serviceinfo`, not `live`.
4. **Liveness varies** — private IPs (`10.42.x`), dead hosts, 5xx, 4xx → structured, never fatal.
5. **Auth is heterogeneous** — most `service-info` public; data endpoints challenge with
   `401 WWW-Authenticate: Bearer` (confirmed on `data.terra.bio`); NCI-CRDC is public.
6. **`id` is the key** — `url` is not unique (4 services share `data.terra.bio`); `environment`
   casing is inconsistent → normalized.

## Phase 2 — Architecture

```
src/ga4gh_mcp/
  __main__.py       CLI: serve | tools | call | auth   (headless-testable)
  server.py         build_server() -> FastMCP + /healthz; registers all tools
  config.py         pydantic-settings (env GA4GH_MCP_*)
  http.py           AsyncHttp -> HttpResult; retries, timeouts, never raises on net/HTTP
  cache.py          async TTL cache (registry data)
  normalize.py      PURE: url/version/env normalization, liveness classify, service-info guard
  models.py         permissive pydantic models (Service, Implementation, ServiceType)
  registry.py       RegistryClient (cached): services/implementations/types/service-info
  serviceinfo.py    generic version-tolerant service-info fetch + liveness probe
  auth/             manager (resolution + flows), discovery (WWW-Auth + OIDC), store (0600 tokens)
  ga4gh/            base (api_base + auth), drs, trs, wes, plugins (type registry)
  tools/            registry_tools, service_tools, drs/trs/wes_tools, auth_tools
  context.py        AppContext singleton + resolve(service_id_or_url)
```

Design principles: **generic-by-default** (service-info works for any type), **type-aware where
valuable** (DRS/TRS/WES), **plugin pattern** for new types, **structured results** `{ok, data|error, warnings}`
so one bad endpoint never crashes the server.

## Phase 3 — Tool surface (23 tools)

- **Registry:** `registry_list_services` (filters + optional liveness), `registry_get_service`,
  `registry_search`, `registry_list_service_types`, `registry_list_implementations`,
  `registry_service_info`, `registry_check_health`.
- **Generic:** `service_get_info`, `service_request` (authed passthrough), `list_supported_service_types`.
- **DRS:** `drs_get_object`, `drs_get_access_url`, `drs_resolve_curie` (uses registry `curiePrefix`).
- **TRS:** `trs_list_tools`, `trs_get_tool`.
- **WES:** `wes_get_service_info`, `wes_list_runs`, `wes_get_run`.
- **Auth:** `auth_status`, `auth_discover`, `auth_set_token`, `auth_login` (device-code), `auth_revoke`.

## Auth strategy (the hard part)

Per-host resolution order: cached **OAuth** token (auto-refresh) → **static bearer**
(env `GA4GH_MCP_TOKEN_<HOST>` / YAML / `auth_set_token`) → **global** bearer
(`GA4GH_MCP_BEARER_TOKEN`, opt-in) → none. Tokens are host-scoped (never leaked cross-host).
**Discovery** (`auth_discover`): provoke a `WWW-Authenticate` challenge on a protected endpoint,
then OIDC `.well-known` discovery to find token/device/authorization endpoints and pick a flow.
Flows implemented: no-auth, static bearer, **device-code** (interactive; CLI `ga4gh-mcp auth login`),
**client-credentials** (M2M), refresh. Headless now: public + static-bearer fully testable;
device-code implemented with a CLI path (needs a registered `client_id`). See `docs/auth.md`.

## Testing strategy

- **Unit (mocked, respx):** `test_normalize` (pure), `test_serviceinfo` (liveness/compliance edges),
  `test_registry` (parsing/cache/malformed-skip), `test_auth` (store/resolution/discovery),
  `test_tools` (real MCP tool calls vs mocked registry). → 46 pass.
- **Live (skippable):** `test_live.py` (`GA4GH_MCP_LIVE=1`).
- **Smoke:** `scripts/smoke.py` drives BOTH transports via a real MCP client (15/15).
- **Compat matrix:** `scripts/compat_matrix.py` probes all 36 services → `docs/compatibility.md`.

## Verification commands (see README for expected output)

```bash
uv sync --extra dev                         # or: uv pip install -e ".[dev]"
uv run pytest -q                            # 46 passed, 3 skipped
uv run python scripts/smoke.py              # 15/15 checks passed (stdio + http)
uv run ga4gh-mcp tools                      # list 23 tools
uv run ga4gh-mcp call registry_list_service_types
uv run python scripts/compat_matrix.py      # regenerate docs/compatibility.md
```

## Open items / future work

- Add typed clients for htsget (byte-range streaming), refget, rnaget, Beacon v2 as they gain live deployments.
- Optional per-request auth injection for HTTP transport (multi-tenant); today auth is server-scoped.
- Cache `service-info`/health probes with a short TTL (registry list already cached).
