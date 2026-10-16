"""Mutation check for the v5 suite: each mutation must make its test fail.

Run from the repo root on a scratch copy (it edits files and restores them):
    cp -r . /tmp/moneta-mut && cd /tmp/moneta-mut && python scripts/v5/mutation_check.py
"""

import pathlib
import subprocess
import sys

MUTS = [
    (
        "M5 no lock in signal_attention",
        "src/moneta/v5/substrate.py",
        """        with self._lock:
            self._check_open()
            when = self._t(t)
            clean: dict[str, float] = {}""",
        """        if True:
            self._check_open()
            when = self._t(t)
            clean: dict[str, float] = {}""",
        "tests/v5/test_review_regressions.py::test_every_fold_apply_holds_the_substrate_lock",
    ),
    (
        "M6 compaction keeps emb",
        "src/moneta/v5/substrate.py",
        """                    event["emb"] = None
                    event["erased"] = True""",
        """                    event["erased"] = True""",
        "tests/v5/test_review_regressions.py::test_compact_scrubs_erased_vectors_everywhere",
    ),
    (
        "M6b compaction keeps revector vectors",
        "src/moneta/v5/substrate.py",
        """                        event["vectors"] = {k: v for k, v in vectors.items() if k not in erased}""",
        """                        pass""",
        "tests/v5/test_review_regressions.py::test_compact_scrubs_erased_vectors_everywhere",
    ),
    (
        "M7 skip torn-tail truncate",
        "src/moneta/v5/journal.py",
        """                os.ftruncate(self._fd, good)
                os.fsync(self._fd)""",
        """                pass""",
        "tests/v5/test_review_regressions.py::test_recovered_journal_reopens_after_further_writes",
    ),
    (
        "M8 skip seq check",
        "src/moneta/v5/journal.py",
        """        if event["seq"] != expected_seq:""",
        """        if False:""",
        "tests/v5/test_review_regressions.py::test_sequence_gaps_and_duplicates_are_corruption",
    ),
    (
        "M2b recall bumps attended",
        "src/moneta/v5/substrate.py",
        """                u = rec.utility_at(self.lam, when)
                scored.append""",
        """                u = rec.utility_at(self.lam, when); rec.attended += 0 if u is None else 1
                scored.append""",
        "tests/v5/test_review_regressions.py::test_reads_leave_all_record_state_untouched",
    ),
    (
        "M2c explain edits reason",
        "src/moneta/v5/substrate.py",
        """            verdicts, winners = self._verdicts(policy, allowed)
            verdict = verdicts[eid]""",
        '''            verdicts, winners = self._verdicts(policy, allowed)
            verdict = verdicts[eid]; rec.status_reason = "touched"''',
        "tests/v5/test_review_regressions.py::test_reads_leave_all_record_state_untouched",
    ),
    (
        "F1 no dim validation",
        "src/moneta/v5/substrate.py",
        """        if dim is not None and (isinstance(dim, bool) or not isinstance(dim, int) or dim < 1):
            raise ValueError(f"embedding_dim must be a positive int or None, got {dim!r}")""",
        """        pass""",
        "tests/v5/test_review_regressions.py::test_bad_embedding_dim_never_reaches_the_journal",
    ),
    (
        "F5 key returns dead id",
        "src/moneta/v5/substrate.py",
        """                if existing.status in RECALLABLE:""",
        """                if True:""",
        "tests/v5/test_review_regressions.py::test_key_of_a_dead_memory_deposits_a_new_one",
    ),
    (
        "I4 index miss silently skipped",
        "src/moneta/v5/index.py",
        """                raise KeyError(f"index has no vector for recallable record {eid}")""",
        """                continue""",
        "tests/v5/test_review_regressions.py::test_index_miss_raises_instead_of_dropping_a_memory",
    ),
    (
        "guard: corrupt snapshot refused",
        "src/moneta/v5/compat.py",
        """        return {"ignored_unreadable_snapshot": True}""",
        """        raise diverged("unreadable")""",
        "tests/v5/test_compat.py::test_corrupt_snapshot_is_ignored_not_fatal",
    ),
    (
        "guard: stale export refused",
        "src/moneta/v5/compat.py",
        """    seq = substrate.revector(vectors, dim=configured_dim, allow_missing=True)""",
        """    seq = substrate.revector(vectors, dim=configured_dim, allow_missing=False)""",
        "tests/v5/test_compat.py::test_embedder_swap_from_a_stale_export_keeps_every_memory",
    ),
    (
        "guard: journal note shas ignored",
        "src/moneta/v5/compat.py",
        """    if sha in _read_known_shas(journal) or sha in _journal_known_shas(substrate):""",
        """    if sha in _read_known_shas(journal):""",
        "tests/v5/test_compat.py::test_missing_sidecar_after_a_crash_is_not_a_second_writer",
    ),
    (
        "HL1 mismatched half-life open not refused",
        "src/moneta/v5/substrate.py",
        """                if half_life_change is None:
                    raise HalfLifeMismatchError(""",
        """                if False:
                    raise HalfLifeMismatchError(""",
        "tests/v5/test_half_life.py::test_default_config_open_on_a_non_default_store_refuses_and_writes_nothing",
    ),
    (
        "HL2 first pass after a change not held as a dry run",
        "src/moneta/v5/substrate.py",
        """            if pending is not None and not confirm_half_life_change:""",
        """            if False:""",
        "tests/v5/test_half_life.py::test_change_then_dry_run_then_confirm",
    ),
    (
        "HL3 forward change does not rebase anchors",
        "src/moneta/v5/model.py",
        """                rec.anchor_u = rec.utility_at(old_lam, t)
                rec.anchor_t = t""",
        """                pass""",
        "tests/v5/test_half_life.py::test_forward_keeps_history_and_applies_the_new_value_after_the_change",
    ),
    (
        "E1C1 half-migrated journal not detected",
        "src/moneta/v5/compat.py",
        """    if progress["begin"] is not None or progress["imports"]:
        reason = "begun\"""",
        """    if False:
        reason = "begun\"""",
        "tests/v5/test_compat.py::test_hard_kill_mid_migration_reopens_with_every_record[20-appends]",
    ),
    (
        "E1C1 no begin marker journaled",
        "src/moneta/v5/compat.py",
        """            "kind": MIGRATION_BEGIN,""",
        """            "kind": "v1_migration_start",""",
        "tests/v5/test_compat.py::test_hard_kill_mid_migration_reopens_with_every_record[begin-note]",
    ),
    (
        "E1C1 interrupted migration decided by file existence",
        "src/moneta/v5/compat.py",
        """            if not fresh and snapshot is not None:
                # Whether to migrate""",
        """            if False:
                # Whether to migrate""",
        "tests/v5/test_compat.py::test_hard_kill_mid_migration_reopens_with_every_record[all-but-completion]",
    ),
    (
        "E1C1 writes after an interrupted migration hidden by a restart",
        "src/moneta/v5/compat.py",
        """    if progress["foreign_op"] is not None:
        raise incomplete(""",
        """    if False:
        raise incomplete(""",
        "tests/v5/test_compat.py::test_writes_after_an_interrupted_migration_are_refused_not_hidden",
    ),
    (
        "E1C1 half-life change journaled before the migration check",
        "src/moneta/v5/compat.py",
        """                    self.v5 = open_substrate(fresh)
                except HalfLifeMismatchError""",
        """                    self.v5 = open_substrate(fresh, change=half_life_change)
                except HalfLifeMismatchError""",
        "tests/v5/test_compat.py::test_hard_kill_then_a_half_life_change_restarts_before_journaling_the_change",
    ),
]
failed_to_catch = []
for name, path, old, new, test in MUTS:
    p = pathlib.Path(path)
    src = p.read_text()
    assert src.count(old) == 1, (name, src.count(old))
    p.write_text(src.replace(old, new))
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-x", test],
        capture_output=True,
        text=True,
    )
    p.write_text(src)
    caught = r.returncode != 0
    print(("caught " if caught else "MISSED ") + name)
    if not caught:
        failed_to_catch.append(name)
print("missed:", failed_to_catch)
