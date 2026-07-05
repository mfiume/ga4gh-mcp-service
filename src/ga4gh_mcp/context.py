"""Shared runtime container: one HTTP client, registry client, and auth resolver."""

from __future__ import annotations

from dataclasses import dataclass

from .auth.resolver import AuthResolver
from .config import Settings
from .http_client import Ga4ghHttpClient
from .registry import RegistryClient


@dataclass
class ServerContext:
    settings: Settings
    http: Ga4ghHttpClient
    registry: RegistryClient
    resolver: AuthResolver

    @classmethod
    def create(cls, settings: Settings) -> "ServerContext":
        http = Ga4ghHttpClient(settings)
        return cls(
            settings=settings,
            http=http,
            registry=RegistryClient(http, settings),
            resolver=AuthResolver(settings, http),
        )

    async def aclose(self) -> None:
        await self.http.aclose()
