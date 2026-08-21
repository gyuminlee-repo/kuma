#!/usr/bin/env python3
"""Produce real MAME capture data by driving the built sidecar over JSON-RPC.

Everything written to scripts/mame-real-data.json comes back from the sidecar
binary in src-tauri/binaries. No value is hand-written here, so the capture
screens that consume this file show sidecar output rather than fixtures.

The input is the nanopore run the lab sequenced for the IspS campaign:
a MinKNOW folder of 288 barcoded fastq files, the plate order the wells were
picked in, and the plasmid the reads are aligned against. The analyze call
demuxes and scores that run in one round trip, which is why the timeout here
is generous rather than the transport default.

Parameter names mirror `_demuxAndAnalyze` in src/store/mame/slices/inputSlice.ts.
The point of this file is to send what the app sends; a divergence here would
produce screens that no operator can reproduce.

Usage:
    python3 scripts/gen_mame_capture_data.py [--out scripts/mame-real-data.json]
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# The lab run, as recorded in the autosaved workspace at
# ~/Documents/kuma/260731_hmk_test/.autosave/mame.json.
DEFAULT_BASE = Path.home() / "_workspace" / "260730 MAME test"
DEFAULT_RUN_DIR = DEFAULT_BASE / "260729_KHM" / "20260729_1904_X4_FBF91250_f497f4eb"
DEFAULT_EXPECTED = DEFAULT_BASE / "260722_Ep_R2-1_platemap_plate-order.xlsx"
DEFAULT_REFERENCE = DEFAULT_BASE / "pTSN-PtIspS-idi(KanR)_corrected.fa"
DEFAULT_BARCODES = DEFAULT_BASE / "barcodes sequence.xlsx"
DEFAULT_OUTPUT_DIR = DEFAULT_BASE / "260821_MAME_capture_pernb"

# Analyze knobs, same values the autosaved workspace carries.
MODE = "amplicon"
INGEST_MODE = "barcode"
MIN_FILE_SIZE_KB = 50
MANY_CUTOFF = 5
COVERAGE_FRACTION = 0.98
EDIT_DIST_RATIO = 0.25
CHIMERA_SPLIT = True
MAPQ_THRESHOLD = 25
TRIM_FLANK_BP = 30

# A raw-run analyze demuxes 288 fastq files before it scores anything, so the
# app itself sends a long timeout here (MAME_RAWRUN_RPC_TIMEOUT_MS).
ANALYZE_TIMEOUT_S = 7200.0


def sidecar_path() -> Path:
    machine = platform.machine()
    arch = "aarch64" if machine in {"arm64", "aarch64"} else "x86_64"
    system = platform.system()
    if system == "Darwin":
        triple = f"{arch}-apple-darwin"
    elif system == "Linux":
        triple = f"{arch}-unknown-linux-gnu"
    else:
        triple = f"{arch}-pc-windows-msvc.exe"
    return ROOT / "src-tauri" / "binaries" / f"mame-sidecar-{triple}"


class Sidecar:
    """Line-delimited JSON-RPC client over the sidecar stdio pipe.

    Progress notifications carry no `id`, so the read loop skips them and keeps
    reading until the reply that answers the request arrives.
    """

    def __init__(self, binary: Path) -> None:
        self._proc = subprocess.Popen(  # noqa: S603
            [str(binary)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
        self._next_id = 0

    def call(self, method: str, params: dict, timeout_s: float = 900.0) -> dict:
        self._next_id += 1
        request_id = self._next_id
        payload = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        assert self._proc.stdin is not None
        assert self._proc.stdout is not None
        self._proc.stdin.write(json.dumps(payload) + "\n")
        self._proc.stdin.flush()

        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            line = self._proc.stdout.readline()
            if not line:
                raise RuntimeError(f"{method}: sidecar closed the pipe")
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if message.get("id") != request_id:
                continue
            if "error" in message:
                raise RuntimeError(f"{method}: {json.dumps(message['error'], ensure_ascii=False)}")
            return message["result"]
        raise TimeoutError(f"{method}: no response within {timeout_s}s")

    def close(self) -> None:
        try:
            self.call("shutdown", {}, timeout_s=10.0)
        except Exception:  # noqa: BLE001 - shutdown is best effort
            pass
        assert self._proc.stdin is not None
        self._proc.stdin.close()
        try:
            self._proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self._proc.kill()


def log(message: str) -> None:
    sys.stdout.write(f"{message}\n")
    sys.stdout.flush()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN_DIR)
    parser.add_argument("--expected", type=Path, default=DEFAULT_EXPECTED)
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument("--barcodes", type=Path, default=DEFAULT_BARCODES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--out", type=Path, default=ROOT / "scripts" / "mame-real-data.json")
    args = parser.parse_args()

    for label, path in (
        ("run dir", args.run_dir),
        ("expected", args.expected),
        ("reference", args.reference),
        ("barcodes", args.barcodes),
    ):
        if not path.exists():
            sys.stderr.write(f"missing {label}: {path}\n")
            return 1

    binary = sidecar_path()
    if not binary.exists():
        sys.stderr.write(f"sidecar not built: {binary}\nRun: pnpm sidecar:build\n")
        return 1

    args.output_dir.mkdir(parents=True, exist_ok=True)
    workbook = args.output_dir / "260821_pTSN-PtIspS-idi_KanR__corrected_MAME.xlsx"
    demux_dir = args.output_dir / "demux_filtered"

    # Recorded so the capture harness drives the UI with the same paths this
    # run sent the sidecar, rather than carrying its own copy of them.
    bundle: dict[str, object] = {
        "inputs": {
            "run_dir": str(args.run_dir),
            "barcodes": str(args.barcodes),
            "expected": str(args.expected),
            "reference": str(args.reference),
            "output_dir": str(args.output_dir),
        }
    }
    sidecar = Sidecar(binary)
    try:
        bundle["health"] = sidecar.call("health_info", {})
        log("health_info ok")

        # What the operator sees before pressing Run: which wells the plate
        # order claims, and which native barcodes the run actually used.
        bundle["well_layout"] = sidecar.call(
            "mame.build_well_layout",
            {"expected_mutations_xlsx": str(args.expected)},
        )
        log("mame.build_well_layout ok")

        detected = sidecar.call(
            "mame.detect_native_barcodes", {"minknow_run_dir": str(args.run_dir)}
        )
        bundle["native_barcodes"] = detected
        # The selection an operator confirms in NativeBarcodeConfirmDialog, taken
        # from the detection rather than typed here. The RPC wants the MinKNOW
        # directory names (`barcode07`), not the sort form the results carry;
        # see confirmNativeBarcodeSelection in inputSlice.ts.
        #
        # Passing null instead collapses the three replicate plates into a
        # single pool: the run then scores 96 wells and recovers 76 of 95
        # mutants, where the per-barcode run scores 288 and recovers 94.
        used_barcodes = [
            str(nb["name"])
            for nb in (detected.get("native_barcodes") or [])
            if nb.get("is_used")
        ]
        if not used_barcodes:
            raise RuntimeError("detection reported no used native barcode")
        log(f"mame.detect_native_barcodes ok, using {used_barcodes}")

        bundle["variant_source"] = sidecar.call(
            "inspect_variant_source", {"path": str(args.expected)}
        )
        log("inspect_variant_source ok")

        # Both fire from the input step as soon as a path lands: the plate
        # order is checked against the expected list, and the reference is
        # parsed for its CDS candidates.
        bundle["plate_order"] = sidecar.call(
            "check_plate_order", {"path": str(args.expected)}
        )
        log("check_plate_order ok")

        bundle["parse_reference"] = sidecar.call(
            "mame.ingest.parse_reference", {"path": str(args.reference)}
        )
        log("mame.ingest.parse_reference ok")

        bundle["validate_inputs"] = sidecar.call(
            "validate_inputs",
            {
                "input_dir": str(args.run_dir),
                "reference": str(args.reference),
                "expected": str(args.expected),
                "output": str(workbook),
                "custom_barcodes_xlsx": str(args.barcodes),
            },
        )
        log("validate_inputs ok")

        analyze_params = {
            "input_dir": str(args.run_dir),
            "reference": str(args.reference),
            "expected": str(args.expected),
            "output": str(workbook),
            "mode": MODE,
            "ingest_mode": INGEST_MODE,
            "cds_start": 0,
            "cds_end": 0,
            "min_file_size_kb": MIN_FILE_SIZE_KB,
            "many_cutoff": MANY_CUTOFF,
            "well_layout": None,
            "selected_wells": None,
            "custom_barcodes_xlsx": str(args.barcodes),
            "native_barcodes": used_barcodes,
            "coverage_fraction": COVERAGE_FRACTION,
            "edit_dist_ratio": EDIT_DIST_RATIO,
            "chimera_split": CHIMERA_SPLIT,
            "demux_output_dir": str(demux_dir),
            "mapq_threshold": MAPQ_THRESHOLD,
            "trim_flank_bp": TRIM_FLANK_BP,
        }
        log("analyze: demuxing and scoring the run, this takes a while")
        started = time.monotonic()
        bundle["analyze"] = sidecar.call("analyze", analyze_params, timeout_s=ANALYZE_TIMEOUT_S)
        elapsed = time.monotonic() - started
        # How long the run really took. The capture harness replays this delay
        # before handing back the recorded reply, because the app measures the
        # duration client-side and paints it on the review screen. Serving the
        # reply instantly would put "Took 2 s" on a 288-well nanopore run.
        bundle["analyze_seconds"] = round(elapsed, 1)
        log(f"analyze ok in {elapsed:.0f}s")

        # Downstream RPCs read the analyze artefacts the sidecar just cached.
        bundle["plate"] = sidecar.call("get_plate_data", {})
        log("get_plate_data ok")

        bundle["run_health"] = sidecar.call("get_run_health", {})
        log("get_run_health ok")

        bundle["janus_dry_run"] = sidecar.call("export_janus_mapping_dry_run", {})
        log("export_janus_mapping_dry_run ok")

        bundle["kuma_meta"] = sidecar.call("read_kuma_meta", {"path": str(workbook)})
        log("read_kuma_meta ok")
    finally:
        sidecar.close()

    args.out.write_text(json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8")
    log(f"wrote {args.out} ({args.out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
