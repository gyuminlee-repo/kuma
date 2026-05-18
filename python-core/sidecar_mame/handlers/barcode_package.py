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

Optional
  gene_name            (str,   default "ispS")
  polymerase           (str,   default "Q5")
  flank_min            (int,   default 100)
  flank_max            (int,   default 400)
  binding_min_len      (int,   default 18)
  binding_max_len      (int,   default 35)
  tm_min               (float, default 55.0)
  tm_max               (float, default 68.0)
  require_gc_clamp     (bool,  default true)

Response schema
---------------
  barcodes_xlsx         (str) -- absolute path
  amplicon_fa           (str) -- absolute path
  sample_map_template   (str) -- absolute path
  context_json          (str) -- absolute path
  warnings              (list[str]) -- non-critical messages from primer design
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

    # Optional parameters
    # gene_name: required to be a non-empty string when present. The UI seeds
    # a default ("ispS") in the input panel, so empty here implies the user
    # explicitly cleared it. Silently substituting a hardcoded literal would
    # mislead operators expecting their typed gene name to flow through.
    gene_name_raw = params.get("gene_name", "ispS")
    if gene_name_raw is None or str(gene_name_raw).strip() == "":
        raise ValueError(
            "gene_name must be a non-empty string; received empty value. "
            "Type a gene name in the Project metadata panel before generating."
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
    )

    return {
        "barcodes_xlsx": str(result.barcodes_xlsx),
        "amplicon_fa": str(result.amplicon_fa),
        "sample_map_template": str(result.sample_map_template),
        "context_json": str(result.context_json),
        "warnings": result.warnings,
        "amplicon_length": result.amplicon_length,
    }


__all__ = ["handle_generate_mame_package"]
