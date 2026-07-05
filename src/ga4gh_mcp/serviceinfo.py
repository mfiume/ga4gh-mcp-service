"""Tolerant parsing + version reconciliation for GA4GH service-info payloads.

Reality (see docs/compatibility.md): registered services return at least five different
service-info shapes, and the version fields disagree. This module normalizes what it can,
records *why* something is non-compliant, and reconciles the (often conflicting) version
signals rather than trusting any single one.
"""

from __future__ import annotations

from typing import Any

from .models import ServiceInfoAnalysis, VersionAnalysis

# Spec-required fields for a GA4GH service-info Service object.
_REQUIRED = ("id", "name", "type", "organization", "version")


def normalize_version(v: str | None) -> tuple[int, ...] | None:
    """`'v2.0.0'`/`'1.0'` -> comparable tuple; None if not parseable."""
    if not v or not isinstance(v, str):
        return None
    s = v.strip().lstrip("vV")
    # keep only the leading dotted-number core (drop pre-release/build suffixes)
    core = []
    for part in s.split("."):
        num = ""
        for ch in part:
            if ch.isdigit():
                num += ch
            else:
                break
        if num == "":
            break
        core.append(int(num))
    return tuple(core) or None


def _versions_equal(a: str | None, b: str | None) -> bool | None:
    na, nb = normalize_version(a), normalize_version(b)
    if na is None or nb is None:
        return None
    n = max(len(na), len(nb))
    return na + (0,) * (n - len(na)) == nb + (0,) * (n - len(nb))


def _detect_shape(payload: dict[str, Any]) -> str:
    t = payload.get("type")
    if isinstance(t, dict) and t.get("artifact"):
        return "ga4gh"
    if "meta" in payload and "response" in payload:
        return "beacon"
    if payload.get("beaconId") or (payload.get("apiVersion") and "response" in payload):
        return "beacon"
    if "title" in payload and "version" in payload and "id" not in payload:
        return "nonstandard"  # e.g. Terra "Jade" DRS
    return "unknown"


def analyze_service_info(
    payload: Any,
    *,
    declared_product: str | None = None,
    declared_version: str | None = None,
) -> ServiceInfoAnalysis:
    """Normalize a service-info payload and reconcile versions against the registry."""
    va = VersionAnalysis(declared_product=declared_product, declared_version=declared_version)

    if not isinstance(payload, dict):
        va.notes.append("service-info body was not a JSON object")
        return ServiceInfoAnalysis(
            shape="unknown", compliant=False, version=va,
            warnings=["service-info was not a JSON object"], raw=None,
        )

    shape = _detect_shape(payload)
    warnings: list[str] = []
    missing: list[str] = []
    org: dict[str, Any] | None = None
    sid = name = desc = env = None

    if shape == "ga4gh":
        t = payload.get("type") or {}
        va.reported_artifact = t.get("artifact")
        va.reported_type_version = t.get("version")
        va.reported_service_version = payload.get("version")
        sid = payload.get("id")
        name = payload.get("name")
        desc = payload.get("description")
        env = payload.get("environment")
        o = payload.get("organization")
        org = o if isinstance(o, dict) else ({"name": str(o)} if o else None)
        for f in _REQUIRED:
            if f not in payload or payload.get(f) in (None, "", {}):
                missing.append(f)
        if isinstance(org, dict):
            for f in ("name", "url"):
                if not org.get(f):
                    missing.append(f"organization.{f}")

    elif shape == "beacon":
        meta = payload.get("meta") or {}
        resp = payload.get("response") or {}
        va.reported_artifact = "beacon"
        va.reported_type_version = meta.get("apiVersion") or payload.get("apiVersion")
        va.reported_service_version = resp.get("version") or resp.get("apiVersion")
        sid = resp.get("id") or payload.get("beaconId") or meta.get("beaconId")
        name = resp.get("name")
        desc = resp.get("description")
        env = resp.get("environment")
        o = resp.get("organization")
        org = o if isinstance(o, dict) else None
        warnings.append(
            "Beacon services publish a framework 'info' document, not a GA4GH service-info; "
            "fields were mapped best-effort from meta/response."
        )

    elif shape == "nonstandard":
        va.reported_service_version = payload.get("version")
        name = payload.get("title")
        desc = payload.get("description")
        warnings.append(
            "service-info is NOT a spec-compliant GA4GH document (missing id/name/type). "
            "Falling back to the registry-declared product/version."
        )
        for f in ("id", "name", "type"):
            missing.append(f)

    else:  # unknown
        warnings.append("Unrecognized service-info shape; returning raw payload only.")

    # ---- reconcile versions ----
    if va.declared_product and va.reported_artifact:
        va.product_matches = va.declared_product.strip().lower() == va.reported_artifact.strip().lower()
        if va.product_matches is False:
            warnings.append(
                f"product mismatch: registry declares '{va.declared_product}' but service-info "
                f"type.artifact is '{va.reported_artifact}'."
            )
    if va.declared_version and va.reported_type_version:
        eq = _versions_equal(va.declared_version, va.reported_type_version)
        va.version_matches = eq
        if eq is False:
            warnings.append(
                f"version discrepancy: registry declares '{va.declared_version}' but service-info "
                f"reports type.version '{va.reported_type_version}'. Note: some servers report the "
                f"service-info schema version here rather than the API spec version."
            )
    va.notes = [w for w in warnings if "version" in w or "product" in w]

    compliant = shape == "ga4gh" and not missing
    return ServiceInfoAnalysis(
        shape=shape,
        compliant=compliant,
        id=sid,
        name=name,
        description=desc,
        organization=org,
        environment=env,
        version=va,
        missing_required=missing,
        warnings=warnings,
        raw=payload,
    )
