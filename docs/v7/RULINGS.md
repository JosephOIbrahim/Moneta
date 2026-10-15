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

---

**Still unruled:** mile 0 (v5's E1–E4 and the half-life call). Every ruling above assumes v5 lands `[A]`.
