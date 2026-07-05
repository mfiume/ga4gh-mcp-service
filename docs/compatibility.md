# GA4GH Implementation Registry — Compatibility Matrix

This document is the **empirical basis** for the server's design. It was produced by
probing every `serviceInfoUrl` registered in the
[GA4GH Implementation Registry](https://implementation-registry.ga4gh.org/) on
**2026-07-05** and recording liveness, spec version, compliance, and auth behaviour.

Reproduce it any time:

```bash
python scripts/probe_registry.py            # writes docs/compatibility_probe.json + prints table
```

## Registry API (reverse-engineered)

The registry frontend is a React SPA; its backend API is public JSON at
`https://implementation-registry.ga4gh.org/api`:

| Endpoint | Returns | Notes |
|---|---|---|
| `GET /api/service-info` | the registry's own GA4GH service-info | `type.artifact = org.ga4gh.registry` |
| `GET /api/services` | array of registered **SERVICE** entries | 40 as of probe date |
| `GET /api/deployments` | array of **DEPLOYMENT** entries (software products) | 6; `serviceInfoUrl` often null |
| `GET /api/organisations` | array of organisations | 33 |
| `GET /api/standards` | GA4GH standards catalog + versions | 11 standards |
| `GET /api/services/{uuid}` | single entry by **UUID** | by `implementationId` returns HTTP 500 |

**Key API facts that shape the client:**

- **No server-side filtering.** `?type=DRS`, `?ga4ghProduct=DRS`, etc. are all ignored and
  return the full list. All filtering (type/org/version/liveness/search) is done **client-side**.
- **No OpenAPI/Swagger.** `/api/openapi.json` and friends return HTTP 500.
- **Detail lookup is by UUID only.** `implementationId` (e.g. `com.sb.cgc.drs`) 500s on the
  detail route, so we resolve `implementationId` → UUID locally from the cached list.

## Service entry data model (from `/api/services`)

```
id, implementationId, name, description, url, implementationType (SERVICE|DEPLOYMENT),
contactEmails[], documentationUrl, serviceInfoUrl, environment (PRODUCTION|null|…),
curiePrefix, organisation{id,orgId,name,shortName,url,description},
standardVersion{version, ga4ghProduct, description, …},   ← authoritative DECLARED spec+version
geolocation{latitude,longitude,city,country},
implData{drs{objectsCount,storageFootprintGb,hostingInfra,queryConsent}, wes, tes, trs},
createdAt, updatedAt
```

## Service types present (live catalog)

| ga4ghProduct | # SERVICEs | Declared versions seen |
|---|---|---|
| DRS | 25 | 1.0.0, 1.2.0, 1.3.0, 1.4.0, 1.5.0 |
| TES | 8 | 1.0.0, 1.1.0 |
| TRS | 4 | 2.0.0, 2.0.1 |
| Beacon | 1 | v2.0.0 |
| WES | 1 | 1.1.0 |
| htsget | 1 | 1.2.0 |

Standards the registry **knows about** (can register), from `/api/standards`:
DRS, WES, TES, TRS, htsget, refget, seqcol, Beacon, RNAget (APIs) + Passports, DUO (policies).

## Liveness summary (46 probed = 40 services + 6 deployments)

| Status | Count | Meaning |
|---|---|---|
| `live+valid` | 21 | reachable, returns spec-compliant GA4GH service-info |
| `live+nonstandard` | 5 | reachable, returns JSON but **not** a valid GA4GH service-info (Beacon info shape; Terra "Jade" shape) |
| `no_service_info_url` | 13 | registry entry has no `serviceInfoUrl` (mostly DEPLOYMENTs + a few services) |
| `http_error` (404) | 2 | reachable host, service-info path missing / different |
| `dns_fail` | 3 | hostname does not resolve (test/placeholder entries) |
| `timeout` | 1 | private/internal IP (`10.42.28.180`) unreachable from public internet |
| `tls_error` | 1 | TLS handshake fails (`WRONG_VERSION_NUMBER`) |

## Server probe vs. naive probe (why the server does better)

The table below is a **naive external probe** (fetch each registered `serviceInfoUrl` as-is).
The server's own probe (`python scripts/probe_registry.py` → `docs/compatibility_probe.json`)
does two extra things and consequently classifies **more services as live (24 vs 21)**:

- **Infers a `serviceInfoUrl`** from the base `url` + the type's default path when the registry
  entry has none (recovered e.g. *Gen3 Indexd Server*, *TESK @ ELIXIR-CZ (Prod)*).
- **Discovers auth**: several TESK endpoints answer `403` → classified `auth_required` with an
  auth hint, rather than a bare failure.

Latest server-probe liveness distribution: `live: 24, invalid_response: 4, http_error: 5,
unreachable_dns: 5, no_service_info_url: 3, auth_required: 2, timeout: 1, tls_error: 1,
connection_error: 1`.

## The five service-info shapes we must tolerate

1. **Spec-compliant GA4GH service-info** (most DRS 1.2/1.3/1.5, TES, TRS): has
   `id`, `name`, `type:{group,artifact,version}`, `version`, `organization:{name,url}`.
   `type.artifact` is the reliable **kind** signal (`drs`/`tes`/`trs`/…).
2. **Gen3 DRS** (`type.version = "1.0.3"`): valid service-info, but `type.version` is the
   **service-info schema version**, *not* the DRS API version the registry declares (1.2.0).
   `id` is a k8s pod name. → do **not** trust `type.version` as the spec version.
3. **Terra "Jade" DRS** (`version = "0.0.1"`): **non-compliant** — `{version,title,description,contact,license}`,
   no `id`/`name`/`type`. Must fall back to the registry-declared product (DRS) and emit a compliance warning.
4. **Beacon v2** info (`/api/info`): `{meta, response}` framework shape — entirely different from
   GA4GH service-info; version lives in `meta.apiVersion` / `response`.
5. **Version-string quirks**: TESK reports `"1.0"` where the registry declares `"1.0.0"` → normalize.

## Full probe table

<!-- BEGIN PROBE TABLE (generated) -->
| Product | Name | Status | HTTP | service-info `type.version` | Registry-declared | serviceInfoUrl |
|---|---|---|---|---|---|---|
| Beacon | AfriGen-D Beacon | live+nonstandard | 200 | — | v2.0.0 | `https://beacon.afrigen-d.org/api/info` |
| DRS | AfriGen-D DRS | live+valid | 200 | 1.5.0 | 1.5.0 | `https://dev-drs.afrigen-d.dev/ga4gh/drs/v1/service-info` |
| DRS | Bio-OS DRS API | no_url | — | — | 1.0.0 | `—` |
| DRS | BioData Catalyst (Seven Bridges) | live+valid | 200 | 1.3.0 | 1.3.0 | `https://ga4gh-api.sb.biodatacatalyst.nhlbi.nih.gov/…` |
| DRS | Bloodpac | live+valid | 200 | 1.0.3 | 1.2.0 | `https://data.bloodpac.org/ga4gh/drs/v1/service-info` |
| DRS | Broad Institute (Terra) | live+nonstandard | 200 | 0.0.1 | 1.3.0 | `https://data.terra.bio/ga4gh/drs/v1/service-info` |
| DRS | Cancer Genomics Cloud DRS API | live+valid | 200 | 1.3.0 | 1.3.0 | `https://cgc-ga4gh-api.sbgenomics.com/…` |
| DRS | Canine Data Commons | live+valid | 200 | 1.0.3 | 1.2.0 | `https://caninedc.org/ga4gh/drs/v1/service-info` |
| DRS | Cavatica DRS API | live+valid | 200 | 1.3.0 | 1.3.0 | `https://cavatica-ga4gh-api.sbgenomics.com/…` |
| DRS | Chicagoland Covid-19 Commons | live+valid | 200 | 1.0.3 | 1.2.0 | `https://chicagoland.pandemicresponsecommons.org/…` |
| DRS | DRS @ EBI | timeout | — | — | 1.3.0 | `http://10.42.28.180:4500/…` (private IP) |
| DRS | Gen3 Data Hub | live+valid | 200 | 1.0.3 | 1.2.0 | `https://gen3.datacommons.io/…` |
| DRS | Gen3 Indexd Server | no_url | — | — | 1.1.0 | `—` |
| DRS | Human Cell Atlas (Terra) | live+nonstandard | 200 | 0.0.1 | 1.3.0 | `https://data.terra.bio/ga4gh/drs/v1/service-info` |
| DRS | ICGC PCAWG & DREAM Challenge | live+valid | 200 | 1.0.3 | 1.2.0 | `https://icgc.bionimbus.org//ga4gh/drs/v1/service-info` (double slash) |
| DRS | JCOIN | live+valid | 200 | 1.0.3 | 1.2.0 | `https://jcoin.datacommons.io/…` |
| DRS | LungMAP (Terra) | live+nonstandard | 200 | 0.0.1 | 1.3.0 | `https://data.terra.bio/ga4gh/drs/v1/service-info` |
| DRS | MIDRC | live+valid | 200 | 1.0.3 | 1.2.0 | `https://data.midrc.org/…` |
| DRS | NCBI DRS | live+valid | 200 | 1.2.0 | 1.2.0 | `https://locate.be-md.ncbi.nlm.nih.gov/…` |
| DRS | NCI CRDC | live+valid | 200 | 1.0.3 | 1.2.0 | `https://nci-crdc.datacommons.io/…` |
| DRS | NHGRI AnVIL (Terra) | live+nonstandard | 200 | 0.0.1 | 1.3.0 | `https://data.terra.bio/ga4gh/drs/v1/service-info` |
| DRS | NHS Genomic Data Access | http_error | 404 | — | 1.4.0 | `https://sandbox.api.service.nhs.uk/…/drs/v1.4/service-info` (version-in-path) |
| DRS | Sage Bionetworks Synapse DRS | live+valid | 200 | 1.2.0 | 1.2.0 | `https://repo-prod.prod.sagebase.org/…` |
| DRS | Test 2 | dns_fail | — | — | 1.4.0 | `https://drs2.ga4gh.org/…` |
| DRS | Test DRS 1 | dns_fail | — | — | 1.4.0 | `https://drs1.test.ga4gh.org/…` |
| DRS | Veterans Precision Oncology DC | live+valid | 200 | 1.0.3 | 1.2.0 | `https://vpodc.data-commons.org/…` |
| DRS | Viral AI | no_url | — | — | 1.0.0 | `—` |
| TES | Funnel/OpenPBS @ ELIXIR-CZ | http_error | 404 | — | 1.1.0 | `https://funnel.cloud.e-infra.cz/service-info` |
| TES | TESK/Kubernetes @ ELIXIR-* | no_url | — | — | 1.0.0/1.1.0 | `—` (5 entries) |
| TES | TESK/Kubernetes @ ELIXIR-GR | live+valid | 200 | 1.0 | 1.0.0 | `https://tesk-eu.hypatia-comp.athenarc.gr/v1/service-info` |
| TES | TESK/OpenShift @ ELIXIR-FI | live+valid | 200 | 1.0 | 1.0.0 | `https://csc-tesk-noauth.rahtiapp.fi/…` |
| TRS | BioContainers | tls_error | — | — | 2.0.0 | `https://api.biocontainers.pro/…` (WRONG_VERSION_NUMBER) |
| TRS | DNAstack / Terra | no_url | — | — | 2.0.0 | `—` |
| TRS | Dockstore | live+valid | 200 | 2.0.1 | 2.0.1 | `https://dockstore.org/api/ga4gh/trs/v2/service-info` |
| TRS | WorkflowHub | live+valid | 200 | 2.0.1 | 2.0.1 | `https://workflowhub.eu/ga4gh/trs/v2/service-info` |
| TRS | Yevis ddbj/workflow-registry | live+valid | 200 | 2.0.1 | 2.0.0 | `https://ddbj.github.io/workflow-registry/service-info/` |
| WES | Secure Processing Environment | no_url | — | — | 1.1.0 | `—` |
| htsget | Jons Awesome HTSGet server | dns_fail | — | — | 1.2.0 | `https://htsget.jonsserver/mybigendpoint` (placeholder) |
| htsget | htsget Reference Server | no_url | — | — | 1.2.0 | `—` |
| refget | Refget Cloud codebase | no_url | — | — | 1.0.0 | `—` |
<!-- END PROBE TABLE -->

## Design implications (→ how the server behaves)

1. **Never trust a single version source.** Report all three: registry-declared `standardVersion`,
   service-info `type.version`, and `type.artifact`. Flag mismatches as *warnings*, not errors.
2. **Tolerate non-compliant service-info** (Terra "Jade", Beacon). Detect the shape, fall back to
   the registry-declared product, still return whatever fields exist, attach compliance warnings.
3. **Classify liveness into structured statuses** (`live`, `auth_required`, `http_error`,
   `unreachable_dns`, `timeout`, `tls_error`, `connection_error`, `invalid_response`,
   `no_service_info_url`) so the model gets a clear signal per service.
4. **One bad service never crashes the server.** Every outbound call is isolated, timed out, and
   returns a structured envelope `{ok, data, warnings, error}`.
5. **Auth is mostly public for service-info**, but data endpoints (DRS access URLs, TES tasks) need
   bearer/OAuth. Discover requirements from `WWW-Authenticate` challenges + config; see `docs/auth.md`.
