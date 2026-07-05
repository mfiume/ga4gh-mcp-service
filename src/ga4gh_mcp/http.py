"""Robust async HTTP client for talking to heterogeneous GA4GH services.

The whole point of this module is *tolerance*. Registered implementations vary
wildly in liveness and behaviour, so :meth:`AsyncHttp.request` never raises for
network or HTTP errors — it returns an :class:`HttpResult` describing exactly
what happened (timeout / connection / DNS / HTTP status / decode error), which
the tool layer turns into a structured, model-friendly response.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger("ga4gh_mcp.http")

RETRYABLE_STATUS = {429, 502, 503, 504}

# Error kinds returned in HttpResult.error_kind
KIND_TIMEOUT = "timeout"
KIND_CONNECT = "connect"
KIND_DNS = "dns"
KIND_TLS = "tls"
KIND_HTTP = "http"
KIND_DECODE = "decode"
KIND_OTHER = "other"


@dataclass
class HttpResult:
    url: str
    status: int | None = None
    ok: bool = False
    json: Any | None = None
    text: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    error: str | None = None
    error_kind: str | None = None
    elapsed_ms: int = 0

    @property
    def www_authenticate(self) -> str | None:
        for k, v in self.headers.items():
            if k.lower() == "www-authenticate":
                return v
        return None

    def summary(self) -> dict:
        """Compact dict for embedding in tool responses."""
        return {
            "url": self.url,
            "status": self.status,
            "ok": self.ok,
            "error_kind": self.error_kind,
            "error": self.error,
            "elapsed_ms": self.elapsed_ms,
        }


class AsyncHttp:
    """Shared async HTTP client with retries and structured results."""

    def __init__(self, timeout: float = 15.0, max_retries: int = 2, retry_delay: float = 0.5,
                 user_agent: str = "ga4gh-mcp-service/0.1") -> None:
        self._timeout = timeout
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self._user_agent = user_agent
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                follow_redirects=True,
                timeout=self._timeout,
                headers={"User-Agent": self._user_agent},
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()

    @staticmethod
    def _classify(exc: Exception) -> tuple[str, str]:
        if isinstance(exc, httpx.TimeoutException):
            return KIND_TIMEOUT, f"request timed out: {exc}"
        if isinstance(exc, httpx.ConnectError):
            msg = str(exc).lower()
            if "name or service not known" in msg or "nodename nor servname" in msg or "getaddrinfo" in msg:
                return KIND_DNS, f"dns resolution failed: {exc}"
            return KIND_CONNECT, f"connection failed: {exc}"
        if isinstance(exc, (httpx.ConnectTimeout,)):
            return KIND_TIMEOUT, f"connect timed out: {exc}"
        if "ssl" in type(exc).__name__.lower() or "certificate" in str(exc).lower():
            return KIND_TLS, f"TLS error: {exc}"
        return KIND_OTHER, f"{type(exc).__name__}: {exc}"

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        json: Any | None = None,
        data: Any | None = None,
        timeout: float | None = None,
    ) -> HttpResult:
        client = self._get_client()
        req_headers = {"Accept": "application/json"}
        if headers:
            req_headers.update(headers)
        start = time.monotonic()
        last_exc: Exception | None = None
        attempts = self._max_retries + 1

        for attempt in range(attempts):
            try:
                resp = await client.request(
                    method, url, headers=req_headers, params=params, json=json, data=data,
                    timeout=timeout or self._timeout,
                )
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                kind, msg = self._classify(exc)
                if kind in (KIND_TIMEOUT, KIND_CONNECT) and attempt < attempts - 1:
                    await asyncio.sleep(self._retry_delay * (2 ** attempt))
                    continue
                elapsed = int((time.monotonic() - start) * 1000)
                logger.info("HTTP %s %s -> %s (%s)", method, url, kind, msg)
                return HttpResult(url=url, error=msg, error_kind=kind, elapsed_ms=elapsed)

            if resp.status_code in RETRYABLE_STATUS and attempt < attempts - 1:
                await asyncio.sleep(self._retry_delay * (2 ** attempt))
                continue

            elapsed = int((time.monotonic() - start) * 1000)
            result = HttpResult(
                url=str(resp.url),
                status=resp.status_code,
                ok=resp.is_success,
                headers=dict(resp.headers),
                elapsed_ms=elapsed,
            )
            ctype = resp.headers.get("content-type", "")
            body = resp.text
            result.text = body[:20000] if body else ""
            if "json" in ctype or (body and body[:1] in ("{", "[")):
                try:
                    result.json = resp.json()
                except Exception:  # noqa: BLE001
                    result.error_kind = KIND_DECODE
                    result.error = "response was not valid JSON"
            if not resp.is_success:
                result.error_kind = result.error_kind or KIND_HTTP
                result.error = result.error or f"HTTP {resp.status_code}"
            logger.info("HTTP %s %s -> %s (%dms)", method, url, resp.status_code, elapsed)
            return result

        # Exhausted retries on a transient exception
        kind, msg = self._classify(last_exc) if last_exc else (KIND_OTHER, "unknown error")
        return HttpResult(url=url, error=msg, error_kind=kind,
                          elapsed_ms=int((time.monotonic() - start) * 1000))

    async def get_json(self, url: str, **kwargs: Any) -> HttpResult:
        return await self.request("GET", url, **kwargs)
