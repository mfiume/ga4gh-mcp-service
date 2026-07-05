"""Pydantic models for GA4GH registry entities.

Modeled to be *permissive* — registered records are inconsistent, so every
field beyond ``id`` is optional and unknown extra fields are preserved.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from .normalize import (
    normalize_base_url,
    normalize_environment,
    parse_version,
    service_info_candidates,
)


class ServiceType(BaseModel):
    model_config = ConfigDict(extra="allow")
    group: str | None = None
    artifact: str | None = None
    version: str | None = None

    def label(self) -> str:
        return f"{self.artifact or '?'}:{self.version or '?'}"


class Organization(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str | None = None
    name: str | None = None
    shortName: str | None = None  # noqa: N815 — matches GA4GH schema
    url: str | None = None


class Service(BaseModel):
    """A live GA4GH web service deployment (from ``/services``)."""

    model_config = ConfigDict(extra="allow")

    id: str
    name: str | None = None
    type: ServiceType | None = None
    organization: Organization | None = None
    version: str | None = None
    url: str | None = None
    description: str | None = None
    contactUrl: str | None = None  # noqa: N815
    documentationUrl: str | None = None  # noqa: N815
    environment: str | None = None
    curiePrefix: str | None = None  # noqa: N815
    createdAt: str | None = None  # noqa: N815
    updatedAt: str | None = None  # noqa: N815

    @property
    def artifact(self) -> str | None:
        return self.type.artifact if self.type else None

    def base_url(self) -> str | None:
        if not self.url:
            return None
        return normalize_base_url(self.url, self.artifact)

    def service_info_urls(self) -> list[str]:
        if not self.url:
            return []
        return service_info_candidates(self.url, self.artifact)

    def summary(self) -> dict[str, Any]:
        """Compact, model-friendly view of a service."""
        org = self.organization.name if self.organization else None
        curie = self.curiePrefix if self.curiePrefix not in (None, "N/A", "TBC") else None
        return {
            "id": self.id,
            "name": self.name,
            "artifact": self.artifact,
            "declared_version": self.type.version if self.type else None,
            "version_parsed": parse_version(self.type.version if self.type else None),
            "organization": org,
            "url": self.url,
            "base_url": self.base_url(),
            "environment": normalize_environment(self.environment),
            "environment_raw": self.environment,
            "curie_prefix": curie,
            "documentation_url": self.documentationUrl,
            "description": (self.description or "")[:400] or None,
        }


class Implementation(BaseModel):
    """A software implementation / codebase of a GA4GH standard (from ``/implementations``)."""

    model_config = ConfigDict(extra="allow")

    id: str
    name: str | None = None
    type: ServiceType | None = None
    organization: Organization | None = None
    version: str | None = None
    description: str | None = None
    contactUrl: str | None = None  # noqa: N815
    documentationUrl: str | None = None  # noqa: N815

    def summary(self) -> dict[str, Any]:
        org = self.organization.name if self.organization else None
        return {
            "id": self.id,
            "name": self.name,
            "artifact": self.type.artifact if self.type else None,
            "spec_version": self.type.version if self.type else None,
            "software_version": self.version,
            "organization": org,
            "documentation_url": self.documentationUrl,
            "description": (self.description or "")[:400] or None,
        }


class ServiceTypeInfo(BaseModel):
    model_config = ConfigDict(extra="allow")
    group: str | None = None
    artifact: str | None = None
    version: str | None = None
