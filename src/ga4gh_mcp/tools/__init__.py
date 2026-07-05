"""MCP tool registration."""

from __future__ import annotations

from . import (
    auth_tools,
    drs_tools,
    registry_tools,
    service_tools,
    trs_tools,
    wes_tools,
)

REGISTRARS = [
    registry_tools.register,
    service_tools.register,
    drs_tools.register,
    trs_tools.register,
    wes_tools.register,
    auth_tools.register,
]


def register_all(mcp) -> None:
    for register in REGISTRARS:
        register(mcp)
