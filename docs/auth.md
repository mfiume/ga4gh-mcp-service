# Authentication

GA4GH services are heterogeneous: many are public for `/service-info`, but data endpoints
(DRS access URLs, TES tasks, protected Beacons) require OAuth2/OIDC bearer tokens, GA4GH
Passport/AAI visas, or API keys. This server ships a **pluggable auth layer** that selects the
right flow per service and **never stores secrets in code** — credentials are always read from
environment variables (referenced by *name* in the config).

## Providers

| `kind` | Flow | Headless-testable now? | Required inputs (env-var names in config) |
|---|---|---|---|
| `none` | no auth (public) | ✅ fully | — |
| `bearer` | static bearer token | ✅ fully | `token_env` |
| `api_key` | static API key header | ✅ fully | `value_env`, `header` (default `Authorization`), `value_prefix` |
| `oauth2_client_credentials` | machine-to-machine OAuth2 | ✅ (mock token endpoint in tests) | `token_url`, `client_id`/`client_id_env`, `client_secret_env`, `scope`, `audience` |
| `oauth2_device_code` | interactive device grant (RFC 8628) | ⚙️ implemented; interactive step needs a browser once | `device_authorization_url`, `token_url`, `client_id`/`client_id_env`, `scope` |

GA4GH **Passport/AAI** is an OAuth2/OIDC profile: obtain a token via `oauth2_device_code`
(interactive) or `oauth2_client_credentials` (M2M) from the broker/IdP, then the token (which may
carry passport visas) is sent as a bearer token. No separate provider is needed; point the OAuth
provider at your broker's endpoints.

## How a provider is chosen (resolution order)

For each outbound call, `AuthResolver.resolve(service)` picks:

1. An explicit **config match** — a spec whose `match` equals the service's `implementationId`,
   then (if none) a spec whose `match` equals the service **host**.
2. Otherwise, the **global static bearer** (`GA4GH_MCP_BEARER_TOKEN`) — but *only* for hosts in
   the allow-list `GA4GH_MCP_BEARER_HOSTS` (comma-separated). Empty allow-list ⇒ never auto-sent,
   so a token is never leaked to an unintended host.
3. Otherwise **`none`**.

On a `401`/`403`, the server parses the `WWW-Authenticate` header into an **auth hint**
(`scheme`, `realm`, `scope`, `authorization_uri`, guidance) and returns it in the error envelope,
telling the model exactly what to configure.

## Config file

Set `GA4GH_MCP_AUTH_CONFIG=/path/to/auth.json`. Two accepted shapes:

```jsonc
// map form — key is the match (implementationId or host)
{
  "services": {
    "com.sb.cgc.drs": { "kind": "bearer", "token_env": "CGC_TOKEN" },
    "data.terra.bio": {
      "kind": "oauth2_device_code",
      "device_authorization_url": "https://accounts.google.com/o/oauth2/device/code",
      "token_url": "https://oauth2.googleapis.com/token",
      "client_id_env": "TERRA_CLIENT_ID",
      "scope": "openid email profile"
    },
    "some-service.org": {
      "kind": "oauth2_client_credentials",
      "token_url": "https://idp.example/oauth/token",
      "client_id_env": "SVC_CLIENT_ID",
      "client_secret_env": "SVC_CLIENT_SECRET",
      "scope": "drs:read"
    }
  }
}
```

```jsonc
// list form — each spec carries its own "match"
[
  { "match": "workflowhub.eu", "kind": "api_key", "header": "X-API-Key", "value_env": "WFHUB_KEY" }
]
```

Secrets themselves live only in the environment:

```bash
export CGC_TOKEN="…"
export TERRA_CLIENT_ID="…"
export SVC_CLIENT_ID="…"; export SVC_CLIENT_SECRET="…"
export WFHUB_KEY="…"
```

## Verify headless (no browser)

**Public path** (no auth) — proven by the whole live suite:

```bash
GA4GH_MCP_LIVE=1 pytest -q -s tests/test_live_integration.py
```

**Static bearer path** — unit-tested end-to-end, and manually:

```bash
export MY_TOKEN=abc
cat > /tmp/auth.json <<'JSON'
{ "services": { "org.test.drs": { "kind": "bearer", "token_env": "MY_TOKEN" } } }
JSON
GA4GH_MCP_AUTH_CONFIG=/tmp/auth.json ga4gh-mcp --list-tools   # loads without error
pytest -q tests/test_auth.py                                  # bearer/api_key/client_creds/device all covered
```

**Client-credentials path** — verified against a mock token endpoint in `tests/test_auth.py`
(`test_client_credentials_fetches_and_caches_token`). Configure real `token_url` + client env vars
to use it live.

## Interactive device-code (CLI path, for later)

Configure an `oauth2_device_code` spec for the service, then:

```bash
# via the MCP tool (from any client): auth_device_login(service_id="…")
# it returns { verification_uri, user_code, verification_uri_complete, interval }
```

Open the `verification_uri` in any browser once, enter the `user_code`, and authorize. The token is
cached to `~/.ga4gh-mcp/tokens/<match>.json` (mode 0600) and refreshed automatically thereafter.
The device flow's start + poll + refresh logic is unit-tested in
`tests/test_auth.py::test_device_code_flow_start_and_poll`.

## Guarantees

- Tokens are **never** logged or returned to the model (only booleans like `token_present`).
- `auth_status` reports the configured specs, the global-bearer allow-list, and the token store
  path — but no secret values.
