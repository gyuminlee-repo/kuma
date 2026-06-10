"""Pydantic parameter models for MAME sidecar RPC handlers.

Each model corresponds to one JSON-RPC method and validates the ``params``
dict before the handler logic executes.

Usage pattern (in a handler)::

    from sidecar_mame.models import CombinatorialDemuxParams
    p = CombinatorialDemuxParams.model_validate(params)

Convention: all path fields are plain strings in the JSON (not Path objects)
so that serialisation round-trips cleanly.  Validators convert to ``Path``
internally when existence checks are needed, but the model stores ``str``.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, field_validator


class DemuxParamsBase(BaseModel):
    """Shared demux contract: the subset of parameters that every demux-capable
    RPC method needs, with a single source of truth for their validators.

    Both ``CombinatorialDemuxParams`` (full raw-run combinatorial demux) and
    ``AnalyzeRawRunParams`` (raw-run subset for the analyze handler) subclass
    this base so the demux validators are defined exactly once.

    Fields
    ------
    custom_barcodes_xlsx
        Path to the barcodes xlsx with ``isps_f_1..12`` and ``isps_r_1..8``
        rows.
    reference_fasta
        Single-record DNA FASTA used as alignment reference.
    mapq_threshold
        Minimum MAPQ for alignment hits.  Range [0, 60].  Default 25.
    coverage_fraction
        Minimum fraction of reference covered by each alignment hit.
        Range (0.0, 1.0].  Default 0.98.
    edit_dist_ratio
        Maximum allowed edit distance as a fraction of barcode prefix length.
        Range (0.0, 1.0).  Default 0.25.
    chimera_split
        When True (default), evaluate all alignment hits per read (chimera /
        concatemer splitting).  When False, only the first passing hit is used.
    trim_flank_bp
        Bases flanking each alignment hit to include in the per-well FASTA
        slice.  Range [0, 200].  Default 30.
    native_barcodes
        When set, run per-native-barcode demux.  Omit/None for single-pool
        mode.  Must be a non-empty list of bare names (no path separators).
    """

    # Required demux inputs
    custom_barcodes_xlsx: str
    reference_fasta: str

    # Algorithm params
    mapq_threshold: int = Field(default=25, ge=0, le=60)
    coverage_fraction: float = Field(default=0.98, gt=0.0, le=1.0)
    edit_dist_ratio: float = Field(default=0.25, gt=0.0, lt=1.0)
    chimera_split: bool = True
    trim_flank_bp: int = Field(default=30, ge=0, le=200)

    # Optional - per-native-barcode mode
    native_barcodes: list[str] | None = None

    # Shared demux validators (single source of truth)

    @field_validator("custom_barcodes_xlsx", mode="after")
    @classmethod
    def _check_barcodes_xlsx(cls, v: str) -> str:
        p = Path(v)
        if ".." in p.parts:
            raise ValueError(f"Path traversal not allowed: {v}")
        if not p.exists():
            raise ValueError(f"custom_barcodes_xlsx not found: {v}")
        return v

    @field_validator("reference_fasta", mode="after")
    @classmethod
    def _check_reference_fasta(cls, v: str) -> str:
        p = Path(v)
        if ".." in p.parts:
            raise ValueError(f"Path traversal not allowed: {v}")
        if not p.exists():
            raise ValueError(f"reference_fasta not found: {v}")
        return v

    @field_validator("native_barcodes", mode="after")
    @classmethod
    def _check_native_barcodes(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        if not v:
            raise ValueError("native_barcodes must be a non-empty list when provided")
        for entry in v:
            if not isinstance(entry, str) or not entry.strip():
                raise ValueError(
                    f"native_barcodes entry must be a non-empty string: {entry!r}"
                )
            if "/" in entry or "\\" in entry or ".." in entry:
                raise ValueError(
                    f"native_barcodes entry contains path separators: {entry!r}"
                )
        return v


class CombinatorialDemuxParams(DemuxParamsBase):
    """Parameters for the ``mame.run_combinatorial_demux`` RPC method.

    Required fields
    ---------------
    minknow_run_dir
        Root directory of a MinKNOW run.  Must contain a ``fastq_pass/``
        sub-directory with at least one ``.fastq`` or ``.fastq.gz`` file.
    custom_barcodes_xlsx
        Path to the barcodes xlsx with ``isps_f_1..12`` and ``isps_r_1..8``
        rows.
    reference_fasta
        Single-record DNA FASTA used as alignment reference.
    output_dir
        Destination directory for per-well FASTA and consensus files.
        Parent must exist; the directory itself is created if absent.

    Optional fields
    ---------------
    sample_map_xlsx
        When provided, a per-well sample-name mapping xlsx (col A: name,
        col B: well position e.g. "A1").  Loaded into metadata; the core
        pipeline uses it to annotate output filenames with mutant names.
    kuro_xlsx
        Path to a KURO results xlsx containing an ``expected_mutations``
        sheet.  Stored in params metadata for downstream stages; combinatorial
        demux itself does not consume mutation expectations.
    mapq_threshold
        Minimum MAPQ for alignment hits.  Range [0, 60].  Default 25.
    coverage_fraction
        Minimum fraction of reference covered by each alignment hit.
        Range (0.0, 1.0].  Default 0.98.
    edit_dist_ratio
        Maximum allowed edit distance as a fraction of barcode prefix length.
        Range (0.0, 1.0).  Default 0.25.
    chimera_split
        When True (default), evaluate all alignment hits per read (chimera /
        concatemer splitting).  When False, only the first passing hit is used.
    trim_flank_bp
        Bases flanking each alignment hit to include in the per-well FASTA
        slice.  Range [0, 200].  Default 30.
    """

    # Required fields
    minknow_run_dir: str
    output_dir: str

    # Optional - sample mapping and KURO metadata
    sample_map_xlsx: str | None = None
    kuro_xlsx: str | None = None

    # Path existence validators

    @field_validator("minknow_run_dir", mode="after")
    @classmethod
    def _check_minknow_run_dir(cls, v: str) -> str:
        p = Path(v)
        if ".." in p.parts:
            raise ValueError(f"Path traversal not allowed: {v}")
        if not p.exists():
            raise ValueError(f"minknow_run_dir does not exist: {v}")
        if not p.is_dir():
            raise ValueError(f"minknow_run_dir is not a directory: {v}")
        return v

    @field_validator("output_dir", mode="after")
    @classmethod
    def _check_output_dir(cls, v: str) -> str:
        p = Path(v)
        if ".." in p.parts:
            raise ValueError(f"Path traversal not allowed: {v}")
        if not p.parent.exists():
            raise ValueError(
                f"Parent of output_dir does not exist: {p.parent}"
            )
        return v

    @field_validator("sample_map_xlsx", mode="after")
    @classmethod
    def _check_sample_map_xlsx(cls, v: str | None) -> str | None:
        if v is None:
            return None
        p = Path(v)
        if ".." in p.parts:
            raise ValueError(f"Path traversal not allowed: {v}")
        if not p.exists():
            raise ValueError(f"sample_map_xlsx not found: {v}")
        return v

    @field_validator("kuro_xlsx", mode="after")
    @classmethod
    def _check_kuro_xlsx(cls, v: str | None) -> str | None:
        if v is None:
            return None
        p = Path(v)
        if ".." in p.parts:
            raise ValueError(f"Path traversal not allowed: {v}")
        if not p.exists():
            raise ValueError(f"kuro_xlsx not found: {v}")
        return v


class AnalyzeRawRunParams(DemuxParamsBase):
    """Parameters for validating the raw-run subset of the analyze handler.

    The analyze handler instantiates this model only in raw-run mode, so the
    inherited ``custom_barcodes_xlsx`` and ``reference_fasta`` requirements
    enforce "required iff raw-run".  ``reference_fasta`` is supplied by the
    handler from the existing analyze ``reference`` field.

    Required fields
    ---------------
    minknow_run_dir
        Root directory of a MinKNOW run.  Must exist and be a directory.
    custom_barcodes_xlsx
        Inherited from :class:`DemuxParamsBase`.
    reference_fasta
        Inherited from :class:`DemuxParamsBase`.

    Optional fields
    ---------------
    demux_output_dir
        When provided, the destination directory for demux outputs.  Parent
        must exist.
    """

    # Required fields
    minknow_run_dir: str

    # Optional
    demux_output_dir: str | None = None

    @field_validator("minknow_run_dir", mode="after")
    @classmethod
    def _check_minknow_run_dir(cls, v: str) -> str:
        p = Path(v)
        if ".." in p.parts:
            raise ValueError(f"Path traversal not allowed: {v}")
        if not p.exists():
            raise ValueError(f"minknow_run_dir does not exist: {v}")
        if not p.is_dir():
            raise ValueError(f"minknow_run_dir is not a directory: {v}")
        return v

    @field_validator("demux_output_dir", mode="after")
    @classmethod
    def _check_demux_output_dir(cls, v: str | None) -> str | None:
        if v is None:
            return None
        p = Path(v)
        if ".." in p.parts:
            raise ValueError(f"Path traversal not allowed: {v}")
        if not p.parent.exists():
            raise ValueError(
                f"Parent of demux_output_dir does not exist: {p.parent}"
            )
        return v


class BuildWellLayoutParams(BaseModel):
    """Parameters for the ``mame.build_well_layout`` RPC method.

    Required fields
    ---------------
    expected_mutations_xlsx
        Path to a KURO results xlsx containing an ``expected_mutations`` sheet.
        Read via ``read_expected_mutations`` and turned into a draft 96-well
        plate layout by ``build_draft_layout`` (one mutant per well in
        column-major order, followed by a single WT control well).
    """

    expected_mutations_xlsx: str

    @field_validator("expected_mutations_xlsx", mode="after")
    @classmethod
    def _check_expected_mutations_xlsx(cls, v: str) -> str:
        p = Path(v)
        if ".." in p.parts:
            raise ValueError(f"Path traversal not allowed: {v}")
        if not p.exists():
            raise ValueError(f"expected_mutations_xlsx not found: {v}")
        return v


class DetectNativeBarcodesParams(BaseModel):
    """Parameters for the ``mame.detect_native_barcodes`` RPC method.

    Required fields
    ---------------
    minknow_run_dir
        Root directory of a MinKNOW run.  Must contain a ``fastq_pass/``
        sub-directory with native-barcode subdirs.

    Optional fields
    ---------------
    min_share
        Minimum fraction of total FASTQ bytes a native barcode must hold to be
        flagged as used.  Range [0.0, 1.0].  Default 0.05.
    """

    minknow_run_dir: str
    min_share: float = Field(default=0.05, ge=0.0, le=1.0)

    @field_validator("minknow_run_dir", mode="after")
    @classmethod
    def _check_minknow_run_dir(cls, v: str) -> str:
        p = Path(v)
        if ".." in p.parts:
            raise ValueError(f"Path traversal not allowed: {v}")
        if not p.exists():
            raise ValueError(f"minknow_run_dir does not exist: {v}")
        if not p.is_dir():
            raise ValueError(f"minknow_run_dir is not a directory: {v}")
        return v


__all__ = [
    "AnalyzeRawRunParams",
    "BuildWellLayoutParams",
    "CombinatorialDemuxParams",
    "DemuxParamsBase",
    "DetectNativeBarcodesParams",
]
