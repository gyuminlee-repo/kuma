"""``sort_barcode_run`` JSON-RPC handler.

Runs the combinatorial barcode sorter: reads from a MinKNOW run directory
are matched against (fwd × rev) barcode pairs from a custom xlsx and written
to per-well FASTA files under ``sort_barcode{NN}/`` subdirectories.

RPC method name: ``sort_barcode_run``
Registered in ``sidecar_mame.dispatcher._METHODS``.

Parameter schema
----------------
``minknow_run_dir``      (str, required)  — MinKNOW run root (contains fastq_pass/)
``custom_barcodes_path`` (str, required)  — xlsx with isps_f_*/isps_r_* rows
``output_dir``           (str, required)  — destination root for sort_barcode*/ dirs
``nb_override``          (list[str], opt) — if set, only process these NB dir basenames
``error_tolerance``      (float, opt)     — per-base mismatch rate [0.0, 0.5], default 0.1
``use_cutadapt``         (bool, opt)      — reserved (pure-Python only), default True
``sample_map_path``      (str, opt)       — xlsx with sample names + well positions (col A: name, col B: position e.g. "A1").
                         When provided, filenames become ``A01_V5F_F1_R1.fasta``; without it ``A01_F1_R1.fasta``.

Response schema
---------------
``output_dir``              (str)               — resolved output directory
``nb_dirs_processed``       (list[str])         — NB dir basenames successfully processed
``n_total_reads``           (int)               — total reads across all NB dirs
``n_total_assigned``        (int)               — reads assigned to a well
``n_total_unassigned``      (int)               — reads not matched to any well
``per_nb_per_well_counts``  (dict[str, dict])   — {nb_basename: {well_id: count}}
``skipped_nb_dirs``         (list[str])         — NB dirs with no FASTQ files (skipped)
"""

from __future__ import annotations

import logging
from pathlib import Path

from sidecar_mame.core import _validate_dirpath

_logger = logging.getLogger(__name__)


def handle_sort_barcode_run(params: dict) -> dict:
    """Run combinatorial sort_barcode demux.

    Heavy I/O — should be registered as an async method in dispatcher.py.
    """
    from kuma_core.mame.ingest.sort_barcode import sort_barcode_run

    # ── minknow_run_dir ────────────────────────────────────────────────────
    minknow_run_dir = _validate_dirpath(params.get("minknow_run_dir"))

    # ── custom_barcodes_path ───────────────────────────────────────────────
    barcodes_path_raw = params.get("custom_barcodes_path")
    if not barcodes_path_raw:
        raise ValueError("'custom_barcodes_path' is required")
    # Check for ".." BEFORE resolve() — resolve() eliminates ".." components,
    # making a post-resolve check dead code (mirrors core._validate_dirpath pattern).
    _barcodes_pre = Path(str(barcodes_path_raw))
    if ".." in _barcodes_pre.parts:
        raise ValueError(
            f"Path traversal not allowed in custom_barcodes_path: {barcodes_path_raw}"
        )
    barcodes_path = _barcodes_pre.resolve()
    if not barcodes_path.exists():
        raise FileNotFoundError(f"custom_barcodes_path not found: {barcodes_path}")

    # ── output_dir ─────────────────────────────────────────────────────────
    output_dir_raw = params.get("output_dir")
    if not output_dir_raw:
        raise ValueError("'output_dir' is required")
    _output_pre = Path(str(output_dir_raw))
    if ".." in _output_pre.parts:
        raise ValueError(f"Path traversal not allowed in output_dir: {output_dir_raw}")
    output_dir = _output_pre.resolve()
    if not output_dir.parent.exists():
        raise FileNotFoundError(
            f"Parent of output_dir does not exist: {output_dir.parent}"
        )
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── Optional params ────────────────────────────────────────────────────
    nb_override_raw = params.get("nb_override")
    nb_override: list[str] | None = None
    if nb_override_raw is not None:
        if not isinstance(nb_override_raw, list):
            raise ValueError("'nb_override' must be a JSON array of strings")
        # WARNING fix: validate each entry is a plain basename before forwarding
        # to the core.  The core also validates, but fail-fast here avoids I/O.
        for entry in nb_override_raw:
            entry_str = str(entry)
            if (
                not entry_str
                or "/" in entry_str
                or "\\" in entry_str
                or "\x00" in entry_str
                or entry_str in (".", "..")
            ):
                raise ValueError(
                    f"nb_override entry must be a plain directory name: {entry!r}"
                )
        nb_override = [str(x) for x in nb_override_raw]

    error_tolerance = float(params.get("error_tolerance", 0.1))
    use_cutadapt = bool(params.get("use_cutadapt", True))

    # ── sample_map_path (optional) ─────────────────────────────────────────
    sample_map_path_raw = params.get("sample_map_path")
    sample_map_path: Path | None = None
    if sample_map_path_raw:
        _smp_pre = Path(str(sample_map_path_raw))
        if ".." in _smp_pre.parts:
            raise ValueError(
                f"Path traversal not allowed in sample_map_path: {sample_map_path_raw}"
            )
        sample_map_path = _smp_pre.resolve()
        if not sample_map_path.exists():
            raise FileNotFoundError(f"sample_map_path not found: {sample_map_path}")

    # ── Execute ────────────────────────────────────────────────────────────
    _logger.info(
        "sort_barcode_run: run_dir=%s, xlsx=%s, output=%s",
        minknow_run_dir,
        barcodes_path,
        output_dir,
    )

    result = sort_barcode_run(
        minknow_run_dir=minknow_run_dir,
        custom_barcode_xlsx=barcodes_path,
        output_dir=output_dir,
        nb_override=nb_override,
        error_tolerance=error_tolerance,
        use_cutadapt=use_cutadapt,
        sample_map_path=sample_map_path,
    )

    return {
        "output_dir": str(result.output_dir),
        "nb_dirs_processed": result.nb_dirs_processed,
        "n_total_reads": result.n_total_reads,
        "n_total_assigned": result.n_total_assigned,
        "n_total_unassigned": result.n_total_unassigned,
        "per_nb_per_well_counts": result.per_nb_per_well_counts,
        "skipped_nb_dirs": result.skipped_nb_dirs,
    }


__all__ = ["handle_sort_barcode_run"]
