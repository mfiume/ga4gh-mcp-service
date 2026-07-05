"""Pydantic models for derived analyses.

Raw registry entries are passed through as plain dicts (so every upstream field is
preserved); the *derived* structures below — version/compliance analysis, health
reports, auth hints — are typed because their shape is our contract with the model.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .errors import Liveness


class VersionAnalysis(BaseModel):
    """Reconciliation of the (frequently conflicting) version signals for a service."""

    declared_product: str | None = None  # registry standardVersion.ga4ghProduct
    declared_version: str | None = None  # registry standardVersion.version
    reported_artifact: str | None = None  # service-info type.artifact
    reported_type_version: str | None = None  # service-info type.version
    reported_service_version: str | None = None  # service-info top-level version
    product_matches: bool | None = None  # declared product vs reported artifact
    version_matches: bool | None = None  # declared version vs reported type.version (normalized)
    notes: list[str] = Field(default_factory=list)


class ServiceInfoAnalysis(BaseModel):
    """Normalized view of a service-info payload, tolerant of the 5 observed shapes."""

    shape: str  # "ga4gh" | "beacon" | "nonstandard" | "unknown"
    compliant: bool  # is this a spec-valid GA4GH service-info?
    id: str | None = None
    name: str | None = None
    description: str | None = None
    organization: dict[str, Any] | None = None
    environment: str | None = None
    version: VersionAnalysis = Field(default_factory=VersionAnalysis)
    missing_required: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    raw: dict[str, Any] | None = None  # the original payload (may be trimmed)


class AuthHint(BaseModel):
    """What credentials a service appears to want, derived from a 401/WWW-Authenticate."""

    required: bool = False
    scheme: str | None = None  # "Bearer" | "Basic" | "ApiKey" | …
    realm: str | None = None
    scope: str | None = None
    authorization_uri: str | None = None  # OIDC/OAuth discovery hint if advertised
    www_authenticate: str | None = None  # raw header
    guidance: str | None = None  # human/model guidance on how to configure


class HealthReport(BaseModel):
    """Structured liveness + compliance report for one registered service."""

    service_id: str | None = None
    implementation_id: str | None = None
    name: str | None = None
    product: str | None = None
    service_info_url: str | None = None
    probed_url: str | None = None  # may differ from serviceInfoUrl if inferred
    liveness: Liveness
    http_status: int | None = None
    latency_ms: int | None = None
    service_info: ServiceInfoAnalysis | None = None
    auth: AuthHint | None = None
    error: str | None = None
    warnings: list[str] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = self.model_dump(exclude_none=True)
        d["liveness"] = self.liveness.value
        return d
