"""Conversation capture adapters."""

from .base import (
    AdapterResult,
    BaseAdapter,
    AdapterRegistry,
    adapter_config_path,
    install_adapter_config,
    load_adapter_config,
    sync_adapters,
)

__all__ = [
    "AdapterResult",
    "BaseAdapter",
    "AdapterRegistry",
    "adapter_config_path",
    "install_adapter_config",
    "load_adapter_config",
    "sync_adapters",
]
