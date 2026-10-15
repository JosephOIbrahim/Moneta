# Owner rulings: v6 R1–R5, as carried into v7

**Ruled by:** Joseph Ibrahim, owner · **Date:** 2026-10-15 · **Evidence:** `pass1_rulings_brief.md` (with the protocol v2 addendum), `jev/summary.json`, `jev/summary_v2.json`, `pass1_advocacy.json`

Jev's answers were a prior, not a verdict. Each line below is the owner's call.

---

**R1. Policy history → `one_timeline`. RULED.**
`govern` events carry the policy spec inline. USD layers are derived and regenerated. Owner edits go through `drafts/` and a journaling `reload()`. The live-edit cost in Solaris is accepted.

**R2. First knob → `recall_half_life`. CARRIED AS AN ASSUMPTION [A].**
Mile 2 adds a β (utility exponent) sweep as a diagnostic arm. It flips to `utility_exponent` if β recovers about the same held-out gain, or if the v5 half-life call is rejected at mile 0.

**R3. Labels → `owner_labels`. CARRIED AS AN ASSUMPTION [A].**
It flips to `mixed` if arm E fails *and* arm D survives systematic bias.

**R4. Pointer → `owner_gate`, amended. RULED.**
- Shadow-only is the operative mode through mile 4.
- (a) On rollback, the retention fold excludes attention tagged with the rolled-back generation. V-UNDO gains a sabotage: a sleep pass after rollback.
- (b) Promote, adopt and rollback are owner-signed.
- (c) The constitution sets a probation ceiling with an explicit default. Only one generation may be pending at a time.
- (d) The owner's evidence shows held-out pass/fail only, or each disclosure counts against the window's wear.

**R5. Tamper → `seals_and_signing`, amended. RULED.**
- A per-event running hash from the v6/v7 genesis, which is a fourth option Jev never saw.
- The signed set covers `govern` with why ∈ {promote, adopt, rollback, amend}, T3 reloads, and the trust store.
- An external anchor holds the latest signed seal.
- The public key is pinned in code or in the genesis.
- Key rotation is signed by the old key, with a pre-registered recovery key.

**O27. The seam-admission rule → CONFIRMED. RULED 2026-10-15.**
Rust enters only behind a pure seam with an exact Python oracle, where it buys speed or a guarantee. This is a project constraint, separate from D1, whose latency gate did not fire. Both live seams, `moneta_native.ScanIndex` and `decay_batch`, stay on by default behind `MONETA_NATIVE`, and their conformance suites are the contract. The same rule governs the future referee, verifier and recall-fold crates.

**O35. Where is the v5 bundle? → NOT FOUND (searched 2026-10-15).**
Searched and not found:
- `origin`, which has no `v5` ref.
- The owner's other GitHub repos.
- `Moneta-private`, Downloads and OneDrive/Backups.
- The `.bundle` files on C:, D:, E:, F: and G:. The only bundles found are SYNAPSE ones.

The v6 measurements came from a "2-vCPU cloud container", so v5 most likely lives in that cloud session. Mile 0 step 0 stays open: recover it from the session, or rule that mile 0 proceeds on v1 alone.

**O35, update: FOUND.** The owner supplied `moneta-v5.bundle` (`refs/heads/v5` @ `b1feaaf`, based on `6cf05f5`) and its blueprint on 2026-10-15. It is merged beside v1 on branch `v7-native-seams` (`861bed9`), not on `main`.

---

## Round 4: mile 0 rulings (2026-10-15)

**Evidence:** `ROUND4_BRIEF.md` (five skeptics, checked against the v5 code), `jev/summary_round4.json` (every ruling settled toward v5; the question framing was drawn from v5's own blueprint), `round4_skeptics.json`.

**F1, recorded as factual ground:** v1's `signal_attention` promises fsync (`api.py:416-418`), but `durability.py:144-149` only flushes. Acknowledged attention can be lost on a crash today.

**E1 + E2. The journal is the authority; reads are pure → FOR v5, WITH CONDITIONS. RULED.**
- The decay formula stays verbatim. "Three evaluation points" becomes "zero mutation points; state changes only through journaled events".
- *Blocking cutover step 2:* fix the migration crash window. Whether to migrate is decided from a journaled completion marker, not from whether the journal file exists.
- *Before 5.0.0:*
  - a checkpoint, so open replays only the tail;
  - re-projection made idempotent;
  - one source of λ;
  - runtime λ tuning made explicit;
  - a timestamp-skew guard;
  - the native decay seam ported to v5.
- *Polish:*
  - a CRC-bad final line treated as a torn tail;
  - an attention durability tier;
  - export failure logged, not raised.

**E3. One ordered journal under a writer lock → FOR v5, CLOSURE GATED. RULED.**
Closes only when all three blocking conditions are met, each with a measured Windows/hython number:
1. USD projection runs outside the writer lock. Recall p95 stall must be ≤ 30 ms during a sleep pass (real `UsdTarget`, hython, 500-prim batches).
2. The snapshot export runs outside the lock. Stall must be ≤ 30 ms per pass at 10k × 768.
3. A journal checkpoint or attend coalescing, with a tested reopen budget.

*Before 5.0.0:*
- Windows fsync numbers, and either group commit or the ~700 writes/s ceiling recorded.
- Free-threaded Python stays `[U]`, with a warning.
- §5.1 amended: attention is visible immediately.
- The SYNAPSE swap re-run on Windows against a copy of the 841-record store.

**E4. Prune = tombstone; operator erase is the real delete → SEMANTICS ONLY, GATED. RULED.**
`compact()` is **not** ratified, because v7 replaces it.

Blocking:
1. Bound the read path: recall p95 with 100k dead records within 10% of zero dead.
2. `erase()` names or invalidates every derived copy.
3. The ruling covers semantics, not mechanism.
4. Fix the O(n²) dedup at `substrate.py:949`.

The E4 Jev question is to be re-asked with corrected option costs.

**Half-life. The journal owns λ; each change is an explicit, journaled, owner-authorised choice between reinterpreting history and applying forward → RULED.**
Blocking:
1. `fold.lam` comes from genesis and change events, never from Config. A mismatched open raises unless the caller passes an explicit mode. Read-only opens never append.
2. The first sleep pass after a change is a dry run (or needs confirmation above a stated LIVE fraction).

R2 does not flip: it stays `recall_half_life` `[A]` until mile 2 reports.

---

**Still open from mile 0:** closing each gated ruling, meaning its blocking conditions implemented and measured.
