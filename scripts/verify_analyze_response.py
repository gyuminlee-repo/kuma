# ruff: noqa: T201
"""Fingerprint the ``analyze`` JSON-RPC response so handler refactors stay silent.

``perf_step2_harness.py`` hashes the *output tree* and a handful of summary
counters.  It does not look at the response payload that the frontend actually
consumes, so a refactor of ``handle_analyze`` could reorder or drop a key and
still pass it.  The frontend reads the payload positionally in places
(``JSON.stringify`` round-trips, snapshot persistence), so key ORDER is part of
the contract, not only key membership.

This script therefore records, for one real analyze call:

* ``response_sha256``, sha256 over ``json.dumps(response, sort_keys=False)``,
  which changes if any value changes *or* any key moves;
* ``key_order``, the top-level key order, and the key order of the first
  verdict / replicate / plate_verdict object, spelled out so a diff says which
  key moved rather than only that the digest changed;
* ``shape``, element counts, so a truncation is legible at a glance.

Timing is reported as an interleaved A/B when ``--repeat`` > 1: three agents
share this machine, so alternating the runs is the only way a wall delta means
anything.  Identity is what gates the exit code; timing is information.

Usage
-----
    export KURO_MINIMAP2="$REPO_ROOT/python-core/vendor/minimap2/linux-x64/minimap2"

    # record the pre-change fingerprint
    .venv/bin/python scripts/verify_analyze_response.py \
        --demux-dir <consensus tree> --save notes/perf/analyze-response-before.json

    # after the change, compare (exit 1 on any difference)
    .venv/bin/python scripts/verify_analyze_response.py \
        --demux-dir <consensus tree> --compare notes/perf/analyze-response-before.json
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(_REPO / "python-core"))


def _default_ngs_root() -> Path:
    workspace = Path(os.environ.get("WORKSPACE_ROOT", str(Path.home() / "_workspace")))
    return Path(
        os.environ.get("NGS_ROOT", str(workspace / "020.admin/projects/060.nanopore_NGS"))
    )


def _key_order(obj: Any) -> list[str]:
    return list(obj.keys()) if isinstance(obj, dict) else []


def _fingerprint(response: dict) -> dict:
    """Digest + spelled-out key order for the response and its nested records."""
    verdicts = response.get("verdicts") or []
    replicates = response.get("replicates") or []
    first_plate: dict = {}
    if replicates and isinstance(replicates[0], dict):
        plate_verdicts = replicates[0].get("plate_verdicts") or {}
        if plate_verdicts:
            first_plate = next(iter(plate_verdicts.values()))
    payload = json.dumps(response, sort_keys=False, ensure_ascii=False, default=str)
    return {
        "response_sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        "key_order": {
            "response": _key_order(response),
            "verdict": _key_order(verdicts[0] if verdicts else {}),
            "replicate": _key_order(replicates[0] if replicates else {}),
            "plate_verdict": _key_order(first_plate),
            "summary": _key_order(response.get("summary") or {}),
            "distribution_stats": _key_order(response.get("distribution_stats") or {}),
        },
        "shape": {
            "n_verdicts": len(verdicts),
            "n_replicates": len(replicates),
            "n_designed_mutant_ids": len(response.get("designed_mutant_ids") or []),
        },
    }


def _run_once(demux_dir: Path, inputs: Path) -> tuple[dict, float]:
    """Call ``handle_analyze`` on *demux_dir*, returning (response, wall seconds).

    The xlsx output is real work that must stay inside the timing, but its bytes
    are not part of this fingerprint, so it is written to a scratch directory.
    That directory has a FIXED name rather than a random one: the handler echoes
    ``output_path`` back in the response, so a random temp name would make every
    run differ for a reason that has nothing to do with the code under test.
    """
    from sidecar_mame.handlers.analyze import handle_analyze

    out_dir = Path(tempfile.gettempdir()) / "kuma-verify-analyze-response"
    out_dir.mkdir(parents=True, exist_ok=True)
    params = {
        "input_dir": str(demux_dir),
        "reference": str(inputs / "ispS.fasta"),
        "expected": str(inputs / "260526_mame_input_96mutants.xlsx"),
        "output": str(out_dir / "result.xlsx"),
        "mode": "amplicon",
        "ingest_mode": "barcode",
        "cds_start": 0,
        "min_file_size_kb": 1.0,
        "many_cutoff": 5,
    }
    started = time.perf_counter()
    # The handler emits JSON-RPC progress on stdout; keep stdout clean.
    with contextlib.redirect_stdout(sys.stderr):
        response = handle_analyze(params)
    return response, time.perf_counter() - started


def main() -> int:
    ngs = _default_ngs_root()
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument(
        "--demux-dir", type=Path, required=True,
        help="A demux/consensus output tree (the analyze input_dir)",
    )
    ap.add_argument("--inputs-dir", type=Path, default=ngs / "mame_step21_test/inputs")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--save", type=Path, default=None)
    ap.add_argument("--compare", type=Path, default=None)
    args = ap.parse_args()

    for path in (args.demux_dir, args.inputs_dir):
        if not path.exists():
            print(f"ERROR: not found: {path}", file=sys.stderr)
            return 2

    walls: list[float] = []
    fingerprints: list[dict] = []
    for i in range(args.repeat):
        response, wall = _run_once(args.demux_dir, args.inputs_dir)
        walls.append(round(wall, 4))
        fingerprints.append(_fingerprint(response))
        print(f"[run {i + 1}/{args.repeat}] wall={wall:.4f}s", file=sys.stderr)

    unstable = [i for i, fp in enumerate(fingerprints) if fp != fingerprints[0]]
    record = {
        "schema": "kuma-mame-analyze-response/1",
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "demux_dir": str(args.demux_dir),
        **fingerprints[0],
        "timing": {
            "repeat": args.repeat,
            "wall_s_runs": walls,
            "wall_s_median": round(statistics.median(walls), 4),
        },
    }
    print(json.dumps(record, indent=2, ensure_ascii=False))

    rc = 0
    if unstable:
        print(f"[FAIL] fingerprint unstable across repeats: runs {unstable}", file=sys.stderr)
        rc = 1

    if args.save:
        args.save.parent.mkdir(parents=True, exist_ok=True)
        args.save.write_text(
            json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"[saved] {args.save}", file=sys.stderr)

    if args.compare:
        base = json.loads(args.compare.read_text(encoding="utf-8"))
        diffs = [
            f"{key}: baseline={base.get(key)!r} current={record.get(key)!r}"
            for key in ("response_sha256", "key_order", "shape")
            if base.get(key) != record.get(key)
        ]
        bw = base.get("timing", {}).get("wall_s_median")
        if bw:
            cw = record["timing"]["wall_s_median"]
            print(
                f"[info] wall median {bw}s -> {cw}s "
                f"({(cw - bw) / bw * 100.0:+.1f}%, negative is faster)",
                file=sys.stderr,
            )
        if diffs:
            print("[FAIL] response differs from baseline:", file=sys.stderr)
            for diff in diffs:
                print(f"  - {diff}", file=sys.stderr)
            rc = 1
        else:
            print("[OK] response fingerprint matches baseline.", file=sys.stderr)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
