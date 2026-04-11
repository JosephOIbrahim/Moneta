"""Moneta — memory substrate built on OpenUSD's composition engine.

Phase 1: ECS hot tier + four-operation agent API. Zero USD dependency.
See ARCHITECTURE.md for the locked specification.
"""
from .api import (
    MonetaConfig,
    MonetaNotInitializedError,
    ProtectedQuotaExceededError,
    deposit,
    get_consolidation_manifest,
    init,
    query,
    run_sleep_pass,
    signal_attention,
    smoke_check,
)
from .types import EntityState, Memory

__all__ = [
    # Four-op API (ARCHITECTURE.md §2)
    "deposit",
    "query",
    "signal_attention",
    "get_consolidation_manifest",
    # Harness-level (not part of the agent surface)
    "init",
    "run_sleep_pass",
    "smoke_check",
    "MonetaConfig",
    # Types
    "Memory",
    "EntityState",
    # Errors
    "MonetaNotInitializedError",
    "ProtectedQuotaExceededError",
]
