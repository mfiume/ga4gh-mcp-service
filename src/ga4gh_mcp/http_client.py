"""Shared async HTTP client with timeouts, bounded retries, and failure classification.

Every outbound call to a GA4GH service goes through here so that the wide variety of
real-world failures (DNS misses, private IPs, TLS mismatches, 401 challenges, HTML error
pages) become *structured* outcomes instead of exceptions that could crash a tool.
"""

from __future__ import annotations

import asyncio
import socket
import ssl
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from .config import Settings
from .errors import Liveness

# HTTP statuses worth retrying (transient).
_RETRY_STATUS = {429, 500, 502, 503, 504}


@dataclass
class HttpResult:
    url: str
    liveness: Liveness
    status: int | None = None
    latency_ms: int | None = None
    headers: dict[str, str] = field(default_factory=dict)
    json: Any = None
    text: str | None = None
    error: str | None = None

    @property
    def reachable(self) -> bool:
        return self.liveness in (
            Liveness.LIVE,
            Liveness.AUTH_REQUIRED,
            Liveness.HTTP_ERROR,
            Liveness.INVALID_RESPONSE,
        )


def _walk_causes(exc: BaseException):
    seen = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        yield cur
        cur = cur.__cause__ or cur.__context__


def classify_exception(exc: Exception) -> tuple[Liveness, str]:
    """Map an httpx/transport exception to a structured liveness + message."""
    # Timeouts first (httpx.TimeoutException covers connect/read/write/pool).
    if isinstance(exc, httpx.TimeoutException):
        return Liveness.TIMEOUT, f"timeout: {exc!s} ({type(exc).__name__})"
    # Inspect the cause chain for DNS / TLS roots.
    for cause in _walk_causes(exc):
        if isinstance(cause, ssl.SSLError):
            return Liveness.TLS_ERROR, f"tls error: {cause!s}"
        if isinstance(cause, socket.gaierror):
            return Liveness.UNREACHABLE_DNS, f"dns resolution failed: {cause!s}"
    msg = str(exc) or type(exc).__name__
    low = msg.lower()
    if "ssl" in low or "certificate" in low or "wrong_version_number" in low:
        return Liveness.TLS_ERROR, f"tls error: {msg}"
    if "nodename nor servname" in low or "name or service not known" in low or "getaddrinfo" in low:
        return Liveness.UNREACHABLE_DNS, f"dns resolution failed: {msg}"
    if isinstance(exc, httpx.ConnectError):
        return Liveness.CONNECTION_ERROR, f"connection error: {msg}"
    return Liveness.CONNECTION_ERROR, f"{type(exc).__name__}: {msg}"


class Ga4ghHttpClient:
    """Thin async wrapper around a single shared ``httpx.AsyncClient``."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: httpx.AsyncClient | None = None

    def _ensure(self) -> httpx.AsyncClient:
        if self._client is None:
            timeout = httpx.Timeout(
                connect=self._settings.connect_timeout,
                read=self._settings.read_timeout,
                write=self._settings.read_timeout,
                pool=self._settings.connect_timeout,
            )
            self._client = httpx.AsyncClient(
                timeout=timeout,
                verify=self._settings.verify_tls,
                follow_redirects=True,
                headers={
                    "User-Agent": self._settings.user_agent,
                    "Accept": "application/json",
                },
                limits=httpx.Limits(max_connections=32, max_keepalive_connections=16),
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
        data: dict[str, Any] | None = None,
    ) -> HttpResult:
        client = self._ensure()
        attempts = self._settings.max_retries + 1
        last: HttpResult | None = None
        for attempt in range(attempts):
            start = time.monotonic()
            try:
                resp = await client.request(
                    method.upper(), url, headers=headers, params=params,
                    json=json_body, data=data,
                )
            except Exception as exc:  # noqa: BLE001 - deliberately broad; classify below
                liveness, msg = classify_exception(exc)
                last = HttpResult(url=url, liveness=liveness, error=msg,
                                  latency_ms=int((time.monotonic() - start) * 1000))
                # DNS/TLS are deterministic — no point retrying.
                if liveness in (Liveness.UNREACHABLE_DNS, Liveness.TLS_ERROR):
                    return last
                if attempt < attempts - 1:
                    await asyncio.sleep(self._settings.retry_backoff * (2 ** attempt))
                    continue
                return last

            latency = int((time.monotonic() - start) * 1000)
            result = self._build_result(url, resp, latency)
            if resp.status_code in _RETRY_STATUS and attempt < attempts - 1:
                delay = self._retry_after(resp) or self._settings.retry_backoff * (2 ** attempt)
                last = result
                await asyncio.sleep(delay)
                continue
            return result
        assert last is not None
        return last

    def _build_result(self, url: str, resp: httpx.Response, latency: int) -> HttpResult:
        # Bound how much we buffer/parse from any single upstream.
        text = resp.text[: self._settings.max_response_bytes]
        parsed: Any = None
        try:
            parsed = resp.json()
        except Exception:  # noqa: BLE001 - non-JSON bodies are common and expected
            parsed = None

        status = resp.status_code
        if status in (401, 403):
            liveness = Liveness.AUTH_REQUIRED
        elif status >= 400:
            liveness = Liveness.HTTP_ERROR
        elif parsed is None:
            liveness = Liveness.INVALID_RESPONSE
        else:
            liveness = Liveness.LIVE
        return HttpResult(
            url=str(resp.url),
            liveness=liveness,
            status=status,
            latency_ms=latency,
            headers={k.lower(): v for k, v in resp.headers.items()},
            json=parsed,
            text=None if parsed is not None else text,
        )

    @staticmethod
    def _retry_after(resp: httpx.Response) -> float | None:
        ra = resp.headers.get("retry-after")
        if not ra:
            return None
        try:
            return min(float(ra), 10.0)  # cap to keep tools responsive
        except ValueError:
            return None

    async def get_json(self, url: str, *, headers: dict[str, str] | None = None,
                       params: dict[str, Any] | None = None) -> HttpResult:
        return await self.request("GET", url, headers=headers, params=params)
