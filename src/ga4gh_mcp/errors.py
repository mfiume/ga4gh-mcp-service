"""Structured result/error helpers.

Every MCP tool returns a plain ``dict`` shaped like::

    {"ok": true,  "data": ...,          "warnings": [...]}
    {"ok": false, "error": {"kind": ..., "message": ...}, "warnings": [...]}

This keeps the model well-informed and guarantees that a single failing
endpoint never crashes the server or produces an opaque stack trace.
"""

from __future__ import annotations

import functools
import logging
from typing import Any

logger = logging.getLogger("ga4gh_mcp")

# Error kinds surfaced to the model
ERR_NOT_FOUND = "not_found"
ERR_UNREACHABLE = "unreachable"
ERR_TIMEOUT = "timeout"
ERR_AUTH_REQUIRED = "auth_required"
ERR_UPSTREAM = "upstream_error"
ERR_BAD_INPUT = "bad_input"
ERR_UNSUPPORTED = "unsupported"
ERR_INTERNAL = "internal_error"


def ok(data: Any, warnings: list[str] | None = None, **extra: Any) -> dict:
    result: dict[str, Any] = {"ok": True, "data": data}
    if warnings:
        result["warnings"] = warnings
    result.update(extra)
    return result


def err(kind: str, message: str, warnings: list[str] | None = None, **extra: Any) -> dict:
    result: dict[str, Any] = {"ok": False, "error": {"kind": kind, "message": message}}
    if warnings:
        result["warnings"] = warnings
    result.update(extra)
    return result


class ToolError(Exception):
    """Raised inside tools to short-circuit with a structured error."""

    def __init__(self, kind: str, message: str, **extra: Any) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.extra = extra

    def as_result(self) -> dict:
        return err(self.kind, self.message, **self.extra)


def safe_tool(func):
    """Decorator: guarantee a tool never raises; always returns a result dict."""

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> dict:
        try:
            return await func(*args, **kwargs)
        except ToolError as e:
            return e.as_result()
        except Exception as e:  # noqa: BLE001 — deliberate catch-all at the tool boundary
            logger.exception("Tool %s failed", getattr(func, "__name__", "?"))
            return err(ERR_INTERNAL, f"{type(e).__name__}: {e}")

    return wrapper
