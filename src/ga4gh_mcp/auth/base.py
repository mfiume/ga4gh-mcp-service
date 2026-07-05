"""Auth provider protocol and the declarative auth spec read from config."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class AuthProvider(Protocol):
    """Produces request headers for an outbound call; may refresh tokens lazily."""

    kind: str

    async def headers(self) -> dict[str, str]:
        """Return auth headers to attach (empty dict for public services)."""
        ...

    def describe(self) -> dict[str, Any]:
        """Non-secret description of this provider for `auth_status` (never leaks tokens)."""
        ...


@dataclass
class AuthSpec:
    """Declarative auth configuration for a service (from the auth config file).

    Secrets are referenced by *environment variable name*, never stored literally.
    """

    kind: str = "none"  # none | bearer | api_key | oauth2_client_credentials | oauth2_device_code
    match: str | None = None  # implementationId or host this spec applies to
    # bearer / api_key
    token_env: str | None = None
    header: str | None = None  # api_key header name (default "Authorization")
    value_env: str | None = None  # api_key value env var
    value_prefix: str = ""  # e.g. "Bearer " for api_key-style bearer
    # oauth2
    token_url: str | None = None
    device_authorization_url: str | None = None
    client_id: str | None = None
    client_id_env: str | None = None
    client_secret_env: str | None = None
    scope: str | None = None
    audience: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "AuthSpec":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in d.items() if k in known})
