"""Moneta — memory substrate built on OpenUSD's composition engine.

Phase 1: ECS hot tier + four-operation agent API. Phase 3: real USD
authoring. The agent-facing surface lives as instance methods on the
:class:`Moneta` handle; per DEEP_THINK_BRIEF_substrate_handle.md
multi-instance is supported by construction (each handle owns its
``storage_uri``).
"""
from .api import (
    Moneta,
    MonetaConfig,
    MonetaResourceLockedError,
    ProtectedQuotaExceededError,
    smoke_check,
)
from .types import EntityState, Memory
from ._native import (
    NativeConfigError,
    NativeSeamError,
    NativeStatus,
    NativeUnavailableError,
    NativeWheel,
    SeamStatus,
)
from ._build import BuildInfo, build_info

__all__ = [
    # Substrate handle (DEEP_THINK_BRIEF §5.1, §5.3)
    "Moneta",
    "MonetaConfig",
    # Errors
    "MonetaResourceLockedError",
    "ProtectedQuotaExceededError",
    "NativeConfigError",
    "NativeUnavailableError",
    "NativeSeamError",
    # Native observability (moneta._native, moneta._build)
    "NativeWheel",
    "NativeStatus",
    "SeamStatus",
    "build_info",
    "BuildInfo",
    # Free-function smoke check (constructs its own ephemeral handle)
    "smoke_check",
    # Types
    "Memory",
    "EntityState",
]
