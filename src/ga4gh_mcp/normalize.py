"""Pure normalization helpers — the empirically-derived heart of compatibility.

Reverse-engineered from probing all 36 services in the live registry:

* Registered ``url``s are inconsistent. Many DRS entries point at the *object
  collection* (``.../ga4gh/drs/v1/objects/``) rather than the service base, so
  ``{url}/service-info`` 404s. Stripping the collection suffix fixes them.
* Service-reported ``type.version`` often differs from the registry's declared
  version (e.g. Gen3 reports ``1.0.3`` while the registry lists DRS ``1.2.0``).
* ``environment`` casing is all over the place ("Production", "prod", "dev").

These functions are deliberately side-effect free so they can be unit tested
exhaustively without any network access.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

# Known nested API prefixes by artifact. service-info 1.0 standardizes
# ``{base}/service-info`` but older/typed deployments nest under these.
NESTED_PREFIXES: dict[str, list[str]] = {
    "drs": ["/ga4gh/drs/v1"],
    "trs": ["/ga4gh/trs/v2", "/api/ga4gh/v2", "/ga4gh/trs/v1"],
    "wes": ["/ga4gh/wes/v1"],
    "tes": ["/ga4gh/tes/v1", "/v1"],
    "htsget": ["/ga4gh/htsget/v1", "/reads", "/variants"],
    "refget": ["/sequence", "/refget"],
    "rnaget": ["/rnaget"],
    "beacon": ["/api", "/beacon"],
}

# Suffixes that indicate the registered URL points at a resource collection,
# not the service base. Stripped (per artifact) to recover the base.
COLLECTION_SUFFIXES: dict[str, list[str]] = {
    "drs": ["/objects", "/objects/"],
    "trs": ["/tools", "/tools/"],
    "refget": ["/sequence", "/sequence/"],
}


def _strip(url: str) -> str:
    return url.rstrip("/")


def host_of(url: str) -> str:
    """Return the ``host[:port]`` of a URL (lowercased host)."""
    p = urlparse(url if "://" in url else f"https://{url}")
    host = (p.hostname or "").lower()
    if p.port:
        return f"{host}:{p.port}"
    return host


def normalize_base_url(url: str, artifact: str | None = None) -> str:
    """Strip collection suffixes to recover the service base URL."""
    base = _strip(url.strip())
    art = (artifact or "").lower()
    for suffix in COLLECTION_SUFFIXES.get(art, []):
        s = suffix.rstrip("/")
        if base.lower().endswith(s.lower()):
            base = base[: -len(s)]
            base = _strip(base)
            break
    return base


def api_base_url(url: str, artifact: str | None = None) -> str:
    """Return the API base *including* the spec's nested prefix when needed.

    ``https://host`` -> ``https://host/ga4gh/drs/v1`` for DRS, while a URL that
    already contains the prefix (``https://host/ga4gh/drs/v1/objects/``) is just
    reduced to ``https://host/ga4gh/drs/v1``.
    """
    base = normalize_base_url(url, artifact)
    prefixes = NESTED_PREFIXES.get((artifact or "").lower(), [])
    for prefix in prefixes:
        if prefix.strip("/") in base.lower():
            return base
    if prefixes:
        return f"{base}{prefixes[0]}"
    return base


def service_info_candidates(url: str, artifact: str | None = None) -> list[str]:
    """Ordered list of candidate ``service-info`` URLs to try for a service."""
    base = normalize_base_url(url, artifact)
    art = (artifact or "").lower()
    candidates: list[str] = [f"{base}/service-info"]
    for prefix in NESTED_PREFIXES.get(art, []):
        # Only add the nested variant if the base doesn't already contain it.
        if prefix.strip("/") not in base.lower():
            candidates.append(f"{base}{prefix}/service-info")
        else:
            # base already includes the prefix; the first candidate covers it
            pass
    # De-duplicate preserving order
    seen: set[str] = set()
    out: list[str] = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


_VERSION_RE = re.compile(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?(.*)$")


def parse_version(raw: str | None) -> dict:
    """Parse a possibly-messy version string.

    Handles "1.3.0experimental", "2.0.1", "beta", "N/A (SaaS)". Returns a dict
    with a comparable tuple plus the raw value and any trailing suffix/label.
    """
    if not raw:
        return {"raw": raw, "tuple": None, "suffix": None, "label": None}
    s = str(raw).strip()
    m = _VERSION_RE.match(s)
    if not m:
        return {"raw": raw, "tuple": None, "suffix": None, "label": s}
    major = int(m.group(1))
    minor = int(m.group(2)) if m.group(2) else 0
    patch = int(m.group(3)) if m.group(3) else 0
    suffix = (m.group(4) or "").strip() or None
    return {"raw": raw, "tuple": (major, minor, patch), "suffix": suffix, "label": None}


def normalize_environment(env: str | None) -> str:
    """Map free-form environment strings to a small canonical set."""
    if not env:
        return "unknown"
    e = env.strip().lower()
    if e.startswith("prod"):
        return "production"
    if e.startswith("dev"):
        return "development"
    if e.startswith("stag"):
        return "staging"
    if e.startswith("test"):
        return "test"
    if e in ("demo", "sandbox", "beta"):
        return e
    return e


# Liveness verdicts
LIVE = "live"
AUTH_REQUIRED = "auth_required"
LIVE_NO_SERVICEINFO = "live_no_serviceinfo"
UNREACHABLE = "unreachable"
SERVER_ERROR = "server_error"
CLIENT_ERROR = "client_error"


def classify_liveness(status: int | None, error_kind: str | None) -> str:
    """Turn an HTTP status / error kind into a liveness verdict."""
    if status == 200:
        return LIVE
    if status in (401, 403):
        return AUTH_REQUIRED
    if status == 404:
        return LIVE_NO_SERVICEINFO
    if status is not None and 500 <= status < 600:
        return SERVER_ERROR
    if status is not None and 400 <= status < 500:
        return CLIENT_ERROR
    return UNREACHABLE


def looks_like_service_info(obj: object) -> bool:
    """Heuristic: does a decoded JSON body actually look like a GA4GH service-info?

    Guards against SPAs / proxies / homepages that return HTTP 200 with unrelated
    content (a common cause of false "live" verdicts). The spec requires ``id``,
    ``name``, ``type`` and ``version``; we accept anything with ``type`` or
    ``version``, or both ``id`` and ``name``.
    """
    if not isinstance(obj, dict):
        return False
    if "type" in obj or "version" in obj:
        return True
    return bool(obj.get("id") and obj.get("name"))


_BEARER_PARAM_RE = re.compile(r'(\w+)\s*=\s*"([^"]*)"')


def parse_www_authenticate(header: str | None) -> dict:
    """Parse a ``WWW-Authenticate`` header into scheme + params.

    Example: ``Bearer realm="https://issuer", scope="openid", error="invalid_token"``
    """
    if not header:
        return {}
    header = header.strip()
    scheme = header.split(" ", 1)[0] if " " in header else header
    params = {k.lower(): v for k, v in _BEARER_PARAM_RE.findall(header)}
    return {"scheme": scheme, "params": params}
