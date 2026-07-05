"""Type-aware GA4GH service clients and the service-type plugin registry."""

from .drs import DRSClient
from .trs import TRSClient
from .wes import WESClient

__all__ = ["DRSClient", "TRSClient", "WESClient"]
