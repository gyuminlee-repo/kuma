# ruff: noqa: T201
"""Verifier for the round-trip removals that ``perf_step2_harness.py`` cannot reach.

The step 2 harness runs detect + combinatorial demux + analyze with
``ingest_mode="barcode"``, so it exercises one of the three changed call sites
and not the other two:

===========================================  ==============================
call site                                    covered by perf_step2_harness?
===========================================  ==============================
handlers/combinatorial_demux._fastq_sorted   yes (both :63 and :160 paths)
ingest/mode_router._load_amplicon            no (amplicon ingest mode only)
ingest/demux._collect_cutadapt_outputs       no (cutadapt backend only)
===========================================  ==============================

For the two uncovered sites this script does what ``verify_demux_and_filter.py``
does for its own path: it runs the *old* expression and the *new* one over the
same real inputs and compares the full result, so identity is established by
construction rather than by a fingerprint that never observed the code.

It also reports an interleaved A/B wall time and, more importantly, an
``os``-boundary syscall count.  Counts are the load-independent evidence: three
optimization agents share this machine, so a wall-time delta measured in
isolation would not be trustworthy, whereas a syscall count is unaffected by
what else is running.  ``DirEntry.stat`` is a C method that cannot be patched on
the type, so entries are wrapped in a counting proxy where they are counted.

Usage
-----
    export KURO_MINIMAP2="$REPO_ROOT/python-core/vendor/minimap2/linux-x64/minimap2"
    .venv/bin/python scripts/verify_9p_sweep.py \
        --tree <a directory holding *-consensus.fasta files> \
        --plate-root "$WORKSPACE_ROOT/.kuma-perf-9p/plate"
"""

from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Callable

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(_REPO / "python-core"))

from kuma_core.mame.ingest.demux import _collect_cutadapt_outputs  # noqa: E402
from kuma_core.mame.ingest.fasta_parser import parse_fasta_file  # noqa: E402
from kuma_core.mame.ingest.mode_router import (  # noqa: E402
    _AMPLICON_CONSENSUS_PATTERNS,
    IngestMode,
    route_ingest,
)
from sidecar_mame.handlers.combinatorial_demux import _fastq_sorted  # noqa: E402


# ---------------------------------------------------------------------------
# The replaced expressions, kept verbatim as the oracle.
# ---------------------------------------------------------------------------


def legacy_fastq_sorted(directory: Path) -> list[Path]:
    return sorted(directory.rglob("*.fastq")) + sorted(directory.rglob("*.fastq.gz"))


def legacy_load_amplicon(input_dir: Path) -> list[Any]:
    records: list[Any] = []
    seen: set[Path] = set()
    for pattern in _AMPLICON_CONSENSUS_PATTERNS:
        for consensus_file in sorted(input_dir.rglob(pattern)):
            if consensus_file in seen:
                continue
            seen.add(consensus_file)
            native = consensus_file.stem.replace("-consensus", "") or "AMPLICON"
            records.append(parse_fasta_file(consensus_file, native_barcode=native))
    return records


def legacy_collect_cutadapt_outputs(
    output_dir: Path, custom_barcodes: dict[str, str]
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


# ---------------------------------------------------------------------------
# Syscall counting at the ``os`` boundary
# ---------------------------------------------------------------------------


class _CountingEntry:
    """``os.DirEntry`` proxy that counts ``stat``.

    ``DirEntry.stat`` is a C method on a C type, so it cannot be monkeypatched
    the way ``os.stat`` can.  Counting the new code without counting this would
    understate it and flatter the result, so the proxy exists to keep the
    comparison honest rather than to change behaviour.
    """

    __slots__ = ("_entry", "_counter")

    def __init__(self, entry: os.DirEntry, counter: dict[str, int]) -> None:
        self._entry = entry
        self._counter = counter

    def stat(self, *a: Any, **k: Any) -> os.stat_result:
        self._counter["stat"] += 1
        return self._entry.stat(*a, **k)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._entry, name)


class SyscallCounter:
    """Patch ``os.stat``/``os.lstat``/``os.scandir`` and ``io.open`` and tally."""

    def __init__(self, *, wrap_entries: bool = True) -> None:
        self.counts: dict[str, int] = {}
        self._wrap_entries = wrap_entries
        self._saved: dict[str, Any] = {}

    def __enter__(self) -> "SyscallCounter":
        self.counts = {"stat": 0, "lstat": 0, "scandir": 0, "open": 0}
        counts = self.counts
        self._saved = {
            "stat": os.stat,
            "lstat": os.lstat,
            "scandir": os.scandir,
            "open": io.open,
        }
        real = self._saved
        wrap = self._wrap_entries

        def stat(*a: Any, **k: Any) -> Any:
            counts["stat"] += 1
            return real["stat"](*a, **k)

        def lstat(*a: Any, **k: Any) -> Any:
            counts["lstat"] += 1
            return real["lstat"](*a, **k)

        def open_(*a: Any, **k: Any) -> Any:
            counts["open"] += 1
            return real["open"](*a, **k)

        class _Scandir:
            def __init__(self, *a: Any, **k: Any) -> None:
                counts["scandir"] += 1
                self._it = real["scandir"](*a, **k)

            def __iter__(self):
                for entry in self._it:
                    yield _CountingEntry(entry, counts) if wrap else entry

            def __enter__(self):
                return iter(self)

            def __exit__(self, *exc: Any) -> None:
                self._it.close()

            def close(self) -> None:
                self._it.close()

        os.stat = stat  # type: ignore[assignment]
        os.lstat = lstat  # type: ignore[assignment]
        os.scandir = _Scandir  # type: ignore[assignment]
        io.open = open_  # type: ignore[assignment]
        return self

    def __exit__(self, *exc: Any) -> None:
        os.stat = self._saved["stat"]  # type: ignore[assignment]
        os.lstat = self._saved["lstat"]  # type: ignore[assignment]
        os.scandir = self._saved["scandir"]  # type: ignore[assignment]
        io.open = self._saved["open"]  # type: ignore[assignment]

    def total(self) -> int:
        return sum(self.counts.values())


def count_calls(fn: Callable[[], Any]) -> tuple[Any, dict[str, int], int]:
    with SyscallCounter() as counter:
        result = fn()
    return result, dict(counter.counts), counter.total()


def interleaved_ab(
    legacy: Callable[[], Any],
    new: Callable[[], Any],
    repeat: int,
) -> dict[str, Any]:
    """Alternate A and B so a load spike hits both arms, and report medians."""
    legacy_walls: list[float] = []
    new_walls: list[float] = []
    for _ in range(repeat):
        t0 = time.perf_counter()
        legacy()
        legacy_walls.append(time.perf_counter() - t0)
        t0 = time.perf_counter()
        new()
        new_walls.append(time.perf_counter() - t0)
    lo = statistics.median(legacy_walls)
    hi = statistics.median(new_walls)
    return {
        "legacy_s_median": round(lo, 5),
        "new_s_median": round(hi, 5),
        "delta_pct": round((hi - lo) / lo * 100, 1) if lo else None,
        "legacy_s_runs": [round(v, 5) for v in legacy_walls],
        "new_s_runs": [round(v, 5) for v in new_walls],
    }


# ---------------------------------------------------------------------------
# Cases
# ---------------------------------------------------------------------------


def case_fastq_sorted(fastq_pass: Path, repeat: int) -> dict[str, Any]:
    old, old_counts, old_total = count_calls(lambda: legacy_fastq_sorted(fastq_pass))
    new, new_counts, new_total = count_calls(lambda: _fastq_sorted(fastq_pass))
    return {
        "site": "python-core/sidecar_mame/handlers/combinatorial_demux.py::_fastq_sorted",
        "in_perf_harness": True,
        "input": str(fastq_pass),
        "n_files": len(new),
        "identical": old == new,
        "syscalls_before": old_counts,
        "syscalls_after": new_counts,
        "syscalls_before_total": old_total,
        "syscalls_after_total": new_total,
        "timing": interleaved_ab(
            lambda: legacy_fastq_sorted(fastq_pass),
            lambda: _fastq_sorted(fastq_pass),
            repeat,
        ),
    }


def case_load_amplicon(tree: Path, repeat: int) -> dict[str, Any]:
    old, old_counts, old_total = count_calls(lambda: legacy_load_amplicon(tree))
    new, new_counts, new_total = count_calls(
        lambda: route_ingest(tree, IngestMode.AMPLICON)
    )
    return {
        "site": "kuma_core/mame/ingest/mode_router.py::_load_amplicon",
        "in_perf_harness": False,
        "input": str(tree),
        "n_records": len(new),
        "identical": old == new,
        "sizes_identical": [r.file_size_kb for r in old] == [r.file_size_kb for r in new],
        "syscalls_before": old_counts,
        "syscalls_after": new_counts,
        "syscalls_before_total": old_total,
        "syscalls_after_total": new_total,
        "timing": interleaved_ab(
            lambda: legacy_load_amplicon(tree),
            lambda: route_ingest(tree, IngestMode.AMPLICON),
            repeat,
        ),
    }


def case_cutadapt_outputs(plate_dir: Path, fill: float, repeat: int) -> dict[str, Any]:
    """Build a 96-well plate at *fill* occupancy and compare both collectors."""
    if plate_dir.exists():
        shutil.rmtree(plate_dir)
    plate_dir.mkdir(parents=True)
    barcodes = {
        f"{row}{col:02d}": "ACGT" for row in "ABCDEFGH" for col in range(1, 13)
    }
    names = list(barcodes)
    n_present = int(len(names) * fill)
    for name in names[:n_present]:
        body = "".join(f">{name}_r{i}\nACGTACGTACGT\n" for i in range(12))
        (plate_dir / f"{name}.fasta").write_text(body, encoding="utf-8")
    (plate_dir / "_unassigned.fasta").write_text(">u\nACGT\n", encoding="utf-8")

    old, old_counts, old_total = count_calls(
        lambda: legacy_collect_cutadapt_outputs(plate_dir, barcodes)
    )
    new, new_counts, new_total = count_calls(
        lambda: _collect_cutadapt_outputs(plate_dir, barcodes)
    )
    return {
        "site": "kuma_core/mame/ingest/demux.py::_collect_cutadapt_outputs",
        "in_perf_harness": False,
        "input": str(plate_dir),
        "plate_fill": fill,
        "wells_present": n_present,
        "identical": old == new,
        "syscalls_before": old_counts,
        "syscalls_after": new_counts,
        "syscalls_before_total": old_total,
        "syscalls_after_total": new_total,
        "timing": interleaved_ab(
            lambda: legacy_collect_cutadapt_outputs(plate_dir, barcodes),
            lambda: _collect_cutadapt_outputs(plate_dir, barcodes),
            repeat,
        ),
    }


def main() -> int:
    workspace = Path(os.environ.get("WORKSPACE_ROOT", str(Path.home() / "_workspace")))
    ngs = Path(
        os.environ.get("NGS_ROOT", str(workspace / "020.admin/projects/060.nanopore_NGS"))
    )
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--run-dir",
        type=Path,
        default=ngs / "mame_step21_test/20260212_2227_X4_FBF10847_e7145f8e",
        help="MinKNOW run folder (its fastq_pass/ drives the _fastq_sorted case)",
    )
    ap.add_argument(
        "--tree",
        type=Path,
        default=None,
        help="Directory of *-consensus.fasta for the amplicon case",
    )
    ap.add_argument(
        "--plate-root",
        type=Path,
        default=None,
        help="Where to build the synthetic 96-well plate. "
        "Default $HOME/.cache/kuma-9p-plate (ext4); pass a share path to measure 9p.",
    )
    ap.add_argument("--repeat", type=int, default=5)
    args = ap.parse_args()

    plate_root = args.plate_root or (Path.home() / ".cache" / "kuma-9p-plate")
    results: list[dict[str, Any]] = []

    fastq_pass = args.run_dir / "fastq_pass"
    if fastq_pass.is_dir():
        results.append(case_fastq_sorted(fastq_pass, args.repeat))
    else:
        print(f"[skip] no fastq_pass under {args.run_dir}", file=sys.stderr)

    if args.tree is not None and args.tree.is_dir():
        results.append(case_load_amplicon(args.tree, args.repeat))
    else:
        print("[skip] --tree not given or missing; amplicon case skipped", file=sys.stderr)

    for fill in (0.02, 1.0):
        results.append(
            case_cutadapt_outputs(plate_root / f"fill{int(fill * 100)}", fill, args.repeat)
        )

    ok = all(r["identical"] for r in results)
    print(json.dumps({"all_identical": ok, "cases": results}, indent=2))
    if not ok:
        print("[FAIL] a case produced a different result", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
