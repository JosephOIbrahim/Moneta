"""USD adapters for Moneta v5. Importing this package requires ``pxr``.

- :class:`UsdPolicyResolver` resolves context policy through a real USD
  sublayer stack (composition doing the load-bearing work).
- :func:`project_generation` writes the recallable records of one
  generation as typed ``MonetaMemory`` prims, a derived and rebuildable
  view of the journal.
"""

from .policy import UsdPolicyResolver, author_policy_layers
from .projection import project_generation

__all__ = ["UsdPolicyResolver", "author_policy_layers", "project_generation"]
