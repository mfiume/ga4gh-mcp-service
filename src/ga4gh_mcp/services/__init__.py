"""Type-aware service plugins. Importing this package registers all built-in plugins."""

from . import beacon, data_connect, drs, tes, trs  # noqa: F401  (side effect: register plugins)
from .base import (
    ServiceTypePlugin,
    all_plugins,
    api_base,
    call_api,
    get_plugin,
    plugin_for_artifact,
    register,
)

__all__ = [
    "ServiceTypePlugin",
    "all_plugins",
    "api_base",
    "call_api",
    "get_plugin",
    "plugin_for_artifact",
    "register",
    "drs",
    "trs",
    "tes",
    "beacon",
    "data_connect",
]
