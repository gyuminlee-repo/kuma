#!/usr/bin/env python3
"""Produce real MAME capture data by driving the built sidecar over JSON-RPC.

Everything written to scripts/mame-real-data.json comes back from the sidecar
binary in src-tauri/binaries. No value is hand-written here, so the capture
screens that consume this file show sidecar output rather than fixtures.

The inputs are a user-supplied MinKNOW run folder, the plate order the wells
were picked in, and the reference the reads are aligned against. They are not
shipped with the repository. The analyze call
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
import os
import platform
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[1]

# The run inputs are not shipped with the repository. MAME_CAPTURE_BASE names a
# folder holding them under the generic names below; each can also be passed
# as an argument.
DEFAULT_BASE = Path(os.environ.get("MAME_CAPTURE_BASE", str(Path.home() / "mame_capture_input")))
DEFAULT_RUN_DIR = DEFAULT_BASE / "minknow_run"
DEFAULT_EXPECTED = DEFAULT_BASE / "plate_order.xlsx"
DEFAULT_REFERENCE = DEFAULT_BASE / "reference.fa"
DEFAULT_BARCODES = DEFAULT_BASE / "barcodes.xlsx"
DEFAULT_OUTPUT_DIR = DEFAULT_BASE / "capture_output"

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

# A raw-run analyze demultiplexes the supplied FASTQ files before scoring, so the
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


sys.path.insert(0, str(ROOT / "python-core"))
from scripts.capture_sidecar import Sidecar  # noqa: E402

def log(message: str) -> None:
    sys.stdout.write(f"{message}\n")
    sys.stdout.flush()


SAMPLES = ROOT / "src-tauri" / "samples" / "mame"


def record_gc_row_preview(call: Callable[[str, dict[str, object]], object], work_dir: Path) -> dict[str, object]:
    """Record the step 4.1 row review over the shipped synthetic sample files.

    The raw round-1 report sample holds only WT and well rows, so a copy with a
    BLANK block and a numeric calibration block appended is reviewed instead:
    the browser stub then shows used, wt and set_aside rows. A second call
    unticks every WT row and records the build's refusal for that selection,
    which the stub returns when the screen sends the same selection.
    """
    import openpyxl

    report = work_dir / "gc_row_preview_report.xlsx"
    wb = openpyxl.load_workbook(SAMPLES / "11_mame_gc_fid_round1_raw.xlsx")
    ws = wb.active
    assert ws is not None
    for name, area in (("BLANK", 3), ("1", 250)):
        for row in (["Signal:", "FID1B"], ["Area", "Sample Name"], [area, name], ["Sum", area], []):
            ws.append(row)
    wb.save(report)
    params: dict[str, object] = {
        "round1_report_xlsx": str(report),
        "layout_xlsx": str(SAMPLES / "06_mame_plate_layout.xlsx"),
        "verdict_xlsx": str(SAMPLES / "13_mame_verdict.xlsx"),
    }
    preview = call("mame.activity.preview_gc_rows", params)
    assert isinstance(preview, dict)
    rows = cast(list[dict[str, object]], preview["rows"])
    wt = [
        {key: row[key] for key in ("source", "row_index", "block_index", "sample_name", "area")}
        for row in rows
        if row["status"] == "wt"
    ]
    unticked = call("mame.activity.preview_gc_rows", {**params, "excluded_rows": wt})
    assert isinstance(unticked, dict)
    return {"preview": preview, "all_wt_unticked_refusal": unticked["selection_refusal"]}


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
    workbook = args.output_dir / "capture_MAME.xlsx"
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
        # Passing null instead pools replicate plates. Preserve the detected
        # barcode selection so each replicate is scored separately.
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
        # reply instantly would show a duration that does not match the capture.
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

        # Public guide input, recorded rather than invented in the browser stub.
        bundle["measurement_detection"] = sidecar.call(
            "mame.activity.detect_measurement_source",
            {"measurement_path": str(ROOT / "src-tauri" / "samples" / "mame"
                                     / "15_mame_activity_variant.csv")},
        )
        log("mame.activity.detect_measurement_source ok")

        bundle["gc_row_preview"] = record_gc_row_preview(sidecar.call, args.output_dir)
        log("mame.activity.preview_gc_rows ok")
    finally:
        sidecar.close()

    args.out.write_text(json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8")
    log(f"wrote {args.out} ({args.out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
