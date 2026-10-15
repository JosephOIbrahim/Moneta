# Moneta v6 — Blueprint

**Status:** design only. Nothing in v6 is built. It assumes Moneta v5 lands as proposed, which hasn't happened yet.

**Date:** 15 October 2026 · **Owner:** Joseph Ibrahim · **Builds on:** Moneta v5 (branch `v5`, a git bundle from 22 September, not merged) and the RSI-in-USD prototype (12 October)

**Tags:**
- `[V]` verified by running code, by a test, or by reading the named source; each tag says which.
- `[P]` proposed here.
- `[U]` unmeasured or unknown.
- `[A]` assumed here and not yet true.

This document is written to stand alone, for a reviewer who has seen none of the earlier work. An independent review of the first draft has been applied. The changes it prompted haven't been reviewed yet (§16).

---

## On one screen

**What v6 is.** Moneta v5 is a memory substrate for AI agents. It keeps an append-only journal of everything the agent was told, with pure, explainable recall on top. v6 adds a governed loop that tunes *how* memory is recalled. The loop never touches *what* was remembered.

**The line.** The loop may only change what moving a pointer can undo. That means read-time policy, never anything that writes the journal as an effect. Hosts act on what they're shown, so a policy change can still have effects downstream. The substrate therefore holds every irreversible effect until the owner adopts or rolls back the change that influenced it (§4).

**Why it's possible.** v5's reads are pure. Given the journal and a logged query, an answer can be recomputed exactly under any candidate policy. That replay is the referee.

**What's hard.** Labels. The first host, SYNAPSE, signals attention on its own top five results after every search. So attention today records what ranked well, not what got used `[V]`. SYNAPSE also uses Moneta only to fill a 50-candidate pool that it reranks itself `[V]`. A loop trained on today's signals would learn to agree with itself.

**The one experiment.** A synthetic world where the best setting is known by brute force. One knob, a recall half-life, is tuned under five label sources and two host shapes. It runs in Python, needs no changes to Moneta, and can kill the idea (§12).

**The one ask.** Go or no-go on that experiment. The architecture rulings in §13 wait for its report.

**Position.** This paper is mile 1 of 6. Mile 0, landing v5, isn't done, but the experiment doesn't need it.

---

## 1. Where this comes from

| When | What | Status |
|---|---|---|
| through Aug 2026 | **Moneta v1**, the `1.2.0-rc` line. Four agent ops (`deposit`, `query`, `signal_attention`, `get_consolidation_manifest`). Lazy exponential decay of a per-memory utility. USD as a cold tier. A locked spec, changeable only through a formal escalation round. | release candidates |
| 8 Sep | **The v4 spine.** Memory needs five things: record, context, policy, generation, operation. Records don't compose; policy does. No USD type appears in any core signature. | design |
| 8 Sep | **Decisions D1–D5.** Rust comes in only if a native scan in Python (arm P) misses its latency gate. USD's first job is resolving policy, not storing truth. oxideav-usdz, a third-party pure-Rust USD library, is parked. | design |
| 22 Sep | **Moneta v5.** The journal is the database, reads are pure, and records don't compose. About 3,150 lines and 124 new tests; 273 pass under OpenUSD 26.08 `[V, v5 blueprint]`. Of SYNAPSE 5.80.0's 253 Moneta tests, 237 pass against the v5 facade with SYNAPSE untouched. With two test helpers re-pointed, 247 pass, and the other 6 assert v1's data loss `[V, v5 SYNAPSE_COMPAT]`. | built, **not merged**: `main` is still at `6cf05f5` `[V, git ls-remote, 15 Oct]` |
| 12 Oct | **RSI-in-USD, mile 3.** A self-improving loop and its governing law in one USD file, on a curve-fitting toy. 18 checks pass, all 21 deliberate sabotages are caught, and a red team landed 0 writes in 608 attempts `[V, mile 3 package]`. | prototype |
| 12 Oct | **A Jev client.** Jev is TypeSafe's typed-judgment model. The client is pinned to `jev-1.13.0`, records every verdict under its exact request, and passed 8 of 8 offline tests `[V, run 12 Oct]`. | never run live |

**Everything here assumes v5 lands `[A]`.** v5 changes four locked decisions (E1–E4, §14) and makes one smaller call about the half-life. The repo's rules require a ruling on each, and none has been made. v5's first real cutover test hasn't run either: its facade against a copy of a real 841-record SYNAPSE store preserved from a 17 September incident.

**From the prototype, v6 keeps the rules and drops the storage.** It keeps:
- the typed proposal language
- the pinned, import-free WASM referee
- the scoring budget and the held-out set
- rollback as a verified repoint
- sabotage testing

It drops the prototype's chain of USD layers, which existed only because that file had no journal. It also drops the prototype's cost figure of about 3 ms per USD text layer. Journal replay has to be measured on its own.

---

## 2. First principles

**The requirement.** A memory that:
- keeps everything it was told
- answers exactly and explainably
- gets better at answering without hand-tuning

Every improvement must be reversible, judged by something the memory can't touch, and re-derivable from its records.

Merging v5's three facts with the prototype's four principles leaves five.

**1. History is append-only, and the present is a pointer.** Nothing is ever edited. "Current" is a position in the journal.

**2. Reads are pure, so every answer and every verdict can be re-derived.** A read never writes, and the same inputs give the same answer, ties included. A referee's score works the same way.

**3. Records don't compose; policy does.** Two contradictory memories are two separate things, each with its own provenance. Composition does its real work on opinions about how to answer, such as which scopes a context admits or which claim wins a slot.

**4. Nothing judges itself.** Whatever decides that a change is better sits outside the reach of the thing being changed. The chain of judges ends on something the system can't write to: a pinned referee, a held-out window, or the owner's key.

**5. The loop's only power is a typed proposal.** It returns a value and never holds a handle.

Four facts about the world constrain the rules.

- **(a) A judge sees only what it measures.** Whatever the referee doesn't measure can get worse while every score improves.
- **(b) Scores leak the test.** A loop that sees its scores learns about the eval set without ever seeing it.
- **(c) You can only react to what you were shown.** Attention lands only on returned results, so labels drawn from it lean toward whatever the old policy surfaced.
- **(d) Replay has a cost, and it has to be measured where it happens.**

---

## 3. What the code says

Four facts from source decide v6's shape.

**v5 doesn't journal queries.** Its journal records deposits, attention, retention, consolidation, tombstones, erasures, re-embeddings and notes, and nothing else `[V, v5 blueprint §4]`. That's right for pure reads, but it means the store alone can't say what was asked. The host must keep a query log (§6).

**A v5 read depends on more than its echo.** `recall` takes five inputs: the query embedding, a limit, a context, the caller's allowed scopes and a time. The echo carries only the sequence number, the time, the context and a fingerprint of the resolved policy `[V, v5 code]`. The caller's scopes even change slot outcomes, because records the caller may not see are removed before a slot's winner is picked `[V, v5 code]`. So exact replay needs the full query, not just the echo.

**SYNAPSE's attention is an echo of retrieval.** After each successful vector search on a text query, SYNAPSE signals attention on its own top five reranked results. Each is weighted by SYNAPSE's reranker score, capped at 1 `[V, read in python/synapse/memory/moneta_store.py at e7a2e1e, VERSION 5.97.2; not run]`. So attention means "ranked well," not "was used." Attention also raises utility, so what ranks well may keep ranking well. That last part is a hypothesis `[U]`.

**SYNAPSE uses Moneta to fill a pool, not to set an order.** It asks Moneta for `max(3 × limit, 50)` results, then reranks them with its own tag, keyword and text-match scorer. Ties break by recency, then by id. Candidates that score zero, or fail its type, tag, tier, source or date filters, are dropped `[V, same file]`. Moneta's order never reaches the agent. For this host, the most Moneta can do is put the needed memory in the pool, so pool recall is an upper bound on what the agent can see.

So v6's labels can't come from today's attention. And the metric has to match how each host consumes recall, which makes it the owner's to set (§6).

---

## 4. The line

**The derivation.** A read has no side effects (principle 2), and the live policy is a pointer (principle 1). So moving the pointer back undoes any change confined to read-time policy. Every answer, at every sequence number, time and context, returns to exactly what it was. A change that writes the journal as an effect can't be undone that way. A tombstone stays in history, and an erase destroys bytes.

**The loop may only change what moving a pointer can undo.**

| Tier | Changed by | Contents | How |
|---|---|---|---|
| Fixed ceilings | nobody: they live in code | the line itself, size limits, referee fuel and memory, the typed-diff language | a new release |
| Constitution | the owner | the referee module and its metric, the eval set, the holdout rule, bounds on every tunable, the budget, the margin rule, the retention policy and its half-life | an owner-signed amendment `[P]` |
| Rules | the owner; later, amendments judged on the held-out window | how the tuner searches: step sizes, candidates per pass, which values are open | an amendment |
| Self | the loop | read-time values only; in v6.0, one recall half-life | a typed proposal the referee scores |
| Records | the agent and the owner, never the loop | the journal's record events | the four agent ops and the owner's operator ops |

**Retention stays the owner's.** The thresholds and the retention half-life decide what a sleep pass tombstones. Tombstone, erase, compact and revector all write history. None of them is pointer-reversible.

**The indirect path, and the hold.** A host acts on what it's shown. Under a tuned policy, SYNAPSE would show different results and signal attention on different records. That changes retention utility, so the next sleep pass could tombstone something it otherwise wouldn't `[V, by reading both codebases; not run]`. A tombstone can't be reversed: v5's fold has no path back from it except erasure `[V, v5 code]`. So v6 adds a hold:

- **Every promotion starts a probation.** While a live generation hasn't been adopted by the owner, sleep passes are held and no retention events are written `[P]`.
- **The owner ends probation** by adopting the generation or rolling it back. Adoption is the owner's act, so retention effects after it fall on the owner's side of the line.
- **Attention from probation stays in the journal.** The eval-set builder tags it with the generation that produced the results it answered. A rolled-back generation's influence can then be kept out of later eval sets `[P]`.
- **The cost:** memory grows without retention for as long as probation lasts.

**The half-life must be split before it can be a knob.** v5 uses one half-life for both ranking and retention. When the half-life changes, v5 reinterprets history: anchors are recomputed on replay under the current value `[V, v5 blueprint §5; that call is unruled]`. If the first knob is a recall half-life (R2):

- **Ranking uses the tuned recall half-life.** The sleep pass keeps the owner's retention half-life, and the retention fold stays exactly v5's.
- **Recall utility becomes a second, derived fold.** It replays each record's attention history under the live recall half-life, reinterpreting history the way v5 already does. A repoint rebuilds it in one pass over the attention events `[P; cost U]`.
- **Everything that reports utility keeps retention utility.** That covers the v1 facade's `Memory.utility`, the v1-format `snapshot.json` export SYNAPSE reads, and USD projection. The v6 surface adds `recall_utility`. `explain()` shows both, plus which layer set the recall half-life `[P]`.

If the split is rejected, the fallback knob is an exponent on utility in the ranking score (R2). It changes only how similarity and utility combine, so no second utility is needed.

---

## 5. Architecture: one timeline that carries policy too

```
<store>/
  journal          the only timeline: record events, and every policy change with its content inline
  blobs/<sha>      referee modules and eval sets: large, content-addressed, verified when used
  derived/         index, fold checkpoints, projection, the v1-format export, and the policy
                   layers generated from the journal for USD composition, usdview and Solaris
  drafts/          policy layers the owner edits; recall never reads them
```

**The journal carries policy.** v5's journal stays the authority for records `[A]`. v6 adds two events, and only the substrate writes them `[P]`:

- **`govern`** records a policy change as `{tier, name, why, spec}`.
  - `tier` is context, self, rules or const.
  - `why` is genesis, edit, promote, adopt, rollback, roll-forward or amend.
  - `spec` is the policy content itself, in the validated canonical form v5's two resolvers already share. It is never a pointer to a file.
- **`seal`** records a running SHA-256 of the journal so far, and names a fold checkpoint by its hash.

Policy content is small: scopes, exclusions, slot selections, a few numbers. Because it's carried inline, **the journal alone fixes the policy at every sequence number.** The layer files USD composes are derived from the journal and regenerated, so they can't drift from it `[P]`. Only large things stay outside, content-addressed: referee modules and eval sets. The constitution names them by hash, and they're verified whenever a tuning pass uses them.

**Exact replay, stated precisely.** Take the journal and a logged query: its embedding, limit, context, allowed scopes and time. From those, the answer at that query's sequence number can be reproduced exactly `[P]`. v5 doesn't offer recall at an earlier sequence number today, because recall reads only the live fold `[V, v5 code]`. The eval-set builder adds that (§6).

**This closes a gap v5 leaves open.** In v5, context policy comes from outside the journal and is versioned only by a fingerprint. `reload()` re-reads layers edited in place, for example in Solaris `[V, v5 code]`. So a past query replayed today would get today's scopes and slot selections.

In v6, the owner edits a layer in `drafts/` with any tool. `reload()` becomes a substrate operator op, and before any read can see the change it:
- reads the draft and lints it
- validates it into a spec
- journals a `govern` edit
- regenerates the derived layer

**Why the self needs no chain.** The prototype's self was a long list of values, kept as sparse USD deltas with checkpoints, because the file had no other history. Moneta's tuned self is a handful of numbers. So each generation is one `govern` event, and its history is the journal. With no chain depth, the prototype's folding-cost question doesn't arise for policy.

**Composition does one load-bearing job.** The policy spec gains one typed field, `recallHalfLife`, which only the self tier and the owner may author. In each context's derived policy stack, the self layer is the weakest sublayer. So any owner opinion, in that context or a parent, wins by strength `[P]`. The owner overrides the loop just by writing a value. v5 already shows that its plain Python resolver and its USD resolver agree on 60 random specs `[V]`. v6 extends that test to stacks that include a self layer `[P]`.

**Seals and checkpoints are one mechanism.** v5 opens by replaying the whole journal. That takes about 1.0 s at 10,000 records `[V]` and an estimated 10 s at 100,000 `[U]`.

A `seal` names a checkpoint that holds the retention fold, plus the recall anchors for whatever recall half-life is live at that moment. Opening loads the checkpoint, verifies both hashes, and replays only the tail. A repoint after the seal rebuilds the recall anchors from the attention history. The audit verifies everything from genesis `[P]`. The constitution sets the seal interval, under a ceiling in code, and its cost is measured on the journal itself (fact d) `[U]`.

**Tamper evidence.** v5 frames each journal line with a CRC-32 `[V]`. That catches corruption but not deliberate edits, since anyone can recompute a CRC. The running hash in each seal makes edits to sealed history detectable, and owner signatures would make them attributable (R5) `[P]`.

**Format.** A v6 journal's genesis declares format 6. A v5 reader refuses it rather than skipping events it doesn't know `[P]`.

---

## 6. The referee and the eval set

**The query log is the host's `[P]`.** Reads stay pure, so the host records each query:
- the echo: sequence number, time, context, policy fingerprint
- the caller's allowed scopes
- the exact float64 query embedding
- the limit
- the ids returned
- its own request id

SYNAPSE can't log this today. It still runs on v1, which returns no echo `[V, SYNAPSE imports moneta.Moneta, and v5 is unmerged]`. Logging moves to mile 3.

**The eval set comes from one forward pass.** The builder walks the journal once. When the fold reaches a logged query's sequence number, it computes that query's candidate pool and features. The features are cosines, deposit order, floors, the deposit's initial utility, and the record's raw attention history up to that point. Utility anchors are left out, because an anchor depends on a half-life, and candidates differ in theirs. One pass answers every query `[P]`. The result is a self-contained blob, and a rebuild from the journal and the query log reproduces it byte for byte `[P]`.

**Labels have five possible sources, each with a cost (R3).**

| Source | Strength | Weakness |
|---|---|---|
| Retrieval echo (SYNAPSE today) | already flowing | teaches the loop to agree with itself; unusable |
| Use signals: the host signals attention when a memory is *used* | real and continuous | labels only what was shown (fact c); needs a host change |
| Model labels: a pinned model judges every record in each logged query's candidate pool | covers memories that were never shown | carries the model's biases |
| Owner labels: a small hand-labeled set, including unshown records | the most trusted | small, slow, and costs the owner's attention |
| A mix of use signals and model labels | coverage grounded in use | two pipelines |

**Shown-only labels can't improve a pool host.** Take a host like SYNAPSE, scored on pool recall. Anything labeled from what was shown was already in the incumbent's pool. So the incumbent scores perfectly against those labels, and no candidate can beat it. Only labels on records outside the shown set can move pool recall: model labels on the full candidate pool, or owner labels `[P; follows from the definitions]`.

**Model labels are recorded before use.** Each one is stored with the model's version pin and the hash of its exact request, and replay never calls the model `[P]`. The Jev client's verdict cache already works this way `[V, offline]`.

**The objective belongs to the owner.** Moneta is creative-agnostic: the substrate doesn't decide what "better" means for an application. So the referee module and its metric live in the constitution. Moneta ships one default, nDCG@k over Moneta's own order `[P]`. For a SYNAPSE-shaped host, the owner swaps in pool recall by amendment.

**The holdout is the future.** The constitution splits queries by time: up to T₁ is train, and T₁ to T₂ is held out.
- The loop sees only its own train scores, within a budget.
- The substrate computes the held-out score and records it as a tripwire. The loop never sees it.
- When the held-out window wears out, an amendment rolls both dates forward.
- A label may only use events inside its own query's window.

Check V-HOLDOUT enforces the split and the label window `[P]`.

**The candidate pool can be exact `[P]`.** Every tunable has bounds. Suppose a record's score is monotone in each tunable. Then its range over the bounds is found at their corners. Any record whose best case can't reach the top k under any allowed value can be left out.

For the recall half-life, the argument goes like this:
- Each step of the attention fold preserves order: decay with the floor, add the weight, clamp to 1.
- Decay is non-increasing in the half-life's rate.
- v1's decay formula, which v5 imports unchanged, clamps a negative time step to zero. So out-of-order attention can't run decay backwards `[V, src/moneta/decay.py at 6cf05f5]`.

That is an argument, not a proof. The bounds are widened by a few ulps. Conformance test **V-POOL** checks the claim directly: for random values in bounds, the referee's top k must equal the read path's.

**`exp()` threatens exactness `[U]`.** Rust compiled to WASM without a standard library needs its own `exp`, typically a port of a math library such as `libm`. Neither that `exp` nor the platform one Python uses is correctly rounded. They can differ in the last bit, which can flip a near-tie. A numpy-vectorized scan (arm P) would change Python's own `exp` the same way. There are two ways out:
- the read path and the referee share one implementation, or
- exactness is defined up to ties within one ulp.

Check **V-EXP** counts disagreements on a real eval set.

**The referee runs the prototype's way** (`[V]` on the toy, `[P]` here).
- It's a WASM module, named in the constitution and pinned by hash in the substrate's trust store.
- It has zero imports, fuel and memory caps, and a fresh instance per call.
- It reads one flat buffer of pool features, labels and candidate values, and returns one number.
- A non-finite result counts as a rejection.

The toy's caps were 20 million fuel units and 8 MB. Mile 2 measures what a realistic eval set needs `[U]`.

**The margin comes from measured noise `[P]`.** A candidate promotes only if a paired bootstrap over eval queries puts its gain above zero, at the confidence the constitution sets. Queries within one session are correlated, so the bootstrap resamples whole sessions `[U]`.

**Tripwires watch what the referee doesn't (fact a) `[P]`.** They track:
- per-context scores, since a global gain can hide a local loss
- the held-out window
- whether protected records stay visible
- latency
- result variety

Tripwires are recorded, never scored, and never shown to the loop.

---

## 7. One tuning pass, one rollback

A tuning pass is a harness-level operator pass, like v5's `run_sleep_pass()`. The four agent ops don't change.

1. **Verify.** The constitution and rules are read from the journal. The referee module's hash must be in the trust store, and the eval set's hash must match the constitution.
2. **Build the view.** It holds the open names, their bounds, the current values and the tuner's last few scores. Nothing else.
3. **The tuner proposes,** for example `{"tier": "self", "set": {"recallHalfLife": 1209600.0}}`. The substrate parses it strictly and checks types and bounds.
4. **The referee scores** the candidate and the current head on the train window. The call counts against the budget.
5. **The margin rule decides.** In v6.0, a winner is recorded as a proposed promotion, with its evidence: scores, bootstrap interval, tripwires and hashes. The pointer stays put until the owner moves it (R4).
6. **On promotion,** the substrate appends `govern{tier: self, why: promote, spec}`. Probation starts, sleep passes are held, and the recall anchors are rebuilt.
7. **The owner ends probation** with `govern{why: adopt}` or with a rollback.

**Rollback** appends `govern{tier: self, why: rollback, spec}`. This restores an earlier generation's spec exactly as an earlier `govern` event recorded it. The content comes from the journal itself, so there's no separate file to forge. Rolling forward works the same way.

---

## 8. Rules

The rules are grouped by principle:
- **T:** the timeline
- **P:** purity
- **C:** composition
- **J:** judging
- **L:** the loop's limits
- **X:** ceilings in code

| ID | Rule | Tag |
|---|---|---|
| **T1** | The journal is the only timeline. Every record event and every policy change is one appended event, and nothing is edited. | `[V]` records (v5) · `[P]` policy |
| **T2** | A `govern` event carries its policy content inline. Policy layer files are derived from the journal and regenerated, never trusted. | `[P]` |
| **T3** | Owner edits join the timeline. `reload()`, as a substrate operator op, lints and journals a draft before any read can see it. | `[P]` |
| **T4** | Rollback and roll-forward append `govern` events that restore a spec an earlier event recorded. | `[P]`; pattern `[V]` on the toy |
| **T5** | A `seal` records a running hash and names a fold checkpoint. Opening verifies from the last seal; the audit verifies from genesis. | `[P]` |
| **P1** | A read depends only on the journal prefix, the query embedding, the limit, the context, the caller's scopes and the time. | `[V]` for v5's inputs · `[P]` policy fixed by the prefix |
| **P2** | The host logs every input in P1 with each query. The builder answers logged queries at their own prefixes in one forward pass, and a rebuild is byte-identical. | `[P]` |
| **P3** | A verdict depends only on the referee's bytes, the eval set's bytes and the candidate's values, and it reproduces in a fresh process. | `[P]`; `[V]` on the toy |
| **P4** | A model label is recorded with its version pin and request hash before use. Replay never calls the model. | `[P]`; cache `[V]` offline |
| **C1** | Tuned values sit in the weakest sublayer of every context's stack, so any owner opinion wins by strength. | `[P]` |
| **C2** | The self tier can't author records, scopes, exclusions or slot selections. | `[P]` |
| **C3** | The plain and USD resolvers agree on resolved policy, including stacks with a self layer. | `[V]` without one (v5) · `[P]` with one |
| **J1** | The referee is a WASM module named in the constitution and pinned in the trust store. It has zero imports, fuel and memory caps, and a fresh instance per call. | `[V]` on the toy |
| **J2** | The owner's constitution holds the objective: the referee module, the metric, the eval set and the holdout rule. nDCG@k is the default. | `[P]` |
| **J3** | The tuner's view never holds labels, held-out queries, the referee or the constitution. It holds only its own recent scores, within a budget. | `[P]`; `[V]` on the toy |
| **J4** | A candidate promotes only past a margin taken from a paired bootstrap of measured noise. | `[P]` |
| **J5** | Tripwires record what the referee doesn't measure. They are never scored and never shown to the loop. | `[P]` |
| **J6** | In v6.0, only the owner moves the pointer. | `[P]` |
| **J7** | While an unadopted generation is live, sleep passes are held. | `[P]` |
| **L1** | The line: the self tier holds read-time values only. Anything that writes the journal as an effect belongs to the owner. | `[P]` |
| **L2** | A proposal is `{"tier": "self", "set": {name: number}}`. It's checked for exact types, open names, and finite values in bounds. Text is size-capped and parsed strictly. | `[V]` on the toy |
| **L3** | Only the substrate writes the journal. The tuner never holds a handle. | `[V]` single writer (v5) and on the toy |
| **X1** | Some ceilings no constitution can raise: diff size and op count, referee fuel and memory, eval-set size, budget, seal interval. | `[P]`; values `[U]` |
| **X2** | The substrate refuses a journal whose genesis declares a format it doesn't implement. | `[P]` |

---

## 9. Checks and their sabotages

Each check must pass with its safeguard in place, and fail when that safeguard is deliberately broken. A green check means nothing until its sabotage is caught.

v5's eight invariants still apply unchanged:
- **I1** recoverability
- **I2** generation purity
- **I3** append-only claims
- **I4** no silent empties
- **I5** authorization only narrows
- **I6** determinism
- **I7** four distinct states
- **I8** ordering without the GIL

| Check | Rules | Pass condition | Sabotage it must catch |
|---|---|---|---|
| V-UNDO | T4, L1 | At a pinned sequence number and time, every answer for a probe set is identical before promotion and after rollback. | a tunable that also feeds retention |
| V-HOLD | J7 | No retention event is written while an unadopted generation is live. | a sleep pass allowed during probation |
| V-TIMELINE | T1–T3 | After an owner edit, an old query replays with the old context policy. | `reload()` serving the draft before journaling it |
| V-DERIVED | T2 | Deleting or editing a derived layer file changes no answer, because it's regenerated. | a resolver that reads the files instead of the journal |
| V-POOL | P2 | For random in-bounds values, the referee's top k equals the read path's. | bounds taken at one corner, or the negative-time clamp removed |
| V-EXP | P3 | WASM and host utilities never disagree on order beyond the declared tolerance. | a less accurate `exp` swapped in |
| V-PIN | J1 | An unpinned referee is refused. | the pin check turned off |
| V-VIEW | J3 | The view holds only open names, bounds, values and recent scores. | labels leaked into the view |
| V-MARGIN | J4 | A candidate that differs from the head only by noise never promotes in 1,000 tries. | the margin set to zero |
| V-OWNER | C1 | An owner value wins in its context and every child. | the self layer placed strongest |
| V-WRITE | L1, L3 | A tuning pass appends only `govern` events. | the tuner calling tombstone |
| V-DIFF | L2 | The prototype's red-team suite, ported, lands zero writes. | a permissive parser |
| V-SEAL | T5 | An edit to sealed history fails the audit, and an edit after the last seal fails at open. | a seal written without the running hash |
| V-REPLAY | P3, P4 | A fresh process reproduces every recorded verdict. | a referee with unseeded noise |
| V-SHADOW | J6 | With live promotion off, the pointer never moves in a full run. | the flag ignored |
| V-HOLDOUT | §6 | No held-out query reaches train, and no label uses events outside its query's window. | splitting by deposit time instead of query time |

---

## 10. Where Rust fits

v5's rule holds: Rust goes behind a pure seam with an exact oracle, where it buys speed or a guarantee the host can't otherwise give.

- **The referee: Rust compiled to WASM `[P]`.** Its guarantee comes from the sandbox, not the language. Rust is the natural source because it compiles with no standard library and no runtime. Mile 2's Python referee is its exact oracle, checked by V-POOL and V-EXP.
- **The verifier `[P]`.** The seal walk and the audit are pure functions of bytes, with Python versions as their oracles. The audit is where the time goes.
- **The scan, unchanged `[V, decision D1]`.** Arm P comes first. Rust follows only if arm P misses the 50 ms p95 query gate in Moneta's benchmark plan. v5's query takes 161 ms at 10,000 records on a 2-vCPU container, about 3× over that gate `[V]`.
- **The amendment channel, with types as a second fence `[P]`.** An amendment moves `Draft → Measured → Signed → Enacted`, and only an `Enacted` value can be written. Types guard against the substrate's own bugs. Trust between machines comes from signatures.
- **Composition stays with Pixar's USD.** oxideav-usdz stays parked.

---

## 11. Measured cost, and what isn't measured

The `[V]` figures are single runs on a 2-vCPU cloud container, not the owner's workstation.

| What | Result | Tag |
|---|---|---|
| v5: make one deposit durable | 0.43 ms (v1: 3.26 s, for SYNAPSE's snapshot on every add) | `[V]` |
| v5: query, top 10, 10k records at 384 dims | 161 ms median (v1: 345 ms) | `[V]` |
| v5: open 10k records | 1.0 s | `[V]` |
| v5: journal at 10k records | 42.6 MB | `[V]` |
| Prototype: honest loop, 3,000 proposals | training error down 94.6%; held-out error 0.395 → 0.024 | `[V]` on the toy |
| v5: open 100k records | about 10 s, estimated | `[U]` |
| A referee call on a realistic eval set | — | `[U]`, mile 2 |
| Building an eval set from a real journal | — | `[U]`, mile 3 |
| Rebuilding recall anchors on a repoint | — | `[U]` |
| How far the knob moves SYNAPSE's pool recall | — | `[U]`: mile 2 in simulation, mile 3 on a real store |

---

## 12. Mile map and the first experiment

| Mile | What | Done means |
|---|---|---|
| 0 | **v5 lands.** Rule on E1–E4 and the half-life call, merge `v5`, and run the facade against a copy of the 841-record store. | rulings recorded and a migration report read `[A]`; not done |
| **1** | **Paper.** This blueprint, the independent review, a second opinion, and the rulings triaged with Jev. | R1–R5 triaged; go or no-go on mile 2 |
| 2 | **The experiment below.** Python only. | a report that passes or kills |
| 3 | **Evidence.** SYNAPSE logs full queries and settles what its attention means. The eval-set builder and validator exist, tuning runs in shadow on real logs, and leverage is measured on a real store. | a real eval set rebuilt byte-identically; shadow verdicts reproduce |
| 4 | **Governance in the store.** `govern` and `seal` events, derived policy layers, the self layer, probation, rollback, the WASM referee, and every §9 check with its sabotage. | §9 green, every sabotage caught |
| 5 | **Live, gated by the owner.** Promotion requests that carry evidence, probation, and a signed constitution. | one promotion, one adoption and one rollback on a real store |
| 6 | **Recursion.** The proposer becomes a WASM module in the rules tier, and changes to it are judged on the held-out window. More knobs arrive only by amendment. | a proposer change promoted on held-out evidence |

**The experiment (mile 2)** runs in a synthetic world where the best setting is known by brute force. So if something fails, the loop failed, not the world.

- **World.** About 5,000 records over 120 simulated days, in topic clusters.
  - Each record's true usefulness decays with a hidden half-life.
  - A record is truly relevant to a query if it shares the query's topic, weighted by its usefulness at that moment.
  - Cluster size relative to the 50-candidate pool is swept, because the SYNAPSE-shaped host's leverage depends on it.
- **Ranking.** v5's ranking math, taken from the branch if the bundle is at hand. Otherwise it's re-implemented and checked against v5's hand-written oracle fixture first.
- **The known answer.** Sweep the recall half-life across its bounds using true labels, and take the best value. Don't assume it equals the world's hidden half-life: Moneta's utility includes attention bumps that the world doesn't, so the two needn't coincide.
- **Two hosts.**
  - One uses Moneta's order directly and is scored by nDCG@10.
  - One is shaped like SYNAPSE: a 50-candidate pool, reranked by a noisy host scorer and scored by pool recall.
- **Five label arms.**
  - **A, oracle:** true relevance on the full candidate pool. The loop must find the swept optimum.
  - **B, echo:** attention on the top five shown, the way SYNAPSE sends it today. This is a negative control, and it should teach nothing.
  - **C, use:** attention only on shown records that were truly relevant. It runs on the direct host only; on the pool host it can't win by construction (§6).
  - **D, model-labeled:** true relevance on the full pool, with errors under two noise models. One flips 10–20% of labels at random. The other adds a systematic bias, for example toward recent or high-cosine records, because real model error is rarely random.
  - **E, owner sample:** true relevance on only about 200 queries. This tests whether a small hand-labeled set is enough.
- **Split.** Train on days 1–90, and hold out days 91–120.
- **Loop.** A line search over the recall half-life within bounds. It uses typed proposals, a scoring budget, the bootstrap margin and shadow mode.
- **Pass.** All three must hold:
  - Arm A finds the swept optimum within the search's resolution.
  - Arm D or arm E recovers at least half of arm A's held-out gain on at least one host.
  - Arm B gains nothing.
- **Kill or rescope.**
  - **The knob is wrong:** if even arm A gains nothing on held-out, try R2's other knob before anything else.
  - **No usable label source:** if arm A gains but arms D and E don't, stop before mile 3, or rescope v6 to larger owner-labeled sets.
  - **No leverage on SYNAPSE:** if arm A can't move pool recall at realistic cluster sizes, v6 has nothing to improve for SYNAPSE as it consumes recall today.
- **Cost.** About a day to build and minutes to run, on a laptop. No changes to USD, Rust, Moneta or SYNAPSE. Fresh-process reproduction and byte-identical rollback are proved in mile 4, not here.

---

## 13. Decisions

**The one ask now: go or no-go on mile 2.** It's cheap, it can kill the idea, and its report changes the evidence behind every ruling below.

**Holding until mile 2 reports.** There are five rulings, each a closed set of options plus "none of these." The full Jev-ready questions are in `rulings.jev.json`, beside this file, with each option's best case and cost in neutral wording.

- **R1. Where does policy history live?**
  - `one_timeline`: policy content inline in `govern` events, with layers derived.
  - `journal_values`: only tuned values are journaled; context layers stay as in v5.
  - `layer_chain`: the prototype's chain of USD layers, with the journal untouched.
- **R2. What's the first knob?**
  - `recall_half_life`: ranking-only, with retention unchanged.
  - `utility_exponent`: score = max(cos, 0) × U^β, where β = 1 is v5.
  - `both`.
- **R3. Where do labels come from?**
  - `use_signals`.
  - `model_labels`: on the full candidate pool.
  - `owner_labels`.
  - `mixed`.
- **R4. When may the pointer move?** Sleep passes are held during probation under every option.
  - `shadow_only`: the loop reports, and the owner repoints.
  - `owner_gate`: the substrate files requests with evidence, and the owner approves each one.
  - `probation`: automatic past the margin, reverted if the held-out window drops.
- **R5. How is tampering detected, and what's signed?**
  - `seals_and_signing`: running-hash seals, plus owner ed25519 signatures over constitution changes and seals, with the key kept off the loop machine.
  - `seals_only`.
  - `per_line_chain`: every line carries the previous line's hash, which changes every v5 line.

**How Jev triages them `[P]`.**

1. Each ruling is asked in both option orders, twice each. The TypeSafe docs give no guidance on option order, so this check is ours.
2. A ruling is settled if both orders pick the same option with probability 0.60 or higher. That's the docs' illustrative threshold, not a calibrated one.
3. Every other ruling is contested and goes to the owner first, with an independent reviewer arguing both sides.
4. Jev's answers are recorded under the pinned version. They're a prior, not a verdict.

The run needs a TypeSafe key, which this workspace doesn't have yet.

---

## 14. Locks and non-goals

| Lock | In v6 |
|---|---|
| Four-op agent API | **Kept.** Tuning and `reload()` are harness-level operator ops. |
| Decay formula `U(t) = max(floor, U·e^(−λΔt))`, with negative Δt clamped to zero | **Kept verbatim.** v6 may evaluate it with a second λ for ranking (R2). |
| E1: the journal, not the vector index, is the authority | **Assumed** `[A]`, unruled. |
| E2: reads never write | **Assumed** `[A]`, unruled. v6 depends on it entirely. |
| E3: one ordered journal replaces the GIL-dependent log | **Assumed** `[A]`, unruled. |
| E4: prune is a tombstone, not a delete | **Assumed** `[A]`, unruled. The line depends on it. |
| The half-life reinterprets history (v5's smaller call) | Unruled. The split in §4 rests on it. |
| Handle, not singleton; codeless typed schema | **Kept.** |
| A creative-agnostic core | **Kept.** It's why the objective lives in the constitution (J2). |
| Composition is Pixar's USD | **Kept.** oxideav-usdz stays parked. |

**Non-goals for v6:**
- The loop doesn't tune retention, tombstone anything, or touch records.
- There's no model in the read path, no ANN index, and no embedding training.
- There's no per-context tuning in v6.0.
- The proposer stays outside the store until mile 6.
- There's no pure-Rust USD and no speed claim.
- v6 is not a differentiable or C-ABI rewrite. An earlier proposal in that direction was rejected, and nothing here reopens it.

---

## 15. Open questions, and what to attack

**Open:**
- The exact-pool argument stays an argument until V-POOL passes.
- Agreement between the two `exp()` implementations is untested (V-EXP).
- The referee's fuel and memory needs are unmeasured.
- Resampling whole sessions in the bootstrap is a choice that hasn't been validated.
- How much systematic label bias the loop tolerates is unknown (arm D).
- The held-out window wears out and has to be rolled forward.
- Holding sleep passes during probation lets memory grow, and how long probation can safely last is unknown.
- What SYNAPSE's attention should mean is SYNAPSE's call, and changing it also changes what utility measures.
- Windows is untested.
- Jev has never been called live.

**For the reviewer: please attack these specifically.** If a lock in §14 should go, say which one and why in a separate section, rather than inside the critique.

1. **The journal carrying policy.** Is the policy at a sequence number really fixed by the prefix? What else does a read depend on that the query log and the journal don't capture?
2. **The line and the hold.** Find a read-time value whose effect isn't fully undone by a repoint plus the probation hold.
3. **Labels.** Will a synthetic world flatter arms D and E? What would make the test harder?
4. **The pool.** Does the monotonicity argument hold through floors and clamps? Where could floating point break it?
5. **The split.** Could a ranking-only half-life make `explain()` or the compat surface misleading anywhere this design doesn't cover?
6. **The margin.** Is a session-level paired bootstrap the right noise model? What would make it fire on noise?
7. **Leverage.** With one knob, and a host that reranks Moneta's pool, can v6.0 fail informatively?
8. **Creative-agnostic.** Does shipping nDCG@k as the default impose a perspective, despite J2?

---

## 16. Independent review

Fable, an advisor model that didn't write this document, reviewed the first draft against the primary sources: both earlier blueprints, the v5 code as written, SYNAPSE's source, and the 8 September decisions. Each finding was checked against the source before it was acted on.

**The changes below were made after that review and haven't been reviewed themselves.** A second opinion will be their first independent look. The first question in §15 points at the largest of them.

**Changed in response:**
- **Replay was overstated (critical).** A v5 read also depends on the caller's scopes, which change slot outcomes, and on the exact embedding and the limit. The echo carries none of these. A journal that only names policy files by hash wasn't sufficient either. Now the journal carries policy content inline, the host logs every read input (P1, P2), and §5 states the claim precisely.
- **The loop could reach a tombstone indirectly.** A tuned policy changes what SYNAPSE shows, which changes its attention, which changes retention. Probation now holds sleep passes until the owner adopts or rolls back (J7, V-HOLD).
- **Policy files could drift from the journal.** A Solaris edit made through the live view would also have landed in a file that was supposed to be immutable. Layer files are now derived and regenerated, and edits go through `drafts/` and a journaling `reload()` (T2, T3, V-DERIVED).
- **The half-life fork was unnamed.** Recall utility now reinterprets history the way v5's half-life does, and the cost of rebuilding it is named. Eval-set features now use raw attention history instead of anchors (§4, §6).
- **One experiment arm couldn't win.** Shown-only labels can't move pool recall. The arms, the noise models and the kill criteria were rebuilt, and the known answer is now a brute-force sweep instead of the hidden half-life (§12).
- **Some tags overclaimed or underclaimed.**
  - SYNAPSE's compatibility numbers are now exact: 237 with SYNAPSE untouched, 247 with helpers, on version 5.80.0.
  - The echo is a fingerprint of resolved policy, not a set of file hashes.
  - "No recall at a past prefix" is now verified rather than unknown.

**Refuted:** the review proposed that out-of-order attention breaks the pool's monotonicity by running decay backwards. v1's decay formula, which v5 imports unchanged, clamps a negative time step to zero `[V, src/moneta/decay.py]`, so that can't happen. The clamp is now part of the argument, and removing it is one of V-POOL's sabotages.

---

## Glossary

- **Moneta:** a memory substrate for AI agents, built on OpenUSD. Its owner is Joseph Ibrahim.
- **Journal:** v5's append-only file of checksummed, fsync'd events. All other state derives from it.
- **Fold:** replaying the journal into current state.
- **Record:** one remembered item, with its payload, vector and provenance.
- **Context:** a named policy binding, such as one project, with an optional parent.
- **Slot:** a named place where competing claims resolve to one winner.
- **Utility:** a per-record value in [floor, 1] that decays with a half-life and rises with attention.
- **Attention:** a host's signal that records mattered, with weights in [0, 1].
- **Sleep pass:** a harness pass that applies retention, tombstoning or staging records by their utility.
- **Tombstone, erase, compact, revector:** respectively, retire a record from recall; remove its payload; physically rewrite the journal; and replace vectors after an embedder swap.
- **Generation:** one version of a policy tier.
- **Referee:** the pinned WASM module that scores a candidate.
- **Constitution, rules, self:** the governed tiers. They hold the owner's law, the search policy, and the loop's tuned values.
- **Probation, adoption:** probation is the period after a promotion when retention is held; adoption is the owner's act that ends it.
- **Host:** the application using Moneta. The first is SYNAPSE, a Houdini-centered agent system.
- **Layer, sublayer, strength, prim, usdz:** in USD, a layer is a file of opinions. A stack of sublayers composes, and stronger layers' opinions win. A prim is one named object in a layer. A usdz is a zipped USD package.
- **WASM:** WebAssembly, a sandboxed bytecode. Here it has no imports, so a module can't reach anything outside itself.
- **ulp:** unit in the last place, the smallest step between adjacent floating-point numbers.
- **nDCG@k:** a ranking metric that rewards placing relevant items near the top of the first k results.
- **Jev:** TypeSafe's typed-judgment model. It returns probabilities over a closed set of options.
