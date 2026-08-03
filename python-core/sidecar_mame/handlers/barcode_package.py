"""``generate_mame_package`` JSON-RPC handler.

Delegates to :mod:`kuma_core.mame.ingest.barcode_package`.

RPC method name: ``generate_mame_package``
Registered in ``sidecar_mame.dispatcher._METHODS``.

Parameter schema
----------------
Required
  fasta_path           (str) -- path to CDS FASTA file
  gene_start           (int) -- 0-based inclusive gene start within CDS
  gene_end             (int) -- 0-based exclusive gene end within CDS
  barcode_seeds_path   (str) -- path to barcode seeds xlsx (fwd_1..12, rev_1..8)
  output_dir           (str) -- destination directory for outputs
  project_root         (str) -- project root for mame_context.json
  gene_name            (str) -- gene identifier for output filenames/labels;
                         annotated inputs auto-fill this from /gene=,
                         /locus_tag=, or /product=; plain FASTA requires explicit
                         entry (no default — omit or blank raises ValueError)

Optional
  polymerase           (str,   default "Q5")
  flank_min            (int,   default 100)
  flank_max            (int,   default 400)
  binding_min_len      (int,   default 18)
  binding_max_len      (int,   default 35)
  tm_min               (float, default 55.0)
  tm_max               (float, default 68.0)
  require_gc_clamp     (bool,  default true)
  topology              (str,  default None -- auto-detect from fasta_path;
                         explicit "linear" or "circular" overrides detection)
  variant_sheet (str, default None) -- sheet holding the variant list, when the
    file is not a KURO export and the sheet cannot be inferred.
  variant_column (str, default None) -- column holding the variant labels, for
    the same case.
  expected_mutations_path (str, default None) -- variant list xlsx. When given,
                         sample_map_template.xlsx is pre-filled with a draft
                         well placement (one designed mutant per well in
                         column-major order, WT control last) instead of
                         headers only.

Response schema
---------------
  barcodes_xlsx         (str) -- absolute path
  amplicon_fa           (str) -- absolute path
  sample_map_template   (str) -- absolute path
  context_json          (str) -- absolute path
  warnings              (list[str]) -- non-critical messages from primer design
  sample_map_prefilled_rows (int) -- pre-filled data rows in the template
                         (0 = header only, or template left untouched)
  sample_map_preserved  (bool) -- true when an existing template already held
                         well assignments and was therefore not rewritten
"""

from __future__ import annotations

import logging
from pathlib import Path

from sidecar_mame.core import (
    _validate_filepath,
    _ALLOWED_SEQUENCE_EXTENSIONS,
    _ALLOWED_EXCEL_EXTENSIONS,
)

_logger = logging.getLogger(__name__)


def _optional_str(raw: object) -> str | None:
    """Treat absent, null and blank alike: the caller did not choose."""
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


def handle_inspect_variant_source(params: dict) -> dict:
    """Report the sheets and columns a variant list offers.

    Lets the UI present the same sheet/column pickers the KURO input step uses,
    rather than rejecting a file whose layout is merely unfamiliar. A KURO export
    answers ``is_kuro_export`` so no mapping is asked for.

    Parameters
    ----------
    path : str
        Variant list to inspect (xlsx or csv).
    """
    from kuma_core.mame.io.variant_list import inspect_variant_source

    raw = _optional_str(params.get("path"))
    if raw is None:
        raise ValueError("path is required")
    info = inspect_variant_source(Path(raw))
    return {
        "is_kuro_export": info.is_kuro_export,
        "sheets": info.sheets,
        "headers": info.headers,
        "suggested_column": info.suggested_column,
    }


def handle_check_plate_order(params: dict) -> dict:
    """Report whether an exported workbook describes one plate or two.

    MAME reads row *i* of ``expected_mutations`` as well *i*, so that sheet and the
    primer plate sheets in the same file are the same statement written twice. Exports
    written before v0.14.3 could disagree, and the disagreement is invisible in the
    numbers: every well gets a variant and the verdicts come out scored against a plate
    nobody built. A caller asks this when loading a project so the mismatch is stated
    instead of inherited.

    Parameters
    ----------
    path : str
        Workbook to check (xlsx). Anything else answers ``comparable: false``.
    """
    from kuma_core.mame.io.plate_order_check import check_plate_order

    raw = _optional_str(params.get("path"))
    if raw is None:
        raise ValueError("path is required")
    report = check_plate_order(Path(raw))
    return {
        "comparable": report.comparable,
        "mismatched": report.mismatched,
        "plate_sheet": report.plate_sheet,
        "examples": [
            {"well": well, "plate": plate, "expected": expected}
            for well, plate, expected in report.examples
        ],
        "missing_from_expected": report.missing_from_expected,
        "absent_from_plate": report.absent_from_plate,
    }


def handle_generate_mame_package(params: dict) -> dict:
    """Generate the MAME barcode package from seeds and a CDS FASTA.

    Raises
    ------
    KeyError   -- missing required parameter
    ValueError -- invalid numeric param or validation failure in core
    FileNotFoundError -- input file not found
    """
    from kuma_core.mame.ingest.barcode_package import generate_mame_package

    # Required string parameters
    fasta_path_str: str = params["fasta_path"]
    barcode_seeds_str: str = params["barcode_seeds_path"]
    output_dir_str: str = params["output_dir"]
    project_root_str: str = params["project_root"]

    # Required numeric parameters (explicit fail-fast on missing/wrong type)
    try:
        gene_start = int(params["gene_start"])
        gene_end = int(params["gene_end"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            f"gene_start and gene_end must be integers: {exc}"
        ) from exc

    # gene_name is required. The UI supplies it from annotation autofill or
    # explicit user entry; a fixed fallback would mislabel other targets.
    gene_name_raw = params.get("gene_name")
    if gene_name_raw is None or str(gene_name_raw).strip() == "":
        raise ValueError(
            "gene_name is required and must be a non-empty string. "
            "Annotated inputs (GenBank/SnapGene) auto-fill this field; "
            "plain FASTA requires an explicit entry in the Project metadata panel."
        )
    gene_name: str = str(gene_name_raw).strip()
    polymerase: str = str(params.get("polymerase", "Q5"))

    try:
        flank_min = int(params.get("flank_min", 100))
        flank_max = int(params.get("flank_max", 400))
        binding_min_len = int(params.get("binding_min_len", 18))
        binding_max_len = int(params.get("binding_max_len", 35))
        tm_min = float(params.get("tm_min", 55.0))
        tm_max = float(params.get("tm_max", 68.0))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid numeric parameter: {exc}") from exc

    require_gc_clamp_raw = params.get("require_gc_clamp", True)
    if isinstance(require_gc_clamp_raw, str):
        require_gc_clamp = require_gc_clamp_raw.lower() not in ("false", "0", "no")
    else:
        require_gc_clamp = bool(require_gc_clamp_raw)

    # topology: None means "auto-detect from fasta_path" (handled inside
    # generate_mame_package). An explicit override must be one of the two
    # recognised literal values; anything else is a client error.
    topology_raw = params.get("topology")
    if topology_raw is not None and topology_raw not in ("linear", "circular"):
        raise ValueError(
            f'topology must be "linear", "circular", or omitted; got {topology_raw!r}.'
        )
    topology: str | None = topology_raw

    # Validate input file paths (existence + extension check)
    # _validate_filepath already enforces existence by default.
    fasta_path = _validate_filepath(
        fasta_path_str,
        allowed_extensions=_ALLOWED_SEQUENCE_EXTENSIONS,
    )
    barcode_seeds_path = _validate_filepath(
        barcode_seeds_str,
        allowed_extensions=_ALLOWED_EXCEL_EXTENSIONS,
    )

    # Optional variant list for sample-map pre-fill. Absent/empty means
    # "emit a header-only template"; a supplied path must be a readable xlsx
    # (validated here so a typo surfaces before primer design runs).
    # A KURO export is detected downstream and keeps its strict reader; any other
    # workbook is read as a plain list, optionally with sheet/column overrides.
    expected_mutations_raw = params.get("expected_mutations_path")
    expected_mutations_path: Path | None = None
    if expected_mutations_raw is not None and str(expected_mutations_raw).strip() != "":
        expected_mutations_path = _validate_filepath(
            str(expected_mutations_raw),
            allowed_extensions=_ALLOWED_EXCEL_EXTENSIONS,
        )

    # output_dir and project_root are directories that may not yet exist;
    # validate as plain paths (no extension check needed).
    # Block path traversal before resolve() eliminates ".." components.
    for label, raw in (("output_dir", output_dir_str), ("project_root", project_root_str)):
        pre = Path(str(raw))
        if ".." in pre.parts:
            raise ValueError(f"Path traversal not allowed in {label}: {raw}")

    output_dir = Path(output_dir_str)
    project_root = Path(project_root_str)

    _logger.info(
        "generate_mame_package: fasta=%s, gene=%d..%d, output=%s",
        fasta_path,
        gene_start,
        gene_end,
        output_dir,
    )

    result = generate_mame_package(
        fasta_path=fasta_path,
        gene_start=gene_start,
        gene_end=gene_end,
        barcode_seeds_path=barcode_seeds_path,
        output_dir=output_dir,
        project_root=project_root,
        gene_name=gene_name,
        polymerase=polymerase,
        flank_min=flank_min,
        flank_max=flank_max,
        binding_min_len=binding_min_len,
        binding_max_len=binding_max_len,
        tm_min=tm_min,
        tm_max=tm_max,
        require_gc_clamp=require_gc_clamp,
        topology=topology,
        expected_mutations_path=expected_mutations_path,
        variant_sheet=_optional_str(params.get("variant_sheet")),
        variant_column=_optional_str(params.get("variant_column")),
    )

    return {
        "barcodes_xlsx": str(result.barcodes_xlsx),
        "amplicon_fa": str(result.amplicon_fa),
        "sample_map_template": str(result.sample_map_template),
        "context_json": str(result.context_json),
        "warnings": result.warnings,
        "amplicon_length": result.amplicon_length,
        "sample_map_prefilled_rows": result.sample_map_prefilled_rows,
        "sample_map_preserved": result.sample_map_preserved,
    }


__all__ = ["handle_generate_mame_package"]
