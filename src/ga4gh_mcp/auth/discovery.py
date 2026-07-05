"""Auth discovery: figure out *what* a service needs and *how* to get a token.

Two mechanisms, matching GA4GH reality:

1. **WWW-Authenticate challenge** — hit a (typically protected) endpoint and read
   the ``Bearer realm="...", scope="..."`` challenge on a 401/403.
2. **OIDC discovery** — fetch ``/.well-known/openid-configuration`` on the host
   (and/or the challenge's realm/issuer) to learn the token, device-code and
   authorization endpoints.
"""

from __future__ import annotations

from urllib.parse import urlparse

from ..http import AsyncHttp
from ..normalize import api_base_url, normalize_base_url, parse_www_authenticate

# Endpoints likely to force an auth challenge, by artifact.
PROTECTED_PROBE_PATHS: dict[str, list[str]] = {
    "drs": ["/objects/_ga4gh_mcp_auth_probe"],
    "wes": ["/runs"],
    "trs": [],  # TRS is generally public
    "rnaget": ["/projects"],
    "htsget": [],
}


async def discover_oidc(http: AsyncHttp, base: str) -> dict | None:
    """Fetch an OpenID Connect discovery document from ``base``."""
    base = base.rstrip("/")
    for suffix in ("/.well-known/openid-configuration", "/.well-known/oauth-authorization-server"):
        res = await http.get_json(f"{base}{suffix}")
        if res.status == 200 and isinstance(res.json, dict) and res.json.get("token_endpoint"):
            d = res.json
            return {
                "issuer": d.get("issuer"),
                "token_endpoint": d.get("token_endpoint"),
                "device_authorization_endpoint": d.get("device_authorization_endpoint"),
                "authorization_endpoint": d.get("authorization_endpoint"),
                "scopes_supported": d.get("scopes_supported"),
                "grant_types_supported": d.get("grant_types_supported"),
                "discovery_url": f"{base}{suffix}",
            }
    return None


async def discover_auth_requirement(
    http: AsyncHttp,
    url: str,
    artifact: str | None = None,
) -> dict:
    """Determine the auth requirements for a service.

    Returns a dict describing the challenge (if any), the discovered OIDC
    endpoints, and which flows are usable.
    """
    base = normalize_base_url(url, artifact)
    api = api_base_url(url, artifact)
    parsed = urlparse(base if "://" in base else f"https://{base}")
    origin = f"{parsed.scheme}://{parsed.netloc}"

    # 1) Provoke a challenge on a protected endpoint (falls back to the base URL).
    probe_paths = PROTECTED_PROBE_PATHS.get((artifact or "").lower(), [])
    challenge = {}
    challenge_status = None
    probed = None
    for path in probe_paths + [""]:
        probe_url = f"{api}{path}" if path else api
        res = await http.get_json(probe_url)
        probed = probe_url
        challenge_status = res.status
        if res.status in (401, 403):
            challenge = parse_www_authenticate(res.www_authenticate)
            break
        if res.status == 200:
            break

    # 2) OIDC discovery — try the challenge realm first, then the service origin.
    oidc = None
    realm = (challenge.get("params") or {}).get("realm") if challenge else None
    for candidate in [realm, origin]:
        if candidate:
            oidc = await discover_oidc(http, candidate)
            if oidc:
                break

    flows = []
    if oidc:
        grants = oidc.get("grant_types_supported") or []
        if oidc.get("device_authorization_endpoint") or "urn:ietf:params:oauth:grant-type:device_code" in grants:
            flows.append("device_code")
        if oidc.get("token_endpoint"):
            flows.append("client_credentials")
        if oidc.get("authorization_endpoint"):
            flows.append("authorization_code")

    requires_auth = challenge_status in (401, 403)
    return {
        "url": url,
        "base_url": base,
        "requires_auth": requires_auth,
        "public": challenge_status == 200 and not requires_auth,
        "probed_endpoint": probed,
        "challenge_status": challenge_status,
        "challenge": challenge or None,
        "oidc": oidc,
        "available_flows": flows,
        "recommended_flow": flows[0] if flows else ("static_bearer" if requires_auth else "none"),
        "notes": _notes(requires_auth, oidc, flows),
    }


def _notes(requires_auth: bool, oidc: dict | None, flows: list[str]) -> list[str]:
    notes = []
    if not requires_auth:
        notes.append("Endpoint responded without an auth challenge — likely public (or needs a "
                     "resource-specific token only for data access).")
    if requires_auth and not oidc:
        notes.append("Auth required but no OIDC discovery document found; supply a static bearer "
                     "token via GA4GH_MCP_TOKEN_<HOST> or auth_set_token.")
    if oidc and "device_code" in flows:
        notes.append("Device-code flow available — run `ga4gh-mcp auth login <service>` (needs a "
                     "registered client_id).")
    if oidc and not flows:
        notes.append("OIDC document found but no usable grant types were advertised.")
    return notes
