# Moneta v6 Rulings R1–R5: Owner Brief

> ## Protocol v2 addendum (overrides the Jev claims below)
>
> **Why:** the first run never moved middle options out of position 2, and the brief below was written before the fix. Protocol v2 (`jev/jev_triage_v2.py`, `jev/summary_v2.json`) runs **every cyclic rotation** of each ruling's options, sends **one question per request**, repeats each twice, and adds an **R4 variant with the adoption wording removed** from the state. That is 38 calls, all on `jev-1.13.0`.
>
> | Ruling | v2 top (every rotation) | Mean | Max position swing | Status |
> |---|---|---|---|---|
> | R1 | journal_values / one_timeline / one_timeline | one_timeline 0.62 | **0.37** | **contested, depends on position** |
> | R2 | recall_half_life ×3 | 0.60 | 0.095 | stable direction, borderline magnitude |
> | R3 | owner_labels ×4 | 0.55 | 0.155 | stable direction, weak magnitude |
> | R4 | owner_gate ×3 | 0.91 | 0.045 | settled |
> | R4, neutral state | owner_gate ×3 | 0.79 | 0.145 | **settled. The priming attack was tested and did not land** |
> | R5 | seals_and_signing ×3 | 0.93 | 0.045 | settled |
>
> **Corrections to the text below:**
> - **R2** is not a coin flip. It points the same way in every rotation and falls just short of the 0.60 bar.
> - **R4's** settlement no longer rests on position or on priming. Both were tested.
> - **"Not independent" (Read this first, #2) is wrong.** TypeSafe states that questions in one request can't see one another's answers. One question per request was a sound control, but not for the reason given.
> - **R1:** "not informative" still holds.
> - **R5:** the recommended "per-event hash from the v6 genesis" is effectively `per_line_chain` scoped to v6. Jev's 0.018 for that option was a vote against a cost ("changes every v5 line") that format 6 makes moot. So the amended R5 is a fourth option that Jev was never asked about.

**For:** Joe, who makes these rulings · **Status:** recommendations only, nothing here is ruled · **Inputs:** `docs/v7/inputs/BLUEPRINT_v6.md`, `docs/v7/inputs/rulings.jev.json`, `docs/v7/jev/summary.json`, `docs/v7/jev/requests.jsonl`, and v1 code in `src/moneta/`

---

## Read this first

**1. All five rulings depend on mile 0.** v5 is not merged. E1–E4 are unruled, and so is the smaller call that "the half-life reinterprets history" (§1 line 46, §14). Every ruling below assumes v5 lands `[A]`. None of them can be put into effect before then.

**2. Jev is a weak prior here, not evidence.** Three reasons, all checked in the files:
- `requests.jsonl` has **4 requests in total**. Each one carries **all five questions under one shared state**, so the five answers are not independent of each other.
- With three real options, reversing the order leaves the middle option in the middle. `journal_values` (R1) and `owner_gate` (R4) were in position 2 both times, so their position was never actually varied. **Only R5's winner moved from first to last and still won.**
- The shared state already says "held while a promoted generation has not yet been adopted by the owner." An owner adoption act is built into the prompt, so R4's result partly repeats the prompt back.

**3. Mile 2 is the real decider for R2 and R3.** It is Python-only and makes no changes to Moneta (§12 line 417). It can test both knobs and both main label sources directly. It cannot test R1, R4 or R5.

**4. The D1 frame used throughout.** Rust is used only behind a pure seam that has an exact oracle (§10 line 349).
- **Scan:** moves to Rust only if arm P misses the 50 ms p95 gate. v5 currently runs about 161 ms at 10k records, roughly 3× over (§10 line 353, §11).
- **Referee:** Rust compiled to WASM, chosen for the sandbox and not for speed (§10 line 351).
- **Verifier:** the seal walk plus the audit is the second candidate (§10 line 352).
- **USD:** composition stays with Pixar's USD, and oxideav-usdz stays parked (§10 line 355).

---

## Summary

| Ruling | Jev status | Recommendation | Wait for mile 2? |
|---|---|---|---|
| **R1** policy history | contested (it flips) | **one_timeline** as the direction, built in mile 4 | No. Mile 2 can't test it |
| **R2** first knob | contested (it flips, unstable) | **recall_half_life, provisionally.** Mile 2 sweeps β alongside it | **Yes** |
| **R3** labels | contested (stable lean) | **owner_labels, provisionally** | **Yes**, decided by arms D and E |
| **R4** pointer | "settled", but untested on position | **owner_gate, amended**, with shadow_only operative through mile 4 | No, but the amendments are required |
| **R5** tamper | settled (survived the position swap) | **seals_and_signing, amended** | No, but the amendments are required |

---

## R1. Where does policy history live?

### Jev result

| Option | As listed | Reversed (none_of_these last) |
|---|---|---|
| one_timeline | 0.385 | **0.745** |
| journal_values | **0.54** | 0.175 |
| layer_chain | 0.04 | 0.06 |
| none_of_these | 0.035 | 0.02 |

- **Confidence:** 0.36 / 0.41 as listed, 0.67 / 0.65 reversed. Both orders were stable across repeats.
- **What this shows:** one_timeline gains 0.36 just from moving from first to last real option, and confidence moves with position. **On R1, Jev's answer is not informative.** Rule this one from the argument.

### The strongest case for one_timeline

- **It fixes the critical review finding.** §16 found that "replay was overstated." The fix was to carry policy content inline (§5 lines 149–157, T2). `journal_values` gives that fix back, and its own cost line says so: "Replaying a past query's eligibility stays approximate."
- **The damage reaches the judge.** Caller scopes and context policy change slot outcomes and candidate pools (§3 line 95). The eval-set builder (§6), the byte-identical rebuild (P2), V-REPLAY and V-UNDO all need the composed policy at a past sequence number.
- **The extra machinery is smaller than it looks.** Format 6, self-tier `govern`, `seal` and constitution events have to be built under either option. one_timeline adds only three things: a journaling `reload()`, `drafts/`, and regenerated layers.
- **There is precedent in v1 for the failure it prevents.** `DecayConfig.set_half_life` changes λ in place and leaves only a log line (`src/moneta/decay.py:91-105`). The WAL is unlinked at every snapshot (`src/moneta/durability.py:119-125`). Policy and history that live off the timeline are exactly what v6 exists to stop.

### The strongest case for journal_values

- **It is a sequencing argument, not an argument about the end state.** Every journal_values event is also a one_timeline event. Self-tier `govern{tier, name, why, spec}` has the same shape under both (§5, §7 steps 6–7). Upgrading later only adds things and rewrites nothing.
- **Under the line, everything the loop can touch is journaled** (§4, L1). Rollback, V-UNDO, V-HOLD, V-WRITE and C1 all still hold.
- **The approximation is limited and can be filtered.** Eval features such as cosines, deposit order, floors, initial utility and raw attention (§6 line 195) don't depend on context policy. Only eligibility can drift. Each echo carries a fingerprint of the resolved policy (§3 line 95), so the builder can **drop** queries whose fingerprint no longer matches instead of replaying them wrongly. The result is exact on a filtered subset.
- **It lets mile 3 start without first owing** T2, T3, V-TIMELINE, V-DERIVED and their sabotages.

### What must be true for one_timeline

- The host logs the **full** query: embedding, limit, context, scopes, time and echo (P1, P2). SYNAPSE can't do this until mile 3 (§6 line 193).
- Policy specs stay small (§5 line 157). If slot selections ever list record ids at scale, the inline argument weakens.
- v5's `reload()` and both resolvers can be pointed at journal-built specs. **This is unverified, because v5 code is not on this machine.**
- Regenerating derived layers on every `reload()` is cheap enough. This is unmeasured (fact d).
- The owner actually edits context layers during or between train and held-out windows. If he doesn't, the gap is only theoretical.

### What would flip it toward journal_values

- **Mile 2 kills v6 outright.** Arm A gains nothing, D and E both fail, or there is no leverage on pool recall. Exact policy replay then loses its main customer (§12 lines 413–416).
- Mile 2 shows that eval scores barely move when context or scope policy is perturbed.
- Mile 0 shows that v5's resolvers are tightly coupled to reading layer files.
- Mile 3 shows that owner context layers never change inside any window, or that specs grow with record count.

### The cost to name honestly

**The reload step is a workflow cost for you in particular.** USD and Solaris were chosen partly so policy could be edited live (§5 line 161). Under one_timeline an edit takes effect only after `reload()`, and derived layers in usdview become read-only in effect (V-DERIVED). For someone who thinks in live composition, that is a regression.

A "hash plus blob on each reload" middle path still needs the same reload hook, so in practice it is one_timeline with an extra step. §16 already found that hash-only naming wasn't enough.

### Rust / D1 implication

- **one_timeline:** the policy at any sequence number is a **pure function of the journal bytes.** The verifier, the audit and the eval-set builder each walk one input, and each has an exact Python oracle. Seal hashes cover record history and policy history together. Derived USD layers are an *output* of the seam, so Pixar's USD stays outside Rust.
- **journal_values:** any seam that resolves past policy also reads mutable files that have no history, so **no exact oracle exists for past states.** That conflicts with D1. One concession to that side: the format a journal_values verifier targets is smaller and settles earlier, while one_timeline's format 6 keeps changing until mile 4.

### RECOMMENDATION (the owner rules)

> **one_timeline**, ruled as the direction now, with the machinery built in mile 4. **Reason:** both advocates agree it is the right end state. journal_values argues only about timing, and the timing question disappears because the extra pieces aren't needed before mile 4 in any case.

**Mile 2 note:** don't block mile 2 on R1. If mile 2 kills v6, this ruling stops mattering.

---

## R2. What is the first knob?

### Jev result

| Option | As listed | Reversed |
|---|---|---|
| recall_half_life | **0.61** | 0.49 |
| utility_exponent | 0.38 | **0.495** |
| both | 0.0 | 0.0 |
| none_of_these | 0.01 | 0.015 |

- **Confidence:** 0.49 / 0.47 as listed, 0.37 / 0.39 reversed. **The reversed repeats were not stable.**
- **What this shows:** a coin flip, with no prior worth using.

### The strongest case for recall_half_life

- **Mile 2 is already built around it.** The world has a hidden fade rate, the known answer is a half-life sweep, and the kill rule already names β as the fallback: "try R2's other knob" (§12 lines 393, 397, 414). If β went first, the experiment's ground truth would need redesigning.
- **It matches the question.** β is a monotone transform of a fixed U. It **cannot reorder two records with equal cosine**, and it cannot change how old attention weighs against recent attention, which is where the echo problem lives (§3 line 97).
- **v1 already treats it as the knob.** It has bounds of 60 s to 24 h (`decay.py:34-35`) and a runtime setter (`decay.py:91-105`). The value is "explicitly provisional" until load testing produces curves (`decay.py:21`). The loop is the curve-producer v1 was asking for.
- **It keeps the tiers separate.** Under β, ranking still reads *retention* utility, so every owner change to the retention half-life would silently move β's optimum. The split removes that coupling (§4 tier table).

### The strongest case for utility_exponent

- **It is the only option that doesn't depend on an unruled call.** The split "rests on" v5's call that the half-life reinterprets history (§14, §4 line 128).
- **β = 1 reproduces v1/v5 ranking exactly.** That is one token at `src/moneta/api.py:414` (`max(cos_sim, 0.0) * memory.utility`), with the same product at `ecs.py:295`.
- **It avoids a whole subsystem.** There is no second fold, no rebuild of recall anchors on a repoint (cost `[U]`, §11), no anchors in seals (§5 line 175), no `recall_utility`, no two-utility `explain()`, and no compatibility exposure for SYNAPSE.
- **Its pool proof is trivial.** For U ∈ [floor, 1], U^β is monotone in β, so V-POOL becomes a short proof.
- **It targets the echo threat directly.** β < 1 means "trust utility less," and β → 0 is pure cosine, a known baseline.

### What must be true for recall_half_life

- You rule the v5 half-life call **in favor** at mile 0.
- **E2 (reads never write) lands.** In v1 the split is impossible: `query()` mutates utility in place through `self.ecs.decay_all(...)` (`api.py:401`, `ecs.py:222`), so ranking utility and retention utility are the same stored number.
- Arm A's half-life sweep gives a non-flat held-out curve on at least one host.
- Rebuilding recall anchors at 10k–100k records is cheap enough that repoint and rollback stay practical (`[U]`, §11).
- The pool monotonicity holds through floor and clamp. It relies on the negative-Δt clamp at `decay.py:66-67` and the clamp to 1 at `ecs.py:212`.

### What would flip it to utility_exponent

- **A β sweep in mile 2 recovers about the same held-out gain as the half-life.** This is plausible when attention is sparse: for unattended records, U^β ≈ U₀^β·e^(−βλΔt), so β behaves like a rescaled λ.
- β moves SYNAPSE-shaped pool recall more than the half-life does. β also reweights the floor (floor^β), which may matter more for who enters a 50-candidate pool.
- The measured anchor-rebuild or seal cost makes repoint slow.
- **You reject the v5 half-life call at mile 0.** β is then the fallback by the blueprint's own text (§4 line 134).

### What would kill utility_exponent

- Arm A finds a half-life gain, but the best β is about 1.
- The failure in the world is a **mis-ordering of utilities**, for example stale but heavily attended records outranking fresh ones. A monotone transform can't fix that.

### Rust / D1 implication

- **Half-life:** this adds **no new transcendental function.** `exp` is still the only libm function that has to match exactly, and V-EXP covers it (§6 line 230). The natural Rust seam is a **pure recall-fold kernel**: (attention events, λ_recall, floor, clamp) → anchors. Its oracle is `decay_value` (`decay.py:48-69`). The same kernel can serve both the read path and the referee. It is also the likeliest place to miss a latency gate, because a repoint rebuilds every anchor.
- **β:** this adds `pow(U, β)`, a second function that isn't correctly rounded, so it needs a V-POW check. The upside is the smallest possible seam: "score a flat pool of (cos, U, label)." The fold stays in Python.

### RECOMMENDATION (the owner rules)

> **recall_half_life, provisionally, conditional on ruling the v5 half-life call in favor at mile 0.** Add a **β sweep as a diagnostic arm in mile 2.** It takes minutes of Python. **Reason:** the experiment, v1 and the ordering argument all point at the half-life, but β is cheap enough that mile 2 should decide it, not taste.

**Mile 2 note:** **wait for it.** This is not the `both` option. Jev gave `both` 0.0, and tuning two knobs in the loop doubles the search space. Running β as a *diagnostic* only answers which single knob to tune.

---

## R3. Where do labels come from?

### Jev result

| Option | As listed | Reversed |
|---|---|---|
| owner_labels | **0.555** | **0.54** |
| mixed | 0.17 | 0.045 |
| use_signals | 0.06 | 0.16 |
| model_labels | 0.10 | 0.12 |
| none_of_these | 0.115 | 0.135 |

- **Confidence:** 0.44 / 0.45 as listed, 0.44 / 0.41 reversed. Both orders were stable.
- **What this shows:** a **stable but weak lean** toward owner_labels that holds across positions. `mixed` is sensitive to position, falling from 0.17 to 0.045.

### The strongest case for owner_labels

- **Use signals can't move pool recall.** Anything shown was already in the incumbent's pool (§6 line 207; arm C "can't win by construction," §12 line 404). On SYNAPSE, all of `mixed`'s leverage comes from its model half, so it costs two pipelines and delivers one.
- **Only the owner's labels carry the owner's meaning of "better."** The core is creative-agnostic (J2, §6 line 211). Model labels bring in a third party's idea of relevance.
- **Model bias can only be measured against a trusted reference** (arm D, §15). So owner labels have to come first on either path.
- **Signing labels you never read weakens the signature R5 is meant to provide.**

### The strongest case for mixed

- **The holdout wears out** and has to be rolled forward (§6 line 216, §15). Each roll needs fresh labels. owner_labels is "slow to refresh" by its own cost line.
- **Model labels are mechanically bounded to the window.** A labeler that sees only the journal prefix can't see the future. An owner labeling months-old queries has hindsight, which the label-window rule forbids (§6 line 217, V-HOLDOUT).
- **It spends your attention best.** You sign a recorded batch (P4) instead of labeling each item by hand.
- **It audits itself.** On shown records the two sources overlap, and their disagreement rate is a running estimate of model bias.

### What must be true for owner_labels

- **About 200 owner-labeled queries recover at least half of arm A's held-out gain on at least one host** (arm E, §12 lines 406 and 411).
- **The labeling job is bounded.** Pools are `max(3 × limit, 50)` per query (§3 line 99). **Roughly 200 queries × 50+ records is about 10,000 judgments per window.** The real store is small: 841 records (§12 line 382).
- The session bootstrap (J4) still yields a margin with about 200 correlated queries.
- Your judgments are consistent over time. Arm E models you as noise-free, and real owners aren't.

### What would flip it to mixed

- **Arm E fails and arm D passes under systematic bias,** not just random flips (§12 lines 405 and 415).
- E's signal is too thin for the bootstrap margin to clear, so nothing ever promotes.
- 10,000 judgments per window turns out to be unsustainable.
- Plus three conditions on mixed's own side: SYNAPSE agrees to emit true *use* signals (§15 line 495), the bias seen on shown records carries over to unshown ones, and each label carries provenance.

### The cost to name honestly

**Your attention is the scarcest resource in the project.** Arm E's perfect labeler flatters you. At 841 records, pinned model labels with request hashes (P4) are cheap, so price is not the real objection to model labels. The real objections are **unmeasured bias** and **diluted signatures**.

### Rust / D1 implication

- **No new seam either way.** Labeling is human work or network I/O, so it has no pure compute to port. Labels are data in the referee's single flat buffer (§6 line 239).
- **owner_labels** keeps that buffer small and single-source, and keeps the WASM referee well inside the toy caps (20M fuel, 8 MB). One downside: fewer near-ties means V-EXP is sampled thinly, so a separate synthetic pool may be needed for conformance testing only.
- **mixed** puts per-label provenance (source, weight, pin, request hash) into the buffer schema, which then becomes part of the pinned contract.

### RECOMMENDATION (the owner rules)

> **owner_labels, provisionally.** **Reason:** it is the only source that both moves pool recall and ends the chain of judges on you (principle 4). Switch to mixed only if arm E fails *and* arm D survives systematic bias.

**Mile 2 note:** **wait for it.** Arms D and E decide this. **Mile 2 has no mixed arm**, so mixed's unshown half stands or falls on arm D alone.

---

## R4. When may the pointer move?

### Jev result

| Option | As listed | Reversed |
|---|---|---|
| owner_gate | **0.945** | **0.875** |
| shadow_only | 0.02 | 0.075 |
| probation | 0.005 | 0.0 |
| none_of_these | 0.03 | 0.05 |

- **Confidence:** 0.93 / 0.92 as listed, 0.85 / 0.81 reversed. Both stable. **Status: settled.**
- **What this shows:** owner_gate sat **in position 2 in both orders**, and the state text already assumes an owner adoption act. So "settled" means **consistent with the blueprint**, not independently confirmed.

### The case for each side (from the option text plus the skeptic)

- **owner_gate:** low risk for little effort, and it matches J6 ("In v6.0, only the owner moves the pointer"). Every change still costs your attention.
- **shadow_only:** zero live risk, and it is what miles 3–4 actually run (V-SHADOW, §12 line 385). It is slow.
- **probation (automatic):** hands-off, but answers change without a human deciding. It conflicts with principle 4 and J6.

### Skeptic's verdict: the direction is right, but it does not hold as stated

**1. The rollback leak.** This is the sharpest point, and it touches verified v1 code.
- Attention from probation stays in the journal, and **only the eval-set builder** filters it by generation (§4 line 125). The retention fold still counts it.
- In v1 the prune key is `memory.utility < PRUNE_UTILITY_THRESHOLD and memory.attended_count < PRUNE_ATTENDED_THRESHOLD` (`src/moneta/consolidation.py:111-112`). That key is fed by `reduce_attention_log` (`src/moneta/attention_log.py:108`), so `attended_count` moves with attention whatever the decay.
- **Result:** after you roll back, the next sleep pass tombstones by attention that the *rolled-back* generation shaped. That cannot be reversed (§4 line 121). V-UNDO never runs a sleep pass after a rollback, so it misses this.

**2. Approval is unauthenticated.** R5 signs only "constitution changes and seals." A buggy process can append `govern{why: adopt}`, which releases held retention. In effect the substrate approves itself.

**3. There is no timeout and no default.** Each change needs two owner acts: approve, then adopt (§7 steps 5–7). If you are away, retention is held without limit, and how long probation can safely last is `[U]` (§15 line 494). The blueprint also doesn't say what happens when a second promotion arrives while one is still unadopted.

**4. The holdout leaks through you.** The evidence you see includes the held-out window (§7 step 5). Approving or rejecting on it, cycle after cycle, is selecting on the holdout (fact b).

**5. Timing.** owner_gate only describes mile 5. Through mile 4 the operative mode is shadow_only.

### What must be true

- All four patches below are in place before mile 5.
- You have enough attention to answer requests at the rate the loop produces them.

### What would flip it

- **Toward shadow_only, permanently:** if requests pile up faster than you review them, or if the probation ceiling has to be so short that every change rolls back.
- **Toward probation:** almost nothing in v6.0 would, because J6 rules it out. It is a mile 6+ question.

### Rust / D1 implication

- **No compute seam.** Gating is workflow.
- **It does grow the verifier seam.** If promote, adopt and rollback are signed, the Rust seal and audit walker must verify those signatures too. That is still a pure function of bytes plus a pinned key, with the Python version as oracle. A typed state machine for generations, `Proposed → Promoted(probation) → Adopted | RolledBack`, mirrors the amendment channel's `Draft → Measured → Signed → Enacted` (§10 line 354). Types guard against the substrate's own bugs, and signatures guard trust.

### RECOMMENDATION (the owner rules)

> **owner_gate, amended,** with **shadow_only as the operative mode through mile 4.** **Reason:** it is the right gate for a solo owner, but without the patches below a rollback is not actually an undo.

**Minimum amendments:**
- **(a)** On rollback, the retention fold excludes attention tagged with the rolled-back generation, or the next sleep pass refuses to act on it. V-UNDO gains a sabotage: *run a sleep pass after rollback.*
- **(b)** Promote, adopt and rollback are **owner-signed** and join R5's signed set.
- **(c)** The constitution sets a **probation ceiling** with an explicit default: either auto-rollback carved out of J6, or retention stays held with an alarm. Only **one pending generation** at a time.
- **(d)** The evidence you see shows **held-out pass/fail only**, or each disclosure counts against the window's wear.

**Mile 2 note:** no need to wait. Mile 2 runs in shadow mode anyway.

---

## R5. How is tampering detected, and what is signed?

### Jev result

| Option | As listed | Reversed |
|---|---|---|
| seals_and_signing | **0.895** | **0.925** |
| per_line_chain | 0.025 | 0.01 |
| seals_only | 0.0 | 0.0 |
| none_of_these | 0.08 | 0.065 |

- **Confidence:** 0.85 / 0.87 as listed, 0.91 / 0.89 reversed. Both stable. **Status: settled.**
- **What this shows:** this is the **only ruling whose winner moved first to last and still won.** It is the most trustworthy Jev result of the five.

### The case for each side

- **seals_and_signing:** tampering is detectable and attributable. The cost is key handling.
- **seals_only:** cheap and catches casual edits, but a full rewrite with recomputed hashes still passes.
- **per_line_chain:** the strongest local evidence. Its stated cost is that it "changes every v5 journal line." **That cost is mostly moot:** §5 line 179 already has v6 declare format 6 and has a v5 reader refuse it, so line compatibility is broken either way. The chain can start at the v6 genesis without rewriting v5 history.

### Skeptic's verdict: it beats the alternatives, but as specified it cannot pass the blueprint's own check

**1. V-SEAL contradicts itself.** V-SEAL requires that "an edit after the last seal fails at open" (§9 line 340). Lines after the last seal carry only v5's CRC-32, which "anyone can recompute" (§5 line 177). **Seals alone can't meet that clause.** It needs a running hash in every event, at least from the v6 genesis.

**2. The signing gap.** Seals are written on the loop machine, and the key is somewhere else. Every seal after the last owner-signed one has the same weakness as seals_only. For a solo owner, that window could be weeks.

**3. Truncation.** Cutting the journal before the latest signed seal leaves a shorter history that is fully valid. Catching that needs an **external anchor**: you keep the seq and hash of the latest signed seal off the machine.

**4. The trust root isn't pinned.** If the public key sits in the same trust store that pins the referee (J1), an attacker can swap keys. Pin it in the code-ceiling tier (X1) or a signed genesis.

**5. The signed set is too narrow.** Adopt, promote and rollback (R4), `reload()` context edits (T3) and the trust store itself are all unsigned, and those are the acts whose effects can't be undone.

**6. Key lifecycle.** A lost key freezes the constitution for good. Rotation must be an event signed by the old key, and recovery needs a pre-registered second key. Windows is untested (§15 line 496).

### What must be true

- You can keep an ed25519 key off the loop machine and sign batches regularly enough that the unsigned window stays short.
- A per-event running hash is cheap at journal scale. The journal is 42.6 MB at 10k records (§11), and the cost is unmeasured.

### What would flip it

- If you cannot maintain key hygiene in practice, the option falls back to seals plus a per-event hash with no signing. That still beats `seals_only`.

### Rust / D1 implication

**This is the cleanest Rust candidate after the referee.** The verifier, meaning the running-hash walk, seal checks, signature checks against a pinned key and the truncation-anchor comparison, is a **pure function of (journal bytes, pinned public key, external anchor) → pass/fail**, with Python as the exact oracle (§10 line 352). "The audit is where the time goes," so a speed argument is likely, but it should be measured, not assumed. The hash and signature primitives are standard and deterministic, so there is no `exp`-style exactness risk.

### RECOMMENDATION (the owner rules)

> **seals_and_signing, amended.** **Reason:** it is the only option that makes authority attributable. The amendments make it pass V-SEAL and cover the acts that can't be undone.

**Minimum amendments:**
- A **per-event running hash from the v6 genesis.** This is a hybrid of seals and per_line_chain and needs no v5 rewrite.
- The **signed set extended** to every `govern` with `why` ∈ {promote, adopt, rollback, amend}, plus T3 reloads and the trust store.
- An **external anchor** of the latest signed seal.
- The **public key pinned** in code or the genesis.
- A **rotation and recovery protocol**, with a pre-registered second key.

**Mile 2 note:** no need to wait. This is mile 4–5 work.

---

## Before the v7 paper cites any Jev settlement

- Rotate through all orders: 3 cyclic rotations, or all 6 permutations.
- Send **one question per request.**
- Use a **neutral state** that leaves out the blueprint's chosen wording, such as the adoption act.
- Treat any option whose mean moves by **0.2 or more** across positions as contested.

---

## Implications for v7

How these rulings shape a Rust-seamed v7 that models the substrate as a typed graph:

- **The journal is an append-only DAG.** The backbone is linear: each event's running hash points to its predecessor (R5, amended). The extra edges are typed references. Rollback and roll-forward point to the earlier `govern` whose spec they restore (T4). `seal` points to a fold checkpoint by hash (T5). Signatures point to a pinned key node. The verifier is one pure graph walk over these edges, and that is the Rust seam R5 justifies.

- **Policy resolution is a derivation graph.** The nodes are `govern` specs, identified by their fingerprint. The edges are the context parent chain plus sublayer strength order, with **self weakest** (C1). The resolved policy at sequence number *n* is a pure function of the journal prefix (one_timeline, R1). USD layers are **derived leaves** that never feed back (V-DERIVED). C3 means the plain and USD resolvers agree on resolved policy, so Pixar's USD stays an output renderer of the graph, not part of the seam.

- **The eval set is a derived node** over (journal prefix, query log, label set). It is content-addressed in `blobs/`, and a rebuild is byte-identical (P2). Labels carry provenance edges (R3). Probation attention carries a generation edge, which is what makes the R4 rollback-leak fix *expressible*: the retention fold filters by generation.

- **The generation lifecycle is a typed state machine**, `Proposed → Promoted → Adopted | RolledBack`, and each transition is a signed `govern` event (R4 + R5 amended). Illegal transitions are unrepresentable, as in the amendment channel (§10 line 354).

- **There are three seams and one exactness risk.**
  - **Referee:** Rust compiled to WASM, chosen for the sandbox.
  - **Verifier:** graph walk plus signatures, likely chosen for speed.
  - **Recall-fold kernel:** only if R2 lands on the half-life and the repoint rebuild misses a gate.
  - **Exactness risk:** `exp`, plus `pow` if β wins. The **scan stays under D1**: arm P first.

- **The order the graph gets built in:** mile 2 decides R2 and R3 → mile 0 rulings unlock everything → mile 3 adds query-log nodes → mile 4 builds the `govern` and `seal` edges and every §9 check with its sabotage → mile 5 turns on signed transitions.

**Verified v1 references used in this brief:**
- `src/moneta/decay.py:21`: provisional half-life note
- `src/moneta/decay.py:34-35`: bounds
- `src/moneta/decay.py:48-69`: `decay_value`
- `src/moneta/decay.py:66-67`: negative-Δt clamp
- `src/moneta/decay.py:91-105`: setter
- `src/moneta/api.py:401`: `decay_all` inside query
- `src/moneta/api.py:414`: score product
- `src/moneta/api.py:420`: `signal_attention`
- `src/moneta/ecs.py:212`: clamp to 1
- `src/moneta/ecs.py:222`: `decay_all`
- `src/moneta/ecs.py:295`: cos × utility
- `src/moneta/consolidation.py:111-112`: prune key
- `src/moneta/attention_log.py:108`: `reduce_attention_log`
- `src/moneta/durability.py:119-125`: WAL unlink

**Correction to the advocates' citations:** the advocates cited the clamp as lines 61–67, 63–65, 65–67 and 66–69. The actual clamp is at `decay.py:66-67`.