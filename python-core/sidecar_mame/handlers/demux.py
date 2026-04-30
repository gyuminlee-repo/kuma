"""``demux_and_filter`` JSON-RPC handler.

Runs A1 (custom barcode demux) and A3 (per-read quality filter) on a
MinKNOW native-barcode directory.  Returns demux + filter statistics and
the path to the output directory containing per-well FASTA files.

The frontend should then set ``input_dir`` to the returned ``output_dir``
and call the existing ``analyze`` RPC to continue the pipeline.

RPC name: ``demux_and_filter``
Method is registered in ``dispatcher.py`` as an async method (heavy I/O).

Parameter schema
----------------
``fastq_dir``        (str, required)   — path to fastq_pass/barcodeN/ directory
``custom_barcodes``  (dict, required)  — {well_name: barcode_seq} mapping
``output_dir``       (str, required)   — destination directory for per-well FASTA
``error_tolerance``  (float, optional) — mismatch rate [0.0, 0.5], default 0.1
``use_cutadapt``     (bool, optional)  — prefer cutadapt if on PATH, default True
``sequencing_summary`` (str, optional) — path to sequencing_summary_*.txt (A3)
``min_qscore``       (float, optional) — Phred Q threshold, default 8.0
``length_min``       (int, optional)   — min read length, default 800
``length_max``       (int, optional)   — max read length, default 3000
``min_barcode_score`` (float, optional)— MinKNOW barcode_score threshold, default 60.0
``nb_dirs``          (list[str], optional)  — if set, run demux on each listed
                     subdirectory of ``fastq_dir`` and merge results.

Response schema
---------------
``output_dir``           (str)  — directory containing per-well FASTA files
``n_input_reads``        (int)
``n_assigned``           (int)
``n_unassigned``         (int)
``per_well_counts``      (dict[str, int])
``filter_stats``         (dict | null)  — QualityFilterResult as dict, or null
                         if no FASTQ-level filtering was performed
``backend``              (str)  — "cutadapt" | "python"
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from sidecar_mame.core import (
    _progress,
    _validate_dirpath,
)


# ---------------------------------------------------------------------------
# Parameter helpers
# ---------------------------------------------------------------------------


def _coerce_barcodes(raw: Any) -> dict[str, str]:
    """Validate and normalise the custom_barcodes parameter."""
    if not isinstance(raw, dict):
        raise ValueError("custom_barcodes must be a JSON object (dict)")
    result: dict[str, str] = {}
    for k, v in raw.items():
        if not isinstance(k, str) or not isinstance(v, str):
            raise ValueError(
                f"custom_barcodes keys and values must be strings, got {k!r}: {v!r}"
            )
        result[str(k)] = str(v).strip().upper()
    return result


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


def handle_demux_and_filter(params: dict) -> dict:
    """Run demux (A1) + quality filter (A3) on a native-barcode FASTQ directory.

    Heavy I/O — registered as an async method in dispatcher.py.
    """
    from kuma_core.mame.ingest.demux import DemuxResult, demux_native_barcode
    from kuma_core.mame.ingest.quality_filter import QualityFilterParams

    # ── Mandatory params ─────────────────────────────────────────────────
    fastq_dir = _validate_dirpath(params.get("fastq_dir"))
    output_dir = Path(str(params.get("output_dir", ""))).resolve()
    if not output_dir.parent.exists():
        raise FileNotFoundError(
            f"Parent of output_dir does not exist: {output_dir.parent}"
        )
    if ".." in output_dir.parts:
        raise ValueError("Path traversal not allowed in output_dir")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Accept either a pre-built dict ("custom_barcodes") or a file path
    # ("custom_barcodes_path") that is parsed on the sidecar side.
    raw_barcodes = params.get("custom_barcodes")
    barcodes_path_raw = params.get("custom_barcodes_path")

    if raw_barcodes is not None:
        custom_barcodes = _coerce_barcodes(raw_barcodes)
    elif barcodes_path_raw:
        from kuma_core.mame.ingest.demux import parse_custom_barcodes as _parse_bc

        bc_path = Path(str(barcodes_path_raw)).resolve()
        if ".." in bc_path.parts:
            raise ValueError("Path traversal not allowed in custom_barcodes_path")
        if not bc_path.exists():
            raise FileNotFoundError(
                f"custom_barcodes_path not found: {bc_path}"
            )
        custom_barcodes = _parse_bc(bc_path)
        if not custom_barcodes:
            raise ValueError(
                f"No valid barcodes parsed from {bc_path}. "
                "Expected xlsx (Sheet1 col L) or csv (name,sequence columns)."
            )
    else:
        raise ValueError(
            "Either 'custom_barcodes' (dict) or 'custom_barcodes_path' (file path) is required"
        )

    # ── Optional demux params ────────────────────────────────────────────
    error_tolerance = float(params.get("error_tolerance", 0.1))
    use_cutadapt = bool(params.get("use_cutadapt", True))

    # ── Optional quality filter params ───────────────────────────────────
    seq_summary_raw = params.get("sequencing_summary")
    sequencing_summary: Path | None = None
    if seq_summary_raw:
        sequencing_summary = Path(str(seq_summary_raw)).resolve()
        if not sequencing_summary.exists():
            raise FileNotFoundError(
                f"sequencing_summary not found: {sequencing_summary}"
            )

    qf_params = QualityFilterParams(
        min_qscore=float(params.get("min_qscore", 8.0)),
        length_min=int(params.get("length_min", 800)),
        length_max=int(params.get("length_max", 3000)),
        min_barcode_score=float(params.get("min_barcode_score", 60.0)),
    )

    # ── Optional multi-NB mode ───────────────────────────────────────────
    nb_dirs_raw: list[str] | None = params.get("nb_dirs")

    # ── Backend detection ────────────────────────────────────────────────
    backend = "cutadapt" if (use_cutadapt and shutil.which("cutadapt")) else "python"

    _progress(5, "Starting demux...")

    # ── Demux ─────────────────────────────────────────────────────────────
    if nb_dirs_raw:
        # Multi-native-barcode mode: merge results from multiple subdirectories.
        merged_input = 0
        merged_assigned = 0
        merged_unassigned = 0
        merged_per_well: dict[str, int] = {}

        total_nb = len(nb_dirs_raw)
        for idx, nb_dir_str in enumerate(nb_dirs_raw):
            nb_dir = Path(nb_dir_str).resolve()
            if not nb_dir.is_dir():
                raise FileNotFoundError(f"nb_dir does not exist: {nb_dir}")
            nb_out = output_dir / nb_dir.name
            nb_out.mkdir(parents=True, exist_ok=True)
            pct = 5 + int(60 * idx / total_nb)
            _progress(pct, f"Demuxing {nb_dir.name}...")
            partial = demux_native_barcode(
                fastq_dir=nb_dir,
                custom_barcodes=custom_barcodes,
                output_dir=nb_out,
                error_tolerance=error_tolerance,
                use_cutadapt=use_cutadapt,
            )
            merged_input += partial.n_input_reads
            merged_assigned += partial.n_assigned
            merged_unassigned += partial.n_unassigned
            for well, cnt in partial.per_well_counts.items():
                merged_per_well[well] = merged_per_well.get(well, 0) + cnt

        demux_result = DemuxResult(
            output_dir=output_dir,
            n_input_reads=merged_input,
            n_assigned=merged_assigned,
            n_unassigned=merged_unassigned,
            per_well_counts=merged_per_well,
        )
    else:
        # Single-NB mode: demux into output_dir/<fastq_dir.name>/ so that
        # load_barcode_directory(output_dir) sees the subfolder as native_barcode
        # and the per-well FASTA files inside it.
        # demux_native_barcode returns DemuxResult.output_dir = single_nb_out,
        # but we expose the parent output_dir to the frontend so that
        # analyze(ingest_mode="barcode") via load_barcode_directory(output_dir)
        # correctly walks <nb_subdir>/<well>.fasta.
        _progress(10, "Demuxing reads...")
        single_nb_out = output_dir / fastq_dir.name
        single_nb_out.mkdir(parents=True, exist_ok=True)
        inner = demux_native_barcode(
            fastq_dir=fastq_dir,
            custom_barcodes=custom_barcodes,
            output_dir=single_nb_out,
            error_tolerance=error_tolerance,
            use_cutadapt=use_cutadapt,
        )
        # Return parent output_dir (not single_nb_out) so analyze receives the
        # correct root that load_barcode_directory expects.
        demux_result = DemuxResult(
            output_dir=output_dir,
            n_input_reads=inner.n_input_reads,
            n_assigned=inner.n_assigned,
            n_unassigned=inner.n_unassigned,
            per_well_counts=inner.per_well_counts,
        )

    _progress(65, "Applying quality filter...")

    # ── Quality filter (A3) — build fail-set then strip per-well FASTA ───
    #
    # Strategy: parse sequencing_summary to identify read_ids that fail any
    # threshold, then iterate every per-well FASTA produced by demux and
    # rewrite it without the failing records.  This avoids re-running demux
    # and is O(n) in total reads.
    #
    # When sequencing_summary is absent we compute Q-score from the FASTQ
    # quality strings directly (first FASTQ only for stats; per-well FASTs
    # have already lost quality strings so we skip in-place filtering).
    filter_stats_dict: dict | None = None

    if sequencing_summary is not None:
        from kuma_core.mame.ingest.quality_filter import _parse_sequencing_summary

        # Build fail set from sequencing_summary.
        summary_meta = _parse_sequencing_summary(sequencing_summary)
        fail_read_ids: set[str] = set()
        n_qf_input = 0
        n_qf_failed_qscore = 0
        n_qf_failed_length = 0
        n_qf_failed_barcode = 0

        for read_id, meta in summary_meta.items():
            n_qf_input += 1
            failed = False

            bscore = meta.get("barcode_score")
            if (
                bscore is not None
                and qf_params.min_barcode_score > 0
                and float(bscore) < qf_params.min_barcode_score
            ):
                n_qf_failed_barcode += 1
                fail_read_ids.add(read_id)
                failed = True

            if not failed:
                length = meta.get("length")
                if length is not None:
                    length_i = int(length)
                    if length_i < qf_params.length_min or length_i > qf_params.length_max:
                        n_qf_failed_length += 1
                        fail_read_ids.add(read_id)
                        failed = True

            if not failed:
                qscore = meta.get("qscore")
                if qscore is not None and float(qscore) < qf_params.min_qscore:
                    n_qf_failed_qscore += 1
                    fail_read_ids.add(read_id)

        # Apply fail set to all per-well FASTA files under output_dir.
        n_removed = 0
        for fasta_file in sorted(output_dir.rglob("*.fasta")):
            if fasta_file.name.startswith("_"):
                continue  # skip _unassigned.fasta
            lines = fasta_file.read_text(encoding="utf-8").splitlines(keepends=True)
            filtered_lines: list[str] = []
            skip_next = False
            for line in lines:
                if line.startswith(">"):
                    rid = line[1:].split()[0].rstrip("\r\n")
                    if rid in fail_read_ids:
                        skip_next = True
                        n_removed += 1
                        continue
                    skip_next = False
                    filtered_lines.append(line)
                else:
                    if not skip_next:
                        filtered_lines.append(line)
            fasta_file.write_text("".join(filtered_lines), encoding="utf-8")

        n_qf_passed = n_qf_input - len(fail_read_ids)
        filter_stats_dict = {
            "n_input": n_qf_input,
            "n_passed": max(0, n_qf_passed),
            "n_failed_qscore": n_qf_failed_qscore,
            "n_failed_length": n_qf_failed_length,
            "n_failed_barcode": n_qf_failed_barcode,
        }

        # Recompute per_well_counts after filtering; remove ghost empty files.
        updated_per_well: dict[str, int] = {}
        for fasta_file in sorted(output_dir.rglob("*.fasta")):
            if fasta_file.name.startswith("_"):
                continue
            count = sum(
                1 for ln in fasta_file.read_text(encoding="utf-8").splitlines()
                if ln.startswith(">")
            )
            if count:
                # Use stem relative to output_dir as well name.
                well_name = fasta_file.stem
                updated_per_well[well_name] = updated_per_well.get(well_name, 0) + count
            else:
                # Remove empty FASTA so analyze does not see ghost wells.
                try:
                    fasta_file.unlink()
                except OSError:
                    pass
        if updated_per_well:
            # Rebuild demux_result with updated counts.
            n_assigned_filtered = sum(updated_per_well.values())
            demux_result = type(demux_result)(
                output_dir=demux_result.output_dir,
                n_input_reads=demux_result.n_input_reads,
                n_assigned=n_assigned_filtered,
                n_unassigned=demux_result.n_input_reads - n_assigned_filtered,
                per_well_counts=updated_per_well,
            )

    _progress(95, "Finalising...")

    return {
        "output_dir": str(demux_result.output_dir),
        "n_input_reads": demux_result.n_input_reads,
        "n_assigned": demux_result.n_assigned,
        "n_unassigned": demux_result.n_unassigned,
        "per_well_counts": demux_result.per_well_counts,
        "filter_stats": filter_stats_dict,
        "backend": backend,
    }


__all__ = ["handle_demux_and_filter"]
