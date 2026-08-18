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

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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

    # Optional - KURO metadata
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
        Path to the expected-variant list: either a KURO results xlsx carrying an
        ``expected_mutations`` sheet, or a plain variant list (one variant per
        row, in plate order). Read via ``read_variant_source`` and turned into a
        draft 96-well plate layout by ``build_draft_layout`` (one mutant per well
        in column-major order plus exactly one WT control well, at the ordinal
        the source stated or after the last mutant when it stated none).

    Optional fields
    ---------------
    variant_sheet, variant_column
        Sheet and column holding the variant labels, for a plain list whose
        layout cannot be told apart on its own. Both default to ``None``, which
        is auto-detection: a caller that omits them (any frontend built before
        this) gets exactly the previous behaviour on a KURO export. They mirror
        the ``generate_mame_package`` params of the same names so this layout and
        every other read of the file come off the same rows.
    wt_placement
        Where to put the control well when the file does not name one:
        ``"last_well"`` (H12), ``"after_last_variant"``, or ``"none"``. Values of
        ``kuma_core.mame.layout.WtPlacement``. ``None`` takes
        ``DEFAULT_WT_PLACEMENT``, which is ``"last_well"``.

        Ignored for a file carrying a ``Well`` column, which states the control
        well itself. Nothing sends this yet: it exists so the setting the
        frontend will offer has somewhere to arrive, and so a caller that wants
        the pre-2026-08-18 placement can ask for it by name today.
    """

    expected_mutations_xlsx: str
    variant_sheet: str | None = None
    variant_column: str | None = None
    wt_placement: str | None = None

    @field_validator("expected_mutations_xlsx", mode="after")
    @classmethod
    def _check_expected_mutations_xlsx(cls, v: str) -> str:
        p = Path(v)
        if ".." in p.parts:
            raise ValueError(f"Path traversal not allowed: {v}")
        if not p.exists():
            raise ValueError(f"expected_mutations_xlsx not found: {v}")
        return v

    @field_validator("wt_placement", mode="after")
    @classmethod
    def _check_wt_placement(cls, v: str | None) -> str | None:
        """Refuse an unknown policy rather than falling back to the default.

        Silently defaulting would place the control somewhere the caller did not
        ask for and say nothing, which is the class of failure this whole change
        exists to remove.
        """
        if v is None:
            return v
        from kuma_core.mame.layout import WtPlacement

        allowed = [p.value for p in WtPlacement]
        if v not in allowed:
            raise ValueError(
                f"wt_placement must be one of {allowed}; got {v!r}"
            )
        return v


class ExportBarcodeWorklistParams(BaseModel):
    """Parameters for the ``mame.export_barcode_worklist`` RPC method.

    Required fields
    ---------------
    expected_mutations_xlsx
        The variant list, read exactly as ``mame.build_well_layout`` reads it so
        the worklist and the grid an operator ticked wells on describe one
        plate.
    output_path
        Destination csv. A save dialog picks it, so the directory may not exist
        yet and the writer creates it.

    Optional fields
    ---------------
    selected_wells
        The wells this campaign fills. ``None`` means the whole draft, which is
        what a run that declares nothing uses.
    custom_barcodes_xlsx
        The barcode workbook, for the seed NAMES. Omitting it still gives every
        well its ``{R}_{F}`` pairing, which comes from the plate.
    variant_sheet, variant_column
        Sheet and column holding the variant labels, mirroring
        ``BuildWellLayoutParams`` so both reads land on the same rows.
    """

    model_config = ConfigDict(extra="forbid")

    expected_mutations_xlsx: str
    output_path: str
    selected_wells: list[str] | None = None
    custom_barcodes_xlsx: str | None = None
    variant_sheet: str | None = None
    variant_column: str | None = None

    @field_validator("expected_mutations_xlsx", "custom_barcodes_xlsx", mode="after")
    @classmethod
    def _check_input_file(cls, v: str | None) -> str | None:
        if v is None:
            return v
        p = Path(v)
        if ".." in p.parts:
            raise ValueError(f"Path traversal not allowed: {v}")
        if not p.exists():
            raise ValueError(f"file not found: {v}")
        return v

    @field_validator("output_path", mode="after")
    @classmethod
    def _check_output_path(cls, v: str) -> str:
        # Existence is not checked: this one is written, not read. Traversal
        # still is, for the same reason it is on every other path here.
        if ".." in Path(v).parts:
            raise ValueError(f"Path traversal not allowed: {v}")
        return v

    @field_validator("selected_wells", mode="after")
    @classmethod
    def _check_selected_wells(cls, v: list[str] | None) -> list[str] | None:
        # An empty declaration is refused for the same reason ``analyze``
        # refuses it: a campaign with no wells has no barcodes to pipette, and
        # writing an empty sheet would answer the question with silence.
        if v is not None and not v:
            raise ValueError(
                "selected_wells is empty. A campaign with no wells uses no "
                "barcodes; omit the parameter to use the whole plate."
            )
        return v


class BuildEvolveproInputParams(BaseModel):
    """Strict request contract for the unified MAME Step 3 builder."""

    model_config = ConfigDict(extra="forbid")

    activity_path: str | None = None
    activity_scale: str = "raw"
    gc_data_xlsx: str | None = None
    round1_report_xlsx: str | None = None
    remeasure_report_xlsx: str | None = None
    verdict_xlsx: str
    layout_xlsx: str | None = None
    output_xlsx: str
    mismatch_threshold: float = Field(default=0.1, gt=0.0)
    gc_export_xlsx: str | None = None
    allow_label_mismatch: bool = False

    @field_validator("activity_path", mode="after")
    @classmethod
    def _check_activity_path(cls, v: str | None) -> str | None:
        if v is None:
            return None
        p = Path(v)
        if ".." in p.parts:
            raise ValueError(f"Path traversal not allowed: {v}")
        if p.suffix.lower() not in {".csv", ".xlsx", ".xls"}:
            raise ValueError(f"activity_path must be .csv, .xlsx, or .xls: {v}")
        if not p.exists():
            raise ValueError(f"activity_path not found: {v}")
        return v

    @field_validator(
        "gc_data_xlsx", "round1_report_xlsx", "remeasure_report_xlsx",
        "verdict_xlsx", "layout_xlsx", mode="after",
    )
    @classmethod
    def _check_input_xlsx(cls, v: str | None) -> str | None:
        if v is None:
            return None
        p = Path(v)
        if ".." in p.parts:
            raise ValueError(f"Path traversal not allowed: {v}")
        if p.suffix.lower() != ".xlsx":
            raise ValueError(f"Input must be an .xlsx file: {v}")
        if not p.exists():
            raise ValueError(f"Input xlsx not found: {v}")
        return v

    @field_validator("activity_scale")
    @classmethod
    def _check_activity_scale(cls, v: str) -> str:
        if v not in {"raw", "relative_to_wt"}:
            raise ValueError("activity_scale must be 'raw' or 'relative_to_wt'")
        return v

    @model_validator(mode="after")
    def _primary_source(self) -> "BuildEvolveproInputParams":
        sources = [
            name for name, value in (
                ("activity_path", self.activity_path),
                ("gc_data_xlsx", self.gc_data_xlsx),
                ("round1_report_xlsx", self.round1_report_xlsx),
            ) if value
        ]
        if len(sources) != 1:
            raise ValueError(
                "provide exactly one primary source: activity_path, gc_data_xlsx, "
                "or round1_report_xlsx"
            )
        if self.gc_data_xlsx and not self.layout_xlsx:
            raise ValueError("gc_data_xlsx is well-labeled and requires layout_xlsx")
        if self.round1_report_xlsx and not self.layout_xlsx:
            raise ValueError(
                "round1_report_xlsx is well-labeled and requires layout_xlsx"
            )
        return self

    @field_validator("output_xlsx", "gc_export_xlsx", mode="after")
    @classmethod
    def _check_output_xlsx(cls, v: str | None) -> str | None:
        if v is None:
            return None
        p = Path(v)
        if ".." in p.parts:
            raise ValueError(f"Path traversal not allowed: {v}")
        if p.suffix.lower() != ".xlsx":
            raise ValueError(f"Output must be an .xlsx file: {v}")
        if not p.parent.exists():
            raise ValueError(f"Parent of output path does not exist: {p.parent}")
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
    "BuildEvolveproInputParams",
    "BuildWellLayoutParams",
    "CombinatorialDemuxParams",
    "DemuxParamsBase",
    "DetectNativeBarcodesParams",
]
