# Moneta in the SYNAPSE memory LOOP

This records the existing integration shipped in
[SYNAPSE v5.67.2](https://github.com/JosephOIbrahim/Synapse/releases/tag/v5.67.2).
Moneta supplies durable advisory memory: a later artist-requested operation can
recall the outcome of an earlier one. The integration required host-side repairs
in SYNAPSE; it did not require a change to Moneta's core API.

## Qualified sources

| Component | Source used for qualification |
|---|---|
| SYNAPSE | [v5.67.2, `7d121ea1`](https://github.com/JosephOIbrahim/Synapse/commit/7d121ea1d3abbd4847f277399514c80a639b25b1) |
| Moneta | [v1.2.0-rc3, `c4a6218`](https://github.com/JosephOIbrahim/Moneta/commit/c4a6218aabde668a7499cc7efd32e0e48e78bf83) |
| Hanish | [v0.2.0, `b82e334`](https://github.com/JosephOIbrahim/Hanish/commit/b82e33492282911d22b5eb4091596c1eb88160da) |
| Octavius | [`1fbc090`](https://github.com/JosephOIbrahim/Octavius/commit/1fbc0907cb3dcec345d40c601ef9b2221480365d) |

The real-substrate checks used Houdini 22.0.400's Python 3.13 and USD 0.26.5.
At the Moneta commit above, `pyproject.toml` still declares `1.2.0rc1`; the
qualified source is identified by its Git commit and tag, not by package metadata
alone. This record makes no claim about untested later revisions.

## Ownership and persistence

SYNAPSE owns the live project's `MonetaBackedStore`. Its LOOP port borrows that
existing owner on Houdini's main thread. It does not construct or close a second
handle for the same storage URI. Panel reload keeps the backend owner alive;
an unrelated scene address or unavailable owner produces an explicit unavailable
result. These host rules preserve Moneta's existing handle lifecycle.

The cycle is: Moneta recall, private Octavius context composition, a Hanish
forecast recorded before dispatch, the observed handler result, and a protected
Moneta feedback capsule. SYNAPSE supplies stable capsule identities and bounded
outbox recovery. Delivery retries do not repeat the artist's scene action.
Hanish remains the authoritative forecast/outcome ledger; Moneta makes that
evidence available as advisory context.

The qualified persistence path includes SYNAPSE's wrapper-managed snapshot and
restore. This is not qualification of native Moneta cold-tier USD hydration or
typed-memory composition in an artist's production stage. Moneta, Hanish and
Octavius do not import each other's Python packages in this integration.

## Artist control

The host LOOP is off by default and requires explicit local configuration.
Remembering an outcome grants no permission to choose the next action, modify an
approved network, or train a model. Imported Solaris notes retain their source
provenance and reference-only status; a lecture claim is not a tested recipe.

Use SYNAPSE's [configuration and recovery guide](https://github.com/JosephOIbrahim/Synapse/blob/v5.67.2/docs/MEMORY_LOOP_REPAIR.md)
for enable/disable settings and ownership behavior. Do not copy scene memory or
runtime ledgers into this repository as integration evidence.

## Verification when this seam changes

Run the consumer's [real-substrate integration checks](https://github.com/JosephOIbrahim/Synapse/blob/v5.67.2/tests/test_loop_integration.py)
from the pinned SYNAPSE checkout. Set `MONETA_SRC` to this checkout's `src`, and
set `SYNAPSE_TEST_LOOP_PYTHON`, `SYNAPSE_TEST_HANISH_ROOT` and
`SYNAPSE_TEST_OCTAVIUS_ROOT` to the qualified runtime and source checkouts.

```text
python -m pytest tests/test_loop_integration.py tests/test_loop_contracts.py -q
```

These checks exercise the second operation, reopen, ownership, failed delivery
and recovery. Missing optional runtimes produce explicit skips, which do not
qualify the real-substrate path. The [release qualification](https://github.com/JosephOIbrahim/Synapse/releases/tag/v5.67.2)
states the live observations and limits; it does not establish production-scale
latency, arbitrary Solaris graph correctness, or predictive learning.
