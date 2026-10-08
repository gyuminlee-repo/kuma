"""The remaining 9p round-trip removals must not change what the code sees.

Two call sites were collapsed for a Windows share, where one metadata call costs
roughly 2.8 ms against 10 us on ext4:

* ``sidecar_mame.handlers.combinatorial_demux._fastq_sorted`` replaced
  ``sorted(rglob("*.fastq")) + sorted(rglob("*.fastq.gz"))``, two complete
  recursive walks of one tree, with a single bucketed walk;
* ``kuma_core.mame.ingest.demux._read_text_if_present`` replaced an ``exists()``
  guard followed by ``read_text()``, two round-trips per well, with one open.

Both are only safe if they are indistinguishable from what they replaced, so
every assertion here compares against the *original expression* rather than
against a hard-coded expectation, the way
``tests/mame/test_fs_walk_rglob_parity.py`` compares against ``Path.rglob``
itself.  The old code is spelled out in ``_legacy_*`` helpers for that purpose.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from kuma_core.mame.ingest.demux import (
    _collect_cutadapt_outputs,
    _read_text_if_present,
)
from kuma_core.mame.ingest.fasta_parser import parse_fasta_file
from kuma_core.mame.ingest.mode_router import (
    _AMPLICON_CONSENSUS_PATTERNS,
    IngestMode,
    route_ingest,
)
from sidecar_mame.handlers.combinatorial_demux import _collect_fastq, _fastq_sorted

# --------------------------------------------------------------------------
# The expressions that were replaced, kept verbatim as the oracle.
# --------------------------------------------------------------------------


def _legacy_fastq_sorted(directory: Path) -> list[Path]:
    return sorted(directory.rglob("*.fastq")) + sorted(directory.rglob("*.fastq.gz"))


def _legacy_read_text_if_present(path: Path) -> str | None:
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def _legacy_collect_cutadapt_outputs(
    output_dir: Path,
    custom_barcodes: dict[str, str],
) -> tuple[dict[str, int], int, int]:
    per_well_counts: dict[str, int] = {}
    n_assigned = 0
    for name in custom_barcodes:
        fp = output_dir / f"{name}.fasta"
        if not fp.exists():
            continue
        count = sum(
            1 for ln in fp.read_text(encoding="utf-8").splitlines()
            if ln.startswith(">")
        )
        if count:
            per_well_counts[name] = count
            n_assigned += count

    unassigned_file = output_dir / "_unassigned.fasta"
    n_unassigned = 0
    if unassigned_file.exists():
        n_unassigned = sum(
            1 for ln in unassigned_file.read_text(encoding="utf-8").splitlines()
            if ln.startswith(">")
        )
    return per_well_counts, n_assigned, n_unassigned


def _supports_symlinks(tmp_path: Path) -> bool:
    try:
        (tmp_path / "_probe_target").write_text("x", encoding="utf-8")
        (tmp_path / "_probe_link").symlink_to(tmp_path / "_probe_target")
    except (OSError, NotImplementedError):
        return False
    (tmp_path / "_probe_link").unlink()
    (tmp_path / "_probe_target").unlink()
    return True


# --------------------------------------------------------------------------
# _fastq_sorted: one walk, same list, same order
# --------------------------------------------------------------------------


@pytest.fixture()
def run_dir(tmp_path: Path) -> Path:
    """A MinKNOW-shaped tree stocked with the cases a hand-rolled walk drifts on."""
    fastq_pass = tmp_path / "run" / "fastq_pass"
    (fastq_pass / "barcode01").mkdir(parents=True)
    (fastq_pass / "barcode02" / "nested").mkdir(parents=True)
    (fastq_pass / "unclassified").mkdir()

    for rel in (
        "barcode01/PAY_0.fastq",
        "barcode01/PAY_1.fastq.gz",
        "barcode01/PAY_10.fastq",
        "barcode01/PAY_2.fastq",
        "barcode01/.hidden.fastq",
        "barcode01/notes.txt",
        "barcode01/PAY_3.FASTQ",
        "barcode02/PAY_0.fastq.gz",
        "barcode02/PAY_1.fastq",
        "barcode02/nested/PAY_9.fastq",
        "barcode02/nested/PAY_9.fastq.gz",
        "top_level.fastq",
    ):
        (fastq_pass / rel).write_text(f"@{rel}\nACGT\n+\n!!!!\n", encoding="utf-8")

    # A directory named like a data file: rglob yields it, so the walk must too.
    (fastq_pass / "decoy.fastq").mkdir()
    (fastq_pass / "decoy.fastq" / "inner.fastq").write_text("x", encoding="utf-8")
    return tmp_path / "run"


def test_fastq_sorted_matches_the_two_rglob_expression(run_dir: Path) -> None:
    """Same files, and the same order, since this list is the demux input order."""
    fastq_pass = run_dir / "fastq_pass"
    assert _fastq_sorted(fastq_pass) == _legacy_fastq_sorted(fastq_pass)


def test_fastq_sorted_keeps_groups_separate_not_merge_sorted(run_dir: Path) -> None:
    """``sorted(a) + sorted(b)``, not ``sorted(a + b)``: .fastq all precede .fastq.gz."""
    got = _fastq_sorted(run_dir / "fastq_pass")
    suffixes = [p.name.endswith(".fastq.gz") for p in got]
    assert suffixes == sorted(suffixes), got
    assert any(suffixes) and not all(suffixes)


def test_fastq_sorted_per_barcode_matches(run_dir: Path) -> None:
    """The per-native-barcode call site enumerates one subdirectory the same way."""
    for nb in ("barcode01", "barcode02"):
        nb_dir = run_dir / "fastq_pass" / nb
        assert _fastq_sorted(nb_dir) == _legacy_fastq_sorted(nb_dir)


def test_fastq_sorted_with_symlinks(run_dir: Path, tmp_path: Path) -> None:
    if not _supports_symlinks(tmp_path):
        pytest.skip("filesystem does not support symlinks")
    fastq_pass = run_dir / "fastq_pass"
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "linked.fastq").write_text("x", encoding="utf-8")

    (fastq_pass / "link_to_file.fastq").symlink_to(outside / "linked.fastq")
    (fastq_pass / "link_to_dir").symlink_to(outside, target_is_directory=True)
    (fastq_pass / "dangling.fastq").symlink_to(tmp_path / "does_not_exist")
    (fastq_pass / "loop").symlink_to(fastq_pass, target_is_directory=True)

    assert _fastq_sorted(fastq_pass) == _legacy_fastq_sorted(fastq_pass)


def test_collect_fastq_still_raises_on_missing_and_empty(tmp_path: Path) -> None:
    """The single walk did not swallow either FileNotFoundError."""
    with pytest.raises(FileNotFoundError, match="fastq_pass"):
        _collect_fastq(tmp_path / "no_such_run")

    empty = tmp_path / "empty_run"
    (empty / "fastq_pass" / "barcode01").mkdir(parents=True)
    with pytest.raises(FileNotFoundError, match="No FASTQ files"):
        _collect_fastq(empty)


def test_collect_fastq_walks_the_tree_once(run_dir: Path, monkeypatch) -> None:
    """The point of the change: exactly one ``scandir`` per directory in the tree.

    ``os.scandir`` is counted at the ``os`` boundary because that is where both
    ``Path.rglob`` and the bucketed walk enter the filesystem.  The legacy count
    is left as an inequality rather than a ratio: ``pathlib`` scans each
    directory more than once per pattern, and how many times is an internal
    detail that has changed between CPython releases.
    """
    fastq_pass = run_dir / "fastq_pass"
    n_dirs = 1 + sum(1 for p in fastq_pass.rglob("*") if p.is_dir())

    calls: list[int] = []
    real_scandir = os.scandir

    def counting_scandir(*args, **kwargs):
        calls.append(1)
        return real_scandir(*args, **kwargs)

    monkeypatch.setattr(os, "scandir", counting_scandir)

    calls.clear()
    _legacy_fastq_sorted(fastq_pass)
    legacy_scandirs = len(calls)

    calls.clear()
    _fastq_sorted(fastq_pass)
    new_scandirs = len(calls)

    assert new_scandirs == n_dirs, (new_scandirs, n_dirs)
    assert legacy_scandirs > new_scandirs, (legacy_scandirs, new_scandirs)


# --------------------------------------------------------------------------
# _read_text_if_present: one open where there were exists() + read_text()
# --------------------------------------------------------------------------


def test_read_text_if_present_matches_exists_guard(tmp_path: Path) -> None:
    present = tmp_path / "A01.fasta"
    present.write_text(">r1\nACGT\n", encoding="utf-8")
    missing = tmp_path / "A02.fasta"
    empty = tmp_path / "A03.fasta"
    empty.write_text("", encoding="utf-8")
    under_a_file = present / "not_a_dir" / "A04.fasta"  # ENOTDIR

    for path in (present, missing, empty, under_a_file):
        assert _read_text_if_present(path) == _legacy_read_text_if_present(path), path


def test_read_text_if_present_treats_dangling_symlink_as_absent(
    tmp_path: Path,
) -> None:
    if not _supports_symlinks(tmp_path):
        pytest.skip("filesystem does not support symlinks")
    dangling = tmp_path / "A05.fasta"
    dangling.symlink_to(tmp_path / "gone")
    assert _legacy_read_text_if_present(dangling) is None
    assert _read_text_if_present(dangling) is None


def test_read_text_if_present_still_raises_where_exists_raised(tmp_path: Path) -> None:
    """EISDIR and EACCES are outside the ignored set, so both spellings raise."""
    a_dir = tmp_path / "A06.fasta"
    a_dir.mkdir()
    # Windows reports EACCES where POSIX reports EISDIR. Both are outside the
    # ignored set, which is what this asserts; pinning the POSIX spelling made
    # the test a platform check instead.
    opening_a_directory = (IsADirectoryError, PermissionError)
    with pytest.raises(opening_a_directory):
        _legacy_read_text_if_present(a_dir)
    with pytest.raises(opening_a_directory):
        _read_text_if_present(a_dir)

    if os.name != "posix" or os.geteuid() == 0:
        return
    locked = tmp_path / "A07.fasta"
    locked.write_text(">r1\nACGT\n", encoding="utf-8")
    locked.chmod(0o000)
    try:
        with pytest.raises(PermissionError):
            _legacy_read_text_if_present(locked)
        with pytest.raises(PermissionError):
            _read_text_if_present(locked)
    finally:
        locked.chmod(0o644)


def _write_plate(output_dir: Path, present: dict[str, int]) -> dict[str, str]:
    """96 declared barcodes, only *present* of which cutadapt actually emitted."""
    output_dir.mkdir(parents=True, exist_ok=True)
    barcodes = {
        f"{row}{col:02d}": "ACGT"
        for row in "ABCDEFGH"
        for col in range(1, 13)
    }
    for name, n_reads in present.items():
        body = "".join(f">{name}_r{i}\nACGT\n" for i in range(n_reads))
        (output_dir / f"{name}.fasta").write_text(body, encoding="utf-8")
    return barcodes


def test_collect_cutadapt_outputs_matches_the_exists_guarded_version(
    tmp_path: Path,
) -> None:
    out = tmp_path / "demux"
    # A01 has reads, A02 is an empty file (present but zero-count), the rest absent.
    barcodes = _write_plate(out, {"A01": 3, "B05": 1, "A02": 0})
    (out / "_unassigned.fasta").write_text(">u1\nACGT\n>u2\nACGT\n", encoding="utf-8")

    assert _collect_cutadapt_outputs(out, barcodes) == _legacy_collect_cutadapt_outputs(
        out, barcodes
    )


def test_collect_cutadapt_outputs_matches_without_unassigned_file(
    tmp_path: Path,
) -> None:
    out = tmp_path / "demux"
    barcodes = _write_plate(out, {"H12": 7})
    assert not (out / "_unassigned.fasta").exists()
    assert _collect_cutadapt_outputs(out, barcodes) == _legacy_collect_cutadapt_outputs(
        out, barcodes
    )


def test_collect_cutadapt_outputs_matches_on_an_empty_plate(tmp_path: Path) -> None:
    out = tmp_path / "demux"
    barcodes = _write_plate(out, {})
    assert _collect_cutadapt_outputs(out, barcodes) == _legacy_collect_cutadapt_outputs(
        out, barcodes
    )
    assert _collect_cutadapt_outputs(out, barcodes) == ({}, 0, 0)


def test_collect_cutadapt_outputs_halves_the_metadata_calls(
    tmp_path: Path, monkeypatch
) -> None:
    """One open per well replaces stat-then-open, on a plate that is mostly absent.

    ``os.stat`` is where ``Path.exists()`` lands and ``io.open`` is where
    ``Path.read_text`` lands, so both are counted at those boundaries rather
    than by wall time, which says nothing under a shared machine load.
    """
    out = tmp_path / "demux"
    barcodes = _write_plate(out, {"A01": 3, "B05": 1})
    # 96 wells plus _unassigned.fasta; only 2 wells exist on disk.
    n_candidates = len(barcodes) + 1
    n_on_disk = 2

    import io

    counters = {"stat": 0, "open": 0}
    real_stat = os.stat
    real_open = io.open

    def counting_stat(*args, **kwargs):
        counters["stat"] += 1
        return real_stat(*args, **kwargs)

    def counting_open(*args, **kwargs):
        counters["open"] += 1
        return real_open(*args, **kwargs)

    monkeypatch.setattr(os, "stat", counting_stat)
    monkeypatch.setattr(io, "open", counting_open)

    counters.update(stat=0, open=0)
    _legacy_collect_cutadapt_outputs(out, barcodes)
    legacy = dict(counters)

    counters.update(stat=0, open=0)
    _collect_cutadapt_outputs(out, barcodes)
    new = dict(counters)

    # Before: one stat for every candidate, then a second round-trip (open) for
    # the few that existed. After: one open per candidate and no stat at all.
    assert legacy == {"stat": n_candidates, "open": n_on_disk}, legacy
    assert new == {"stat": 0, "open": n_candidates}, new
    assert new["stat"] + new["open"] < legacy["stat"] + legacy["open"]


def test_collect_cutadapt_outputs_saving_scales_with_how_full_the_plate_is(
    tmp_path: Path, monkeypatch
) -> None:
    """A sparse plate saves little; a full plate halves the round-trips.

    Worth pinning because the sparse case above understates the change: the
    saving is one round-trip per *existing* file, so it is largest exactly when
    the run went well and every well produced reads.
    """
    out = tmp_path / "demux"
    barcodes = _write_plate(out, {})
    for name in barcodes:
        (out / f"{name}.fasta").write_text(f">{name}_r0\nACGT\n", encoding="utf-8")
    (out / "_unassigned.fasta").write_text(">u\nACGT\n", encoding="utf-8")
    n_candidates = len(barcodes) + 1

    import io

    counters = {"n": 0}
    real_stat, real_open = os.stat, io.open

    def bump(fn):
        def wrapped(*args, **kwargs):
            counters["n"] += 1
            return fn(*args, **kwargs)

        return wrapped

    monkeypatch.setattr(os, "stat", bump(real_stat))
    monkeypatch.setattr(io, "open", bump(real_open))

    counters["n"] = 0
    legacy_result = _legacy_collect_cutadapt_outputs(out, barcodes)
    legacy_calls = counters["n"]

    counters["n"] = 0
    new_result = _collect_cutadapt_outputs(out, barcodes)
    new_calls = counters["n"]

    assert new_result == legacy_result
    assert legacy_calls == 2 * n_candidates, legacy_calls
    assert new_calls == n_candidates, new_calls


# --------------------------------------------------------------------------
# _load_amplicon: one walk for two patterns, and a free file_size_kb
# --------------------------------------------------------------------------


def _legacy_load_amplicon(input_dir: Path):
    records = []
    seen: set[Path] = set()
    for pattern in _AMPLICON_CONSENSUS_PATTERNS:
        for consensus_file in sorted(input_dir.rglob(pattern)):
            if consensus_file in seen:
                continue
            seen.add(consensus_file)
            native = consensus_file.stem.replace("-consensus", "") or "AMPLICON"
            records.append(parse_fasta_file(consensus_file, native_barcode=native))
    return records


@pytest.fixture()
def amplicon_dir(tmp_path: Path) -> Path:
    """A nested consensus tree using both accepted extensions."""
    root = tmp_path / "amplicon"
    (root / "run_a").mkdir(parents=True)
    (root / "run_b" / "deep").mkdir(parents=True)
    for rel in (
        "sampleA-consensus.fasta",
        "run_a/sampleB-consensus.fasta",
        "run_a/sampleC-consensus.fa",
        "run_b/sampleD-consensus.fa",
        "run_b/deep/sampleE-consensus.fasta",
        "run_a/ignored.fasta",
        "run_a/notes.txt",
    ):
        (root / rel).write_text(f">{Path(rel).stem}\nACGTACGTACGT\n", encoding="utf-8")
    return root


def test_load_amplicon_matches_the_two_rglob_version(amplicon_dir: Path) -> None:
    """Same records, same order, same sizes as the two-walk original."""
    got = route_ingest(amplicon_dir, IngestMode.AMPLICON)
    expected = _legacy_load_amplicon(amplicon_dir)
    assert [r.native_barcode for r in got] == [r.native_barcode for r in expected]
    assert [r.file_size_kb for r in got] == [r.file_size_kb for r in expected]
    assert got == expected


def test_load_amplicon_keeps_pattern_groups_in_order(amplicon_dir: Path) -> None:
    """``.fasta`` matches all precede ``.fa`` matches, as the pattern loop did.

    Within a group the order is ``sorted()`` over full paths, so nested
    directories sort before the root-level file (``run_a/`` < ``run_b/`` <
    ``sampleA-``), which is what the original expression produced too.
    """
    got = route_ingest(amplicon_dir, IngestMode.AMPLICON)
    names = [r.native_barcode for r in got]
    assert names == ["sampleB", "sampleE", "sampleA", "sampleC", "sampleD"], names


def test_load_amplicon_on_an_empty_tree(tmp_path: Path) -> None:
    empty = tmp_path / "nothing"
    empty.mkdir()
    assert route_ingest(empty, IngestMode.AMPLICON) == _legacy_load_amplicon(empty) == []


def test_load_amplicon_walks_once_and_does_not_restat_each_file(
    amplicon_dir: Path, monkeypatch
) -> None:
    """One ``scandir`` per directory instead of one per directory per pattern.

    The saving being pinned here is the *walk*, not the per-file size lookup.
    Passing the ``DirEntry`` down to ``parse_fasta_file`` moves ``file_size_kb``
    off ``Path.stat()`` and onto ``DirEntry.stat()``, which on Linux still
    issues a syscall (``scandir``'s ``d_type`` carries the file type but not
    ``st_size``); it resolves against the directory fd rather than the full
    path, so it is cheaper on a share but not free.  ``os.stat`` going to zero
    below therefore records where the call moved, not a call that vanished --
    ``DirEntry.stat`` is a C method and this monkeypatch cannot observe it.
    ``scripts/verify_9p_sweep.py`` wraps the entries in a counting proxy to
    measure the real total.
    """
    n_dirs = 1 + sum(1 for p in amplicon_dir.rglob("*") if p.is_dir())

    counters = {"scandir": 0, "stat": 0}
    real_scandir, real_stat = os.scandir, os.stat

    def counting_scandir(*a, **k):
        counters["scandir"] += 1
        return real_scandir(*a, **k)

    def counting_stat(*a, **k):
        counters["stat"] += 1
        return real_stat(*a, **k)

    monkeypatch.setattr(os, "scandir", counting_scandir)
    monkeypatch.setattr(os, "stat", counting_stat)

    counters.update(scandir=0, stat=0)
    _legacy_load_amplicon(amplicon_dir)
    legacy = dict(counters)

    counters.update(scandir=0, stat=0)
    route_ingest(amplicon_dir, IngestMode.AMPLICON)
    new = dict(counters)

    n_consensus_files = 5
    assert new["scandir"] == n_dirs, (new, n_dirs)
    assert legacy["scandir"] > new["scandir"], (legacy, new)
    # Every consensus file used to reach the filesystem through ``os.stat``;
    # now none do, because the lookup moved onto the walk's ``DirEntry``.
    # The legacy figure is a lower bound: ``Path.rglob`` adds stats of its own
    # that are a CPython internal detail.
    assert legacy["stat"] >= n_consensus_files, legacy
    assert new["stat"] == 0, new
