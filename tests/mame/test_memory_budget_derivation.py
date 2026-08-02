"""Guards for the adaptive sizing of the two MAME demux memory bounds.

``KUMA_MAME_WELL_BUFFER_MB`` and ``KUMA_MAME_CONSENSUS_BATCH_MB`` used to be
fixed constants read off one 10-core / 15 GiB box. They are now derived from the
memory limit divided by the number of concurrent native-barcode workers, so the
properties worth pinning are:

* the derivation reproduces the previously measured values on the box they were
  measured on (otherwise the formula is wrong, not merely different);
* it scales down on a small box and up on a large one, monotonically;
* the clamps hold at both extremes;
* an explicit environment variable always wins, including the documented ``0``
  that disables a bound;
* a container limit beats the physical RAM figure, and the tightest limit on a
  nested cgroup path wins.

Output identity under extreme budgets is covered by the perf harness
(``scripts/perf_step2_harness.py``), not here: it needs the real fixture.
"""

from __future__ import annotations

import pytest

from kuma_core.mame.ingest import combinatorial_demux as cd


GIB = 1024**3


def _budgets(limit_bytes: int, workers: int) -> tuple[int, int]:
    """(well buffer MB, consensus batch MB) derived for a hypothetical box."""
    well = cd._derive_mb(
        limit_bytes,
        workers,
        cd._WELL_BUFFER_FRACTION,
        cd._WELL_BUFFER_MB_MIN,
        cd._WELL_BUFFER_MB_MAX,
        cd._WELL_BUFFER_MB_DEFAULT,
    )
    batch = cd._derive_mb(
        limit_bytes,
        workers,
        cd._CONSENSUS_BATCH_FRACTION,
        cd._CONSENSUS_BATCH_MB_MIN,
        cd._CONSENSUS_BATCH_MB_MAX,
        cd._CONSENSUS_BATCH_MB_DEFAULT,
    )
    return well, batch


def test_reproduces_the_measured_values_on_the_box_they_were_tuned_on():
    """15 GiB / 3 workers must land near the measured 512 and 32 MB.

    This is the calibration anchor. Every performance number recorded in
    ``notes/perf/memory-bound.md`` was taken at 512 / 32, so a formula that does
    not reproduce them there has silently invalidated that evidence.
    """
    # /proc/meminfo MemTotal on the reference box, in decimal bytes.
    well, batch = _budgets(16_424_587_264, 3)
    assert 460 <= well <= 620, f"well buffer {well} MB is not near the measured 512"
    assert 28 <= batch <= 40, f"consensus batch {batch} MB is not near the measured 32"


@pytest.mark.parametrize("workers", [1, 3, 8])
def test_budget_is_monotone_in_the_limit(workers: int):
    """More RAM never yields a smaller budget."""
    seen = [_budgets(gib * GIB, workers) for gib in (2, 4, 8, 16, 32, 64, 128)]
    wells = [w for w, _ in seen]
    batches = [b for _, b in seen]
    assert wells == sorted(wells), wells
    assert batches == sorted(batches), batches


@pytest.mark.parametrize("gib", [4, 16, 64])
def test_budget_is_non_increasing_in_the_worker_count(gib: int):
    """Splitting the box across more workers never RAISES a per-worker budget.

    This is the term the old fixed constants missed entirely: three workers each
    took the whole-box budget, so the box was asked for 3x what was measured.
    """
    seen = [_budgets(gib * GIB, w) for w in (1, 2, 3, 4, 8, 16)]
    wells = [w for w, _ in seen]
    batches = [b for _, b in seen]
    assert wells == sorted(wells, reverse=True), wells
    assert batches == sorted(batches, reverse=True), batches


def test_small_box_scales_down_below_the_tuned_values():
    """An 8 GiB laptop running three workers must ask for less than 512 / 32.

    The whole point of the change: at the fixed defaults that box was asked for
    3 x 512 MB of slice text (~2.5 GB resident after object overhead) plus three
    batch pileups, on top of the aligner.
    """
    well, batch = _budgets(8 * GIB, 3)
    assert well < 512
    assert batch < 32


def test_large_box_scales_up_above_the_tuned_values():
    well, batch = _budgets(64 * GIB, 3)
    assert well > 512
    assert batch > 32


def test_clamps_hold_at_both_extremes():
    tiny_well, tiny_batch = _budgets(64 * 1024 * 1024, 16)
    assert tiny_well == cd._WELL_BUFFER_MB_MIN
    assert tiny_batch == cd._CONSENSUS_BATCH_MB_MIN

    huge_well, huge_batch = _budgets(4096 * GIB, 1)
    assert huge_well == cd._WELL_BUFFER_MB_MAX
    assert huge_batch == cd._CONSENSUS_BATCH_MB_MAX


def test_unknown_limit_falls_back_to_the_fixed_constants():
    """Windows has neither /proc nor os.sysconf; it must keep the old defaults."""
    well, batch = _budgets(None, 3)  # type: ignore[arg-type]
    assert well == cd._WELL_BUFFER_MB_DEFAULT
    assert batch == cd._CONSENSUS_BATCH_MB_DEFAULT


@pytest.mark.parametrize(
    "env_name,key",
    [
        ("KUMA_MAME_WELL_BUFFER_MB", "well_buffer_mb"),
        ("KUMA_MAME_CONSENSUS_BATCH_MB", "consensus_batch_mb"),
    ],
)
def test_explicit_env_wins_over_derivation(monkeypatch, env_name: str, key: str):
    monkeypatch.setenv(env_name, "777")
    info = cd._resolve_memory_budgets(3)
    assert info[key] == 777
    assert info[key + "_source"] == "env"


@pytest.mark.parametrize(
    "env_name,key",
    [
        ("KUMA_MAME_WELL_BUFFER_MB", "well_buffer_mb"),
        ("KUMA_MAME_CONSENSUS_BATCH_MB", "consensus_batch_mb"),
    ],
)
def test_env_zero_still_disables_the_bound(monkeypatch, env_name: str, key: str):
    """``0`` is documented as "no bound" and must not be treated as unset."""
    monkeypatch.setenv(env_name, "0")
    info = cd._resolve_memory_budgets(3)
    assert info[key] == 0
    assert info[key + "_source"] == "env"


@pytest.mark.parametrize(
    "env_name", ["KUMA_MAME_WELL_BUFFER_MB", "KUMA_MAME_CONSENSUS_BATCH_MB"]
)
def test_garbage_env_falls_back_to_derivation(monkeypatch, env_name: str):
    """A typo must not crash a run mid-pipeline."""
    monkeypatch.setenv(env_name, "not-a-number")
    info = cd._resolve_memory_budgets(3)
    assert info["well_buffer_mb"] > 0
    assert info["consensus_batch_mb"] > 0


def test_resolve_reports_its_provenance():
    info = cd._resolve_memory_budgets(3)
    assert info["mem_workers"] == 3
    assert info["mem_limit_source"] in {
        "cgroup_v2",
        "cgroup_v1",
        "meminfo",
        "unknown",
    }
    for key in ("well_buffer_mb", "consensus_batch_mb"):
        assert info[key + "_source"] in {"derived", "env", "fallback"}


def test_container_limit_beats_physical_ram(monkeypatch):
    """MemTotal inside a container is the HOST's RAM; the cgroup cap must win."""
    monkeypatch.setattr(cd, "_read_phys_mem", lambda: 512 * GIB)
    monkeypatch.setattr(cd, "_read_cgroup_v2_limit", lambda: 2 * GIB)
    limit, source = cd._memory_limit_bytes()
    assert limit == 2 * GIB
    assert source == "cgroup_v2"


def test_cgroup_above_physical_ram_defers_to_the_box(monkeypatch):
    """An unconstrained runtime can cap above RAM; the smaller figure binds."""
    monkeypatch.setattr(cd, "_read_phys_mem", lambda: 8 * GIB)
    monkeypatch.setattr(cd, "_read_cgroup_v2_limit", lambda: 512 * GIB)
    limit, source = cd._memory_limit_bytes()
    assert limit == 8 * GIB
    assert source == "meminfo"


def _write_cgroup_tree(tmp_path, rel: str, limits: dict[str, str]):
    """Build a temp-dir replica of a cgroup v2 hierarchy.

    *limits* maps a path relative to the cgroup root to a ``memory.max`` body.
    Returns ``(root, proc_cgroup_file)`` ready to pass to the reader.
    """
    root = tmp_path / "cgroup"
    (root / rel.lstrip("/")).mkdir(parents=True)
    for sub, body in limits.items():
        node = root / sub.lstrip("/") if sub else root
        node.mkdir(parents=True, exist_ok=True)
        (node / "memory.max").write_text(body)
    proc = tmp_path / "proc_cgroup"
    proc.write_text(f"0::{rel}\n")
    return root, proc


def test_nested_cgroup_takes_the_tightest_limit(tmp_path):
    """A pod inside a capped slice is bound by the slice, not by its own leaf.

    The leaf here is the LOOSER of the two, so a reader that stops at the leaf
    returns 8 GiB and over-sizes by 8x against what the kernel will enforce.
    """
    root, proc = _write_cgroup_tree(
        tmp_path,
        "/parent.slice/child.scope",
        {
            "parent.slice": "1073741824\n",  # 1 GiB, the binding cap
            "parent.slice/child.scope": "8589934592\n",  # 8 GiB, looser leaf
        },
    )
    assert cd._read_cgroup_v2_limit(root=root, proc_cgroup=proc) == 1 * GIB


def test_cgroup_max_on_every_level_means_unlimited(tmp_path):
    root, proc = _write_cgroup_tree(
        tmp_path,
        "/parent.slice/child.scope",
        {"parent.slice": "max\n", "parent.slice/child.scope": "max\n"},
    )
    assert cd._read_cgroup_v2_limit(root=root, proc_cgroup=proc) is None


def test_cgroup_leaf_limit_is_found_when_ancestors_are_unlimited(tmp_path):
    root, proc = _write_cgroup_tree(
        tmp_path,
        "/parent.slice/child.scope",
        {
            "parent.slice": "max\n",
            "parent.slice/child.scope": "2147483648\n",  # 2 GiB
        },
    )
    assert cd._read_cgroup_v2_limit(root=root, proc_cgroup=proc) == 2 * GIB


def test_missing_proc_cgroup_is_not_fatal(tmp_path):
    """Non-Linux and stripped containers must degrade, not raise."""
    assert (
        cd._read_cgroup_v2_limit(
            root=tmp_path / "nope", proc_cgroup=tmp_path / "absent"
        )
        is None
    )
