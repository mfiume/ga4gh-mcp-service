"""Structured errors, status enums, and the tool result envelope.

Design principle (see docs/compatibility.md): a single down / non-compliant / slow
upstream service must never crash the MCP server. Tools catch everything and return a
structured envelope so the model gets a clear, machine-readable signal.
"""

from __future__ import annotations

from enum import Enum
from typing import Any


class Liveness(str, Enum):
    """Classification of a service-info probe outcome."""

    LIVE = "live"  # reachable, returned a usable service-info
    AUTH_REQUIRED = "auth_required"  # reachable but 401/403 — needs credentials
    HTTP_ERROR = "http_error"  # reachable, non-auth HTTP error (404/5xx/…)
    INVALID_RESPONSE = "invalid_response"  # reachable, but body is not JSON / not parseable
    TIMEOUT = "timeout"  # connect/read timed out
    UNREACHABLE_DNS = "unreachable_dns"  # hostname does not resolve
    TLS_ERROR = "tls_error"  # TLS handshake failed
    CONNECTION_ERROR = "connection_error"  # refused / reset / other transport error
    NO_SERVICE_INFO_URL = "no_service_info_url"  # registry entry has no serviceInfoUrl


# Liveness values that mean "the host answered us" (useful for filtering/among "up").
REACHABLE = {
    Liveness.LIVE,
    Liveness.AUTH_REQUIRED,
    Liveness.HTTP_ERROR,
    Liveness.INVALID_RESPONSE,
}


class ErrorType(str, Enum):
    NOT_FOUND = "not_found"  # service id / object not found in registry
    VALIDATION = "validation"  # bad arguments
    UPSTREAM = "upstream"  # an upstream GA4GH service failed
    AUTH = "auth"  # authentication/authorization problem
    UNSUPPORTED = "unsupported"  # operation not supported for this service type
    INTERNAL = "internal"  # unexpected server-side error


class ToolError(Exception):
    """Raised inside tool logic; converted to an error envelope at the boundary."""

    def __init__(
        self,
        error_type: ErrorType,
        message: str,
        *,
        detail: Any = None,
        hint: str | None = None,
    ) -> None:
        super().__init__(message)
        self.error_type = error_type
        self.message = message
        self.detail = detail
        self.hint = hint

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"type": self.error_type.value, "message": self.message}
        if self.detail is not None:
            out["detail"] = self.detail
        if self.hint:
            out["hint"] = self.hint
        return out


def ok(data: Any = None, *, warnings: list[str] | None = None, **extra: Any) -> dict[str, Any]:
    """Success envelope. ``extra`` merges top-level convenience fields."""
    env: dict[str, Any] = {"ok": True}
    if data is not None:
        env["data"] = data
    env["warnings"] = warnings or []
    env.update(extra)
    return env


def err(
    error_type: ErrorType | str,
    message: str,
    *,
    detail: Any = None,
    hint: str | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    """Error envelope. Never raised to the transport — always returned as data."""
    et = error_type.value if isinstance(error_type, ErrorType) else str(error_type)
    error: dict[str, Any] = {"type": et, "message": message}
    if detail is not None:
        error["detail"] = detail
    if hint:
        error["hint"] = hint
    return {"ok": False, "error": error, "warnings": warnings or []}
