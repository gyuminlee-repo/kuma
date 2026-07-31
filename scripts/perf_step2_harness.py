# ruff: noqa: T201
"""MAME step 2 performance + output-identity harness.

Runs the real step 2 pipeline (native barcode detection, combinatorial demux
with consensus, then analyze) against a reference MinKNOW run folder, and emits
a JSON fingerprint carrying two things:

* identity, counters plus a deterministic sha256 over the whole output tree, so
  an optimization can be proven byte-identical to the baseline;
* timing, e2e wall plus the per-phase seconds collected through
  ``KUMA_MAME_TIMING_JSON`` (see ``kuma_core/mame/perf.py``).

Only the identity block gates ``--compare-baseline``; wall differences are
reported as information.

Usage
-----
    export KURO_MINIMAP2="$REPO_ROOT/python-core/vendor/minimap2/linux-x64/minimap2"

    # ext4 output (default), 3 repeats, save the baseline
    .venv/bin/python scripts/perf_step2_harness.py --repeat 3 \
        --save-baseline notes/perf/baseline-<sha>-ext4.json

    # Windows share (9p) output
    .venv/bin/python scripts/perf_step2_harness.py --repeat 3 \
        --out-root "$WORKSPACE_ROOT/.kuma-perf" \
        --save-baseline notes/perf/baseline-<sha>-share.json

    # regression check against a saved fingerprint (exit 1 on identity drift)
    .venv/bin/python scripts/perf_step2_harness.py --repeat 1 \
        --compare-baseline notes/perf/baseline-<sha>-ext4.json

Assumptions (stated rather than hidden)
---------------------------------------
* The reference workload is the mame_step21_test folder under ``NGS_ROOT``,
  the same inputs the headless ``run_step21.py`` runner uses.
* The verdict counts come from step 3 (analyze); step 2 alone cannot produce
  them, and the reference fingerprint for this branch includes them, so analyze
  is run and timed separately from demux.
* ``result.xlsx`` is excluded from the tree hash because a zip container embeds
  per-entry timestamps and is therefore not content-deterministic. Every
  exclusion is listed in the fingerprint.
* The timing JSONL is written outside the hashed output tree.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import logging
import os
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

log = logging.getLogger("perf_step2_harness")

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent

# Files never folded into the tree hash, with the reason recorded in the
# fingerprint so an exclusion is never silent.
_HASH_EXCLUSIONS: dict[str, str] = {
    "result.xlsx": "xlsx zip container embeds per-entry mtime, not content-deterministic",
}

# Env knobs that change worker/thread fan-out and therefore both wall time and
# (potentially) output. Recorded verbatim in every fingerprint.
_TUNING_ENV = (
    "KUMA_MAME_NB_PARALLEL",
    "KUMA_MAME_NB_WORKERS",
    "KUMA_MAME_PERREAD_THRESHOLD",
    "KUMA_MAME_PERREAD_WORKERS",
    "KUMA_MAME_CONSENSUS_WORKERS",
    "KUMA_MAME_READ_CHUNK",
    "KUMA_MAME_FASTQ_PREFETCH",
    "KUMA_MAME_KEEP_WELL_READS",
)

# Identity keys; any difference here fails --compare-baseline.
_IDENTITY_KEYS = (
    "assigned_reads",
    "total_reads",
    "wells_with_reads",
    "verdicts",
    "tree_sha256",
    "file_count",
    "hash_excluded",
)


def _default_ngs_root() -> Path:
    workspace = Path(os.environ.get("WORKSPACE_ROOT", str(Path.home() / "_workspace")))
    return Path(
        os.environ.get("NGS_ROOT", str(workspace / "020.admin/projects/060.nanopore_NGS"))
    )


def _resolve_minimap2(explicit: str | None) -> str:
    """Return a usable minimap2 path, or exit with an actionable message."""
    candidates = [
        explicit,
        os.environ.get("KURO_MINIMAP2") or None,
        str(_REPO / "python-core/vendor/minimap2/linux-x64/minimap2"),
    ]
    # A git worktree does not carry the (gitignored) vendor binary, so fall back
    # to the main checkout that owns this worktree.
    gitlink = _REPO / ".git"
    if gitlink.is_file():
        try:
            gitdir = gitlink.read_text(encoding="utf-8").split(":", 1)[1].strip()
            for parent in Path(gitdir).resolve().parents:
                if (parent / "python-core").is_dir():
                    candidates.append(
                        str(parent / "python-core/vendor/minimap2/linux-x64/minimap2")
                    )
                    break
        except (OSError, IndexError) as exc:
            log.warning("could not resolve main checkout from %s: %s", gitlink, exc)
    for cand in candidates:
        if cand and Path(cand).exists():
            return str(Path(cand).resolve())
    print(
        "ERROR: no minimap2 binary found. Set KURO_MINIMAP2 or pass --minimap2.",
        file=sys.stderr,
    )
    sys.exit(2)


def _sha256_tree(root: Path) -> tuple[str, int, list[str]]:
    """Hash every file under *root* in sorted relative-path order.

    Returns ``(hexdigest, file_count, excluded_relpaths)``. Both the relative
    path and the content go into the digest, so a renamed or moved file changes
    it. Excluded files are counted in ``file_count`` but not hashed.
    """
    h = hashlib.sha256()
    files = sorted(p for p in root.rglob("*") if p.is_file())
    excluded: list[str] = []
    for path in files:
        rel = path.relative_to(root).as_posix()
        if path.name in _HASH_EXCLUSIONS:
            excluded.append(rel)
            continue
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        with path.open("rb") as fh:
            for block in iter(lambda: fh.read(1 << 20), b""):
                h.update(block)
        h.update(b"\0")
    return h.hexdigest(), len(files), excluded


def _read_timing(jsonl: Path) -> dict[str, Any]:
    """Aggregate the phase JSONL emitted by ``kuma_core.mame.perf``.

    Phase seconds are summed across every record (the parent plus each
    ProcessPool worker, which each emit their own session). Scope walls are kept
    separate since worker walls overlap the parent wall by construction.
    """
    if not jsonl.exists():
        return {"phases_s": {}, "scopes": [], "records": 0, "malformed_records": 0}
    phases: dict[str, float] = {}
    scopes: list[dict[str, Any]] = []
    n = 0
    bad = 0
    for line in jsonl.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rec = None
        try:
            rec = json.loads(line)
        except ValueError as exc:
            log.warning("malformed timing record in %s: %s", jsonl, exc)
            bad += 1
        if rec is None:
            continue
        n += 1
        for key, val in (rec.get("phases_s") or {}).items():
            phases[key] = phases.get(key, 0.0) + float(val)
        scopes.append(
            {
                "scope": rec.get("scope"),
                "pid": rec.get("pid"),
                "wall_s": round(float(rec.get("wall_s", 0.0)), 4),
                **{k: rec[k] for k in ("workers", "barcodes", "parallel") if k in rec},
            }
        )
    return {
        "phases_s": {
            k: round(v, 4) for k, v in sorted(phases.items(), key=lambda kv: -kv[1])
        },
        "scopes": scopes,
        "records": n,
        "malformed_records": bad,
    }


def _one_run(args: argparse.Namespace, out_dir: Path, timing_jsonl: Path) -> dict[str, Any]:
    """Execute detect + demux + analyze once into a clean *out_dir*."""
    from sidecar_mame.handlers.analyze import handle_analyze
    from sidecar_mame.handlers.combinatorial_demux import handle_run_combinatorial_demux
    from sidecar_mame.handlers.detect_native_barcodes import (
        handle_detect_native_barcodes,
    )

    inputs = args.inputs_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    os.environ["KUMA_MAME_TIMING_JSON"] = str(timing_jsonl)

    t_all = time.perf_counter()

    t0 = time.perf_counter()
    det = handle_detect_native_barcodes({"minknow_run_dir": str(args.run_dir)})
    t_detect = time.perf_counter() - t0

    nbs = det.get("native_barcodes", []) or []
    native: list[str] | None
    if det.get("total_count", 0) > 1:
        native = [b["name"] for b in nbs if isinstance(b, dict) and b.get("is_used")]
        if not native:
            native = [b["name"] for b in nbs if isinstance(b, dict)]
    else:
        native = None

    t0 = time.perf_counter()
    demux = handle_run_combinatorial_demux(
        {
            "minknow_run_dir": str(args.run_dir),
            "custom_barcodes_xlsx": str(inputs / "barcodes sequence.xlsx"),
            "reference_fasta": str(inputs / "ispS.fasta"),
            "output_dir": str(out_dir / "demux"),
            "sample_map_xlsx": None,
            "kuro_xlsx": None,
            "mapq_threshold": 25,
            "coverage_fraction": 0.98,
            "edit_dist_ratio": 0.25,
            "chimera_split": True,
            "trim_flank_bp": 30,
            "native_barcodes": native,
        }
    )
    t_demux = time.perf_counter() - t0

    t0 = time.perf_counter()
    res = handle_analyze(
        {
            "input_dir": demux["output_dir"],
            "reference": str(inputs / "ispS.fasta"),
            "expected": str(inputs / "260526_mame_input_96mutants.xlsx"),
            "sample_map_xlsx": str(inputs / "sample_map.xlsx"),
            "output": str(out_dir / "result.xlsx"),
            "mode": "amplicon",
            "ingest_mode": "barcode",
            "cds_start": 0,
            # Shallow subset, mirrors the reference runner. Production default 50.0.
            "min_file_size_kb": 1.0,
            "many_cutoff": 5,
        }
    )
    t_analyze = time.perf_counter() - t0

    wall = time.perf_counter() - t_all

    stats = demux.get("stats", {}) or {}
    summary = res.get("summary", {}) or {}
    tree_hash, n_files, excluded = _sha256_tree(out_dir)

    return {
        "identity": {
            "assigned_reads": int(demux.get("assigned_reads") or 0),
            "total_reads": int(stats.get("total_reads") or 0),
            "wells_with_reads": int(demux.get("wells_with_reads") or 0),
            "verdicts": {
                "PASS": int(summary.get("pass_count") or 0),
                "AMBIGUOUS": int(summary.get("ambiguous_count") or 0),
                "MIXED": int(summary.get("mixed_count") or 0),
                "FAIL": int(summary.get("fail_count") or 0),
            },
            "tree_sha256": tree_hash,
            "file_count": n_files,
            "hash_excluded": sorted(excluded),
        },
        "extra": {
            "native_barcodes": native,
            "demux_stats": {k: int(v) for k, v in stats.items()},
            "verdict_total": int(summary.get("total") or 0),
        },
        "timing": {
            "wall_s": round(wall, 4),
            "detect_s": round(t_detect, 4),
            "demux_s": round(t_demux, 4),
            "analyze_s": round(t_analyze, 4),
            **_read_timing(timing_jsonl),
        },
    }


def _apply_tuning_env(args: argparse.Namespace) -> None:
    mapping = {
        "KUMA_MAME_NB_PARALLEL": args.nb_parallel,
        "KUMA_MAME_NB_WORKERS": args.nb_workers,
        "KUMA_MAME_PERREAD_THRESHOLD": args.perread_threshold,
        "KUMA_MAME_PERREAD_WORKERS": args.perread_workers,
        "KUMA_MAME_CONSENSUS_WORKERS": args.consensus_workers,
        "KUMA_MAME_READ_CHUNK": args.read_chunk,
    }
    for key, val in mapping.items():
        if val is not None:
            os.environ[key] = str(val)


def _compare(baseline: dict, current: dict) -> list[str]:
    """Return the list of identity differences (empty means identical)."""
    diffs: list[str] = []
    b = baseline.get("identity", {})
    c = current.get("identity", {})
    for key in _IDENTITY_KEYS:
        bv, cv = b.get(key), c.get(key)
        if bv != cv:
            diffs.append(f"{key}: baseline={bv!r} current={cv!r}")
    return diffs


def _fs_type(path: Path) -> str:
    """Filesystem type of *path* (ext4 vs 9p is the whole point of --out-root)."""
    try:
        lines = subprocess.run(
            ["df", "-T", str(path)], capture_output=True, text=True, timeout=10
        ).stdout.strip().splitlines()
        return lines[-1].split()[1] if lines else "unknown"
    except (OSError, subprocess.SubprocessError, IndexError) as exc:
        log.warning("df -T %s failed: %s", path, exc)
        return "unknown"


def _git_head() -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(_REPO), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=10,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("git rev-parse failed: %s", exc)
        return "unknown"


def main() -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ngs = _default_ngs_root()
    ap.add_argument(
        "--run-dir", type=Path,
        default=ngs / "mame_step21_test/20260212_2227_X4_FBF10847_e7145f8e",
        help="MinKNOW run folder (contains fastq_pass/)",
    )
    ap.add_argument(
        "--inputs-dir", type=Path, default=ngs / "mame_step21_test/inputs",
        help="Folder with barcodes xlsx, reference fasta, expected xlsx, sample map",
    )
    ap.add_argument(
        "--out-root", type=Path, default=None,
        help="Where run output dirs are created. Default $HOME/.cache/kuma-perf (ext4). "
             "Point at a path on the Windows share to measure 9p instead.",
    )
    ap.add_argument("--repeat", type=int, default=3, help="Number of runs (default 3)")
    ap.add_argument("--keep", action="store_true", help="Keep output dirs instead of deleting them")
    ap.add_argument("--save-baseline", type=Path, default=None)
    ap.add_argument("--compare-baseline", type=Path, default=None)
    ap.add_argument("--minimap2", default=None)
    ap.add_argument("--verbose", action="store_true", help="INFO logging, includes [perf] blocks")
    ap.add_argument("--nb-parallel", default=None, help="KUMA_MAME_NB_PARALLEL, 0 disables per-NB pool")
    ap.add_argument("--nb-workers", default=None, help="KUMA_MAME_NB_WORKERS")
    ap.add_argument("--perread-threshold", default=None, help="KUMA_MAME_PERREAD_THRESHOLD")
    ap.add_argument("--perread-workers", default=None, help="KUMA_MAME_PERREAD_WORKERS")
    ap.add_argument("--consensus-workers", default=None, help="KUMA_MAME_CONSENSUS_WORKERS")
    ap.add_argument("--read-chunk", default=None, help="KUMA_MAME_READ_CHUNK")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s %(message)s",
        stream=sys.stderr,
    )

    for path in (args.run_dir, args.inputs_dir):
        if not path.exists():
            print(f"ERROR: not found: {path}", file=sys.stderr)
            return 2

    os.environ["KURO_MINIMAP2"] = _resolve_minimap2(args.minimap2)
    _apply_tuning_env(args)

    sys.path.insert(0, str(_REPO / "python-core"))
    sys.path.insert(0, str(_REPO))

    out_root = args.out_root or (Path.home() / ".cache" / "kuma-perf")
    out_root.mkdir(parents=True, exist_ok=True)
    # The timing JSONL never lives inside the hashed tree.
    timing_root = Path.home() / ".cache" / "kuma-perf-timing"
    timing_root.mkdir(parents=True, exist_ok=True)

    stamp = time.strftime("%Y%m%d-%H%M%S")
    runs: list[dict[str, Any]] = []
    for i in range(args.repeat):
        out_dir = out_root / f"perf-{stamp}-{i}"
        # A leftover tree would be picked up by the resume markers and skip real
        # work, which would silently corrupt the measurement.
        if out_dir.exists():
            shutil.rmtree(out_dir)
        timing_jsonl = timing_root / f"perf-{stamp}-{i}.jsonl"
        timing_jsonl.unlink(missing_ok=True)
        print(f"[run {i + 1}/{args.repeat}] out={out_dir}", file=sys.stderr)
        try:
            # The sidecar handlers emit JSON-RPC progress on stdout; keep stdout
            # clean so the fingerprint is the only thing this script prints there.
            with contextlib.redirect_stdout(sys.stderr):
                rec = _one_run(args, out_dir, timing_jsonl)
        finally:
            if not args.keep and out_dir.exists():
                shutil.rmtree(out_dir, ignore_errors=True)
        rec["run_index"] = i
        runs.append(rec)
        print(
            f"[run {i + 1}/{args.repeat}] wall={rec['timing']['wall_s']}s "
            f"demux={rec['timing']['demux_s']}s analyze={rec['timing']['analyze_s']}s "
            f"sha={rec['identity']['tree_sha256'][:12]}",
            file=sys.stderr,
        )

    identities = [r["identity"] for r in runs]
    unstable = [
        k for k in _IDENTITY_KEYS if any(idn[k] != identities[0][k] for idn in identities)
    ]

    walls = [r["timing"]["wall_s"] for r in runs]
    demuxes = [r["timing"]["demux_s"] for r in runs]
    analyzes = [r["timing"]["analyze_s"] for r in runs]

    phase_keys: set[str] = set()
    for r in runs:
        phase_keys |= set(r["timing"]["phases_s"])
    phases_median = {
        k: round(statistics.median([r["timing"]["phases_s"].get(k, 0.0) for r in runs]), 4)
        for k in phase_keys
    }
    phases_median = dict(sorted(phases_median.items(), key=lambda kv: -kv[1]))

    fingerprint = {
        "schema": "kuma-mame-step2-perf/1",
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "git_head": _git_head(),
        "identity": identities[0],
        "identity_stable_across_repeats": not unstable,
        "identity_unstable_keys": unstable,
        "extra": runs[0]["extra"],
        "environment": {
            "out_root": str(out_root),
            "out_root_fs": _fs_type(out_root),
            "run_dir": str(args.run_dir),
            "inputs_dir": str(args.inputs_dir),
            "minimap2": os.environ["KURO_MINIMAP2"],
            "python": sys.version.split()[0],
            "cpu_count": os.cpu_count(),
            "tuning_env": {k: os.environ.get(k) for k in _TUNING_ENV},
        },
        "timing": {
            "repeat": args.repeat,
            "wall_s_runs": walls,
            "wall_s_median": round(statistics.median(walls), 4),
            "demux_s_runs": demuxes,
            "demux_s_median": round(statistics.median(demuxes), 4),
            "analyze_s_runs": analyzes,
            "analyze_s_median": round(statistics.median(analyzes), 4),
            "phases_s_median": phases_median,
            "scopes_run0": runs[0]["timing"]["scopes"],
        },
        "hash_exclusions": _HASH_EXCLUSIONS,
    }

    print(json.dumps(fingerprint, indent=2, ensure_ascii=False))

    if args.save_baseline:
        args.save_baseline.parent.mkdir(parents=True, exist_ok=True)
        args.save_baseline.write_text(
            json.dumps(fingerprint, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"[saved] {args.save_baseline}", file=sys.stderr)

    rc = 0
    if unstable:
        print(f"[FAIL] identity is not stable across repeats: {unstable}", file=sys.stderr)
        rc = 1

    if args.compare_baseline:
        base = json.loads(args.compare_baseline.read_text(encoding="utf-8"))
        diffs = _compare(base, fingerprint)
        bw = base.get("timing", {}).get("wall_s_median")
        cw = fingerprint["timing"]["wall_s_median"]
        if bw:
            delta = (cw - bw) / bw * 100.0
            print(
                f"[info] wall median {bw}s -> {cw}s ({delta:+.1f}%, negative is faster)",
                file=sys.stderr,
            )
        if diffs:
            print("[FAIL] identity differs from baseline:", file=sys.stderr)
            for d in diffs:
                print(f"  - {d}", file=sys.stderr)
            rc = 1
        else:
            print("[OK] identity matches baseline.", file=sys.stderr)
    return rc


if __name__ == "__main__":
    sys.exit(main())
