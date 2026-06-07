"""``demux_and_filter`` JSON-RPC handler.

Runs A1 (custom barcode demux), A3 (per-read quality filter), and — when
``reference_fasta`` is provided — A4/A5 (alignment + consensus calling) on a
MinKNOW native-barcode directory.

When ``reference_fasta`` is given, each per-well FASTA output becomes a
single-record consensus FASTA (equivalent to ``samtools consensus`` per well),
which is directly compatible with ``analyze`` → ``load_barcode_directory``.

When ``reference_fasta`` is omitted, the handler writes per-well raw-read
FASTA bundles (legacy behaviour, maintained for backward compatibility).

.. warning::
    Legacy mode output (no ``reference_fasta``) contains multi-header raw-read
    FASTA files.  Passing this output directly to ``analyze()`` will raise
    ValueError (fail-fast multi-header guard in ``fasta_parser.parse_fasta_file``).
    Always provide ``reference_fasta`` when the result will be consumed by
    ``analyze()``.

RPC name: ``demux_and_filter``
Method is registered in ``dispatcher.py`` as an async method (heavy I/O).

Parameter schema
----------------
``fastq_dir``            (str, required)   — path to fastq_pass/barcodeN/ directory
``custom_barcodes``      (dict, optional)  — {well_name: barcode_seq} mapping
``custom_barcodes_path`` (str, optional)   — xlsx/csv path; parsed on sidecar side
``output_dir``           (str, required)   — destination directory for per-well FASTA
``reference_fasta``      (str, optional)   — path to reference FASTA for consensus calling;
                         when provided, A4/A5 pipeline is run and output is single-record
                         consensus FASTA per well (required for analyze compatibility)
``error_tolerance``      (float, optional) — mismatch rate [0.0, 0.5], default 0.1
``use_cutadapt``         (bool, optional)  — prefer cutadapt if on PATH, default True
``sequencing_summary``   (str, optional)   — path to sequencing_summary_*.txt (A3)
``min_qscore``           (float, optional) — Phred Q threshold, default 8.0
``length_min``           (int, optional)   — min read length fallback, default 800
``length_max``           (int, optional)   — max read length fallback, default 3000
``target_length``        (int | null, opt) — modal amplicon length (bp); auto-detected
                         when omitted and ``auto_detect_length`` is True
``length_tolerance_bp``  (int, optional)   — ± window around target_length, default 30
``auto_detect_length``   (bool, optional)  — run detect_amplicon_length when
                         target_length is None, default True
``min_barcode_score``    (float, optional) — MinKNOW barcode_score threshold, default 60.0
``linked_trim``          (bool, optional)  — trim rev primer from 3′ end, default False
``rev_primer_universal`` (str | null, opt) — 5′→3′ seq of universal rev primer;
                         required when linked_trim=True
``normalize_headers``    (bool, optional)  — write >{well} FASTA headers, default True
``nb_dirs``              (list[str], opt)  — if set, demux each subdirectory separately;
                         if omitted, auto-detected from fastq_dir subdirs matching
                         barcode\\d+ or NB\\d+ pattern (see detect_native_barcode_dirs)
``save_intermediate_reads`` (bool, optional) — when True, intermediate raw-read FASTA files
                         are kept on disk alongside the final consensus FASTA;
                         default False (raw-read files removed after consensus)
``min_mapq``             (int, optional)   — MAPQ threshold for alignment filter, default 25
``min_consensus_depth``  (int, optional)   — minimum per-position depth for base call, default 1

Response schema
---------------
``output_dir``                  (str)        — directory containing per-well FASTA files
``n_input_reads``               (int)
``n_assigned``                  (int)
``n_unassigned``                (int)
``per_well_counts``             (dict[str, int])
``filter_stats``                (dict | null)— QualityFilterResult as dict, or null
``backend``                     (str)        — "cutadapt" | "python"
``amplicon_length_estimate``    (dict | null)— AmpliconLengthEstimate as dict, or null
``length_filter_mode``          (str)        — "target_window" | "fixed_range" | "none"
``auto_detected_nb_count``      (int | null) — number of NB dirs auto-detected; None when
                                 nb_dirs was explicitly provided or single-NB fallback
``auto_detected_nb_names``      (list[str] | null) — basenames of auto-detected dirs;
                                 None in the same cases as auto_detected_nb_count
``consensus_stats``             (dict | null)— per-well ConsensusResult as dict, or null
                                 (null when reference_fasta not provided)
``consensus_pipeline``          (bool)       — True when A4/A5 pipeline was executed
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

from sidecar_mame.core import (
    _progress,
    _validate_dirpath,
)
from kuma_core.mame.ingest.consensus_metadata import (
    ConsensusMetadata,
    format_consensus_fasta_record,
)
from kuma_core.mame.ingest.well_consensus import compute_well_consensuses

_logger = logging.getLogger(__name__)


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
# Consensus helper: read per-well FASTA files → (read_id, seq) lists
# ---------------------------------------------------------------------------


def _collect_fastq_quality_by_read_id(fastq_dir: Path) -> dict[str, str]:
    """Return ``{read_id: quality_string}`` for FASTQ records under *fastq_dir*."""
    from kuma_core.mame.ingest.quality_filter import _iter_fastq_records

    quality_by_read_id: dict[str, str] = {}
    fastq_files = sorted(
        [p for p in fastq_dir.rglob("*.fastq")]
        + [p for p in fastq_dir.rglob("*.fastq.gz")]
    )
    for fastq_path in fastq_files:
        for read_id, _seq, qual in _iter_fastq_records(fastq_path):
            quality_by_read_id.setdefault(read_id, qual)
    return quality_by_read_id


def _collect_reads_from_fasta_dir(
    fasta_dir: Path,
    quality_by_read_id: dict[str, str] | None = None,
) -> dict[str, list[tuple[str, ...]]]:
    """Read all per-well FASTA files under fasta_dir and return per-well reads.

    Returns a dict mapping well name (FASTA stem) to a list of
    (read_id, sequence) pairs.  Multi-header FASTA files (raw read bundles) are
    handled correctly here — the caller passes them to the alignment step.
    """
    per_well: dict[str, list[tuple[str, ...]]] = {}

    for fasta_path in sorted(fasta_dir.glob("*.fasta")):
        if fasta_path.name.startswith("_"):
            continue  # skip _unassigned.fasta
        well_name = fasta_path.stem
        reads: list[tuple[str, ...]] = []
        current_id: str | None = None
        seq_parts: list[str] = []

        with fasta_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.rstrip("\r\n")
                if line.startswith(">"):
                    if current_id is not None and seq_parts:
                        seq = "".join(seq_parts).upper()
                        qual = (
                            quality_by_read_id.get(current_id)
                            if quality_by_read_id is not None
                            else None
                        )
                        reads.append(
                            (current_id, seq, qual) if qual is not None else (current_id, seq)
                        )
                    current_id = line[1:].strip().split()[0] or well_name
                    seq_parts = []
                elif line:
                    seq_parts.append(line.strip())

        if current_id is not None and seq_parts:
            seq = "".join(seq_parts).upper()
            qual = (
                quality_by_read_id.get(current_id)
                if quality_by_read_id is not None
                else None
            )
            reads.append(
                (current_id, seq, qual) if qual is not None else (current_id, seq)
            )

        if reads:
            per_well[well_name] = reads

    return per_well


def _run_consensus_on_dir(
    fasta_dir: Path,
    reference_fasta: Path,
    min_mapq: int = 25,
    min_depth: int = 1,
    save_intermediate: bool = False,
    quality_by_read_id: dict[str, str] | None = None,
) -> dict[str, dict]:
    """Run alignment + consensus on all per-well FASTA files in fasta_dir.

    Replaces each well's raw-read FASTA with a single-record consensus FASTA.
    Returns per-well statistics as JSON-serialisable dicts.
    """

    per_well_reads = _collect_reads_from_fasta_dir(
        fasta_dir,
        quality_by_read_id=quality_by_read_id,
    )

    if not per_well_reads:
        return {}

    consensus_map = compute_well_consensuses(
        per_well_reads=per_well_reads,
        reference_fasta=reference_fasta,
        min_mapq=min_mapq,
        require_full_span=True,
        min_depth=min_depth,
    )

    stats: dict[str, dict] = {}

    for well_name, result in consensus_map.items():
        fasta_path = fasta_dir / f"{well_name}.fasta"

        # Optionally keep original raw-read FASTA.
        if save_intermediate and fasta_path.exists():
            raw_path = fasta_dir / f"{well_name}.raw_reads.fasta"
            try:
                fasta_path.rename(raw_path)
            except OSError as exc:
                _logger.warning("Could not rename raw FASTA %s: %s", fasta_path, exc)

        # Write single-record consensus FASTA with depth metadata so downstream
        # analysis can use true consensus read depth instead of file size.
        fasta_path.write_text(
            format_consensus_fasta_record(
                well_name,
                result.consensus_seq,
                ConsensusMetadata(
                    depth=result.n_passed_filter,
                    input_reads=result.n_input_reads,
                    aligned_reads=result.n_aligned,
                    mapq_failed=result.n_mapq_failed,
                    span_failed=result.n_span_failed,
                    mixed_positions=result.n_mixed_positions,
                    max_minor_allele_fraction=result.max_minor_allele_fraction,
                    low_depth_positions=result.n_low_depth_positions,
                    consensus_n_fraction=result.consensus_n_fraction,
                    low_quality_bases=result.n_low_quality_bases,
                ),
            ),
            encoding="utf-8",
        )

        stats[well_name] = {
            "consensus_seq_length": len(result.consensus_seq),
            "n_input_reads": result.n_input_reads,
            "n_aligned": result.n_aligned,
            "n_passed_filter": result.n_passed_filter,
            "n_unaligned": result.n_unaligned,
            "n_mapq_failed": result.n_mapq_failed,
            "n_span_failed": result.n_span_failed,
            "mean_depth": round(result.mean_depth, 2),
            "n_mixed_positions": result.n_mixed_positions,
            "max_minor_allele_fraction": round(result.max_minor_allele_fraction, 3),
            "n_low_depth_positions": result.n_low_depth_positions,
            "consensus_n_fraction": round(result.consensus_n_fraction, 3),
            "n_low_quality_bases": result.n_low_quality_bases,
        }

    # Remove wells that had zero passing reads (empty consensus).
    empty_wells = [
        w for w, s in stats.items() if s["n_passed_filter"] == 0
    ]
    for w in empty_wells:
        fasta_path = fasta_dir / f"{w}.fasta"
        try:
            fasta_path.unlink()
        except OSError as exc:
            _logger.warning("Could not remove empty consensus FASTA %s: %s", fasta_path, exc)
        _logger.info("Well %s: no reads passed alignment filter — removed.", w)

    return stats


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


def handle_demux_and_filter(params: dict) -> dict:
    """Run demux (A1) + quality filter (A3) [+ alignment + consensus (A4/A5)] on a
    native-barcode FASTQ directory.

    Heavy I/O — registered as an async method in dispatcher.py.
    """
    from kuma_core.mame.ingest.demux import (
        DemuxResult,
        demux_native_barcode,
        detect_native_barcode_dirs,
    )
    from kuma_core.mame.ingest.quality_filter import (
        AmpliconLengthEstimate,
        QualityFilterParams,
        detect_amplicon_length,
    )

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

    # ── Reference FASTA (optional — enables A4/A5 consensus pipeline) ────
    reference_fasta_raw = params.get("reference_fasta")
    reference_fasta: Path | None = None
    if reference_fasta_raw:
        reference_fasta = Path(str(reference_fasta_raw)).resolve()
        if ".." in reference_fasta.parts:
            raise ValueError("Path traversal not allowed in reference_fasta")
        if not reference_fasta.exists():
            raise FileNotFoundError(f"reference_fasta not found: {reference_fasta}")

    # ── Consensus pipeline params ─────────────────────────────────────────
    save_intermediate = bool(params.get("save_intermediate_reads", False))
    min_mapq = int(params.get("min_mapq", 25))
    min_consensus_depth = int(params.get("min_consensus_depth", 1))

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
    linked_trim = bool(params.get("linked_trim", False))
    rev_primer_universal: str | None = params.get("rev_primer_universal") or None
    normalize_headers = bool(params.get("normalize_headers", True))
    # Consensus calling needs original read IDs so FASTQ quality strings can be
    # joined back into the pileup.  Final consensus FASTA headers are still
    # normalized to the well name by _run_consensus_on_dir.
    demux_normalize_headers = normalize_headers and reference_fasta is None

    # ── Optional quality filter params ───────────────────────────────────
    seq_summary_raw = params.get("sequencing_summary")
    sequencing_summary: Path | None = None
    if seq_summary_raw:
        sequencing_summary = Path(str(seq_summary_raw)).resolve()
        if not sequencing_summary.exists():
            raise FileNotFoundError(
                f"sequencing_summary not found: {sequencing_summary}"
            )

    # ── Optional multi-NB mode ───────────────────────────────────────────
    nb_dirs_raw: list[str] | None = params.get("nb_dirs")

    # Track whether auto-detection was used (for response fields).
    auto_detected_nb_count: int | None = None
    auto_detected_nb_names: list[str] | None = None

    if nb_dirs_raw is None:
        # Auto-detect: scan fastq_dir for barcode*/NB* subdirs.
        # Explicit nb_dirs takes priority; auto-detect only fires when omitted.
        detected = detect_native_barcode_dirs(fastq_dir)
        if detected:
            nb_dirs_raw = [str(p) for p in detected]
            auto_detected_nb_count = len(detected)
            auto_detected_nb_names = [p.name for p in detected]
            _progress(2, f"Auto-detected {len(detected)} native barcode dirs")
        # else: leave nb_dirs_raw as None → single-NB mode (existing behaviour)

    # ── Amplicon length: auto-detect or use provided value ───────────────
    target_length_raw = params.get("target_length")
    auto_detect = bool(params.get("auto_detect_length", True))
    length_tolerance_bp = int(params.get("length_tolerance_bp", 30))

    amplicon_estimate: AmpliconLengthEstimate | None = None
    target_length: int | None = None

    if target_length_raw is not None:
        target_length = int(target_length_raw)
    elif auto_detect:
        _progress(3, "Detecting amplicon length...")
        # When multi-NB dirs are present, fastq_dir contains subdirs rather than
        # FASTQ files directly.  Run amplicon detection on the first NB subdir
        # so that detect_amplicon_length finds actual FASTQ files.
        amplicon_detect_dir = fastq_dir
        if nb_dirs_raw:
            first_nb = Path(nb_dirs_raw[0])
            if first_nb.is_dir():
                amplicon_detect_dir = first_nb
        amplicon_estimate = detect_amplicon_length(amplicon_detect_dir)
        if amplicon_estimate is not None:
            target_length = amplicon_estimate.detected_length

    qf_params = QualityFilterParams(
        min_qscore=float(params.get("min_qscore", 8.0)),
        length_min=int(params.get("length_min", 800)),
        length_max=int(params.get("length_max", 3000)),
        min_barcode_score=float(params.get("min_barcode_score", 60.0)),
        target_length=target_length,
        length_tolerance_bp=length_tolerance_bp,
    )

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
                linked_trim=linked_trim,
                rev_primer_universal=rev_primer_universal,
                normalize_headers=demux_normalize_headers,
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
        _progress(10, "Demuxing reads...")
        single_nb_out = output_dir / fastq_dir.name
        single_nb_out.mkdir(parents=True, exist_ok=True)
        inner = demux_native_barcode(
            fastq_dir=fastq_dir,
            custom_barcodes=custom_barcodes,
            output_dir=single_nb_out,
            error_tolerance=error_tolerance,
            use_cutadapt=use_cutadapt,
            linked_trim=linked_trim,
            rev_primer_universal=rev_primer_universal,
            normalize_headers=demux_normalize_headers,
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
        from kuma_core.mame.ingest.quality_filter import (
            _parse_sequencing_summary,
            _resolve_length_window,
        )

        # Build fail set from sequencing_summary.
        summary_meta = _parse_sequencing_summary(sequencing_summary)
        fail_read_ids: set[str] = set()
        n_qf_input = 0
        n_qf_failed_qscore = 0
        n_qf_failed_length = 0
        n_qf_failed_barcode = 0

        # Resolve the effective length window (target_length takes priority over
        # length_min/length_max when set).
        _len_min, _len_max = _resolve_length_window(qf_params)

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
                    if length_i < _len_min or length_i > _len_max:
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
                except OSError as exc:
                    _logger.warning("Could not remove empty FASTA %s: %s", fasta_file, exc)
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

    # ── A4/A5: Alignment + consensus (when reference_fasta provided) ──────
    consensus_stats_dict: dict | None = None
    consensus_pipeline = False

    if reference_fasta is not None:
        _progress(75, "Running alignment and consensus calling...")
        all_consensus_stats: dict[str, dict] = {}

        if nb_dirs_raw:
            # Multi-NB: run consensus for each NB subdirectory.
            total_nb = len(nb_dirs_raw)
            for idx, nb_dir_str in enumerate(nb_dirs_raw):
                nb_dir = Path(nb_dir_str).resolve()
                nb_out = output_dir / nb_dir.name
                if not nb_out.is_dir():
                    continue
                pct = 75 + int(15 * idx / total_nb)
                _progress(pct, f"Consensus calling {nb_dir.name}...")
                nb_stats = _run_consensus_on_dir(
                    fasta_dir=nb_out,
                    reference_fasta=reference_fasta,
                    min_mapq=min_mapq,
                    min_depth=min_consensus_depth,
                    save_intermediate=save_intermediate,
                    quality_by_read_id=_collect_fastq_quality_by_read_id(nb_dir),
                )
                # Namespace stats by NB dir.
                for well, stat in nb_stats.items():
                    all_consensus_stats[f"{nb_dir.name}/{well}"] = stat
        else:
            # Single-NB: run consensus in the single NB subdir.
            single_nb_out = output_dir / fastq_dir.name
            if single_nb_out.is_dir():
                _progress(76, "Consensus calling...")
                all_consensus_stats = _run_consensus_on_dir(
                    fasta_dir=single_nb_out,
                    reference_fasta=reference_fasta,
                    min_mapq=min_mapq,
                    min_depth=min_consensus_depth,
                    save_intermediate=save_intermediate,
                    quality_by_read_id=_collect_fastq_quality_by_read_id(fastq_dir),
                )

        consensus_stats_dict = all_consensus_stats if all_consensus_stats else {}
        consensus_pipeline = True

        # Rebuild per_well_counts after consensus.
        # Wells with zero aligned reads are removed by _run_consensus_on_dir.
        # Use n_input_reads from consensus_stats to preserve the original demux
        # read count (the raw-read count before alignment filtering).
        post_consensus_per_well: dict[str, int] = {}
        for well_key, stat in all_consensus_stats.items():
            # well_key is either "<well>" (single-NB) or "<NB>/<well>" (multi-NB).
            # Use the stem (last path component) as the dict key for per_well_counts,
            # consistent with how demux populates it.
            short_key = well_key.split("/")[-1] if "/" in well_key else well_key
            # Use n_input_reads so the frontend can display "X reads → consensus"
            # rather than a constant 1.
            post_consensus_per_well[short_key] = stat["n_input_reads"]
        if post_consensus_per_well:
            demux_result = type(demux_result)(
                output_dir=demux_result.output_dir,
                n_input_reads=demux_result.n_input_reads,
                n_assigned=demux_result.n_assigned,
                n_unassigned=demux_result.n_unassigned,
                per_well_counts=post_consensus_per_well,
            )

    _progress(95, "Finalising...")

    # Determine which length filter mode was active (for frontend display).
    if qf_params.target_length is not None:
        length_filter_mode = "target_window"
    elif qf_params.length_min != 0 or qf_params.length_max != 0:
        length_filter_mode = "fixed_range"
    else:
        length_filter_mode = "none"

    amplicon_estimate_dict: dict | None = None
    if amplicon_estimate is not None:
        amplicon_estimate_dict = {
            "detected_length": amplicon_estimate.detected_length,
            "n_sample_reads": amplicon_estimate.n_sample_reads,
            "confidence": amplicon_estimate.confidence,
            "distribution_summary": amplicon_estimate.distribution_summary,
        }

    return {
        "output_dir": str(demux_result.output_dir),
        "n_input_reads": demux_result.n_input_reads,
        "n_assigned": demux_result.n_assigned,
        "n_unassigned": demux_result.n_unassigned,
        "per_well_counts": demux_result.per_well_counts,
        "filter_stats": filter_stats_dict,
        "backend": backend,
        "amplicon_length_estimate": amplicon_estimate_dict,
        "length_filter_mode": length_filter_mode,
        "auto_detected_nb_count": auto_detected_nb_count,
        "auto_detected_nb_names": auto_detected_nb_names,
        "consensus_stats": consensus_stats_dict,
        "consensus_pipeline": consensus_pipeline,
    }


__all__ = ["handle_demux_and_filter"]
