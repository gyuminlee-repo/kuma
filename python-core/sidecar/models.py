"""Pydantic input-validation models for KURO sidecar JSON-RPC handlers.

All models use field names that match the exact keys the frontend sends
(verified from params.get() calls in each handler).  Pydantic v2
ValidationError is a subclass of ValueError, so the dispatcher's
``except (KeyError, ValueError)`` block catches it automatically — no
per-handler try/except is required.

Usage in handlers::

    from sidecar.models import DesignSdmPrimersParams
    p = DesignSdmPrimersParams(**params)
    # access as p.fasta_path, p.polymerase, etc.
"""

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# sequence.py handlers
# ---------------------------------------------------------------------------


class LoadFastaParams(BaseModel):
    filepath: str


class ParseMutationsTextParams(BaseModel):
    text: str = ""


# ---------------------------------------------------------------------------
# design.py handlers
# ---------------------------------------------------------------------------


class DesignSdmPrimersParams(BaseModel):
    fasta_path: str
    target_start: int = Field(default=0, ge=0)
    mutations_csv_or_text: str = ""
    polymerase: str = "Q5"
    overlap_len: int = Field(default=20, ge=15, le=40)
    codon_strategy: str = "closest"
    organism: str = "ecoli"

    # Optional Tm targets (None = use polymerase defaults)
    tm_fwd_target: Optional[float] = Field(default=None, ge=20.0, le=80.0)
    tm_rev_target: Optional[float] = Field(default=None, ge=20.0, le=80.0)
    tm_overlap_target: Optional[float] = Field(default=None, ge=20.0, le=80.0)

    # GC% constraints
    gc_min: float = Field(default=40.0, ge=0.0, le=100.0)
    gc_max: float = Field(default=60.0, ge=0.0, le=100.0)

    # Primer length constraints
    fwd_len_min: int = Field(default=18, ge=10, le=60)
    fwd_len_max: int = Field(default=45, ge=10, le=100)
    rev_len_min: int = Field(default=18, ge=10, le=60)
    rev_len_max: int = Field(default=30, ge=10, le=100)


class RetryFailedParams(BaseModel):
    mutation: str = ""
    fasta_path: str
    polymerase: str = "Benchling"
    target_start: int = Field(default=0, ge=0)
    overlap_len: int = Field(default=20, ge=15, le=40)
    codon_strategy: str = "closest"
    organism: str = "ecoli"
    tm_fwd_target: float = Field(default=62.0, ge=20.0, le=80.0)
    tm_rev_target: float = Field(default=58.0, ge=20.0, le=80.0)
    tm_overlap_target: float = Field(default=42.0, ge=20.0, le=80.0)
    gc_min: float = Field(default=40.0, ge=0.0, le=100.0)
    gc_max: float = Field(default=60.0, ge=0.0, le=100.0)
    fwd_len_min: int = Field(default=18, ge=10, le=60)
    fwd_len_max: int = Field(default=45, ge=10, le=100)
    rev_len_min: int = Field(default=18, ge=10, le=60)
    rev_len_max: int = Field(default=30, ge=10, le=100)
    num_return: int = Field(default=10, ge=1, le=960)


class SwapPrimerParams(BaseModel):
    mutation: str = ""
    candidate_idx: int = Field(default=0, ge=0)
    swap_type: Literal["both", "fwd", "rev"] = "both"


class EvaluatePrimerParams(BaseModel):
    mutation: str = "custom"
    fasta_path: str
    forward_seq: str = ""
    reverse_seq: str = ""
    overlap_len: int = Field(default=20, ge=15, le=40)


class GetAlternativesParams(BaseModel):
    mutation: str = ""


# ---------------------------------------------------------------------------
# export.py handlers
# ---------------------------------------------------------------------------


class PlateMappingItem(BaseModel):
    well: str
    primer_name: str
    sequence: str
    primer_type: str
    mutation: str
    tm: Optional[float] = None
    tm_overlap: Optional[float] = None
    wt_codon: Optional[str] = None


class ExportExcelParams(BaseModel):
    filepath: str
    mappings: Optional[list[PlateMappingItem]] = None
    dedup_info: Optional[Any] = None


class ExportOrderParams(BaseModel):
    filepath: str
    format: str = "idt"
    scale: str = "25nm"
    purification: str = "STD"


class SaveWorkspaceParams(BaseModel):
    filepath: str
    data: Any  # arbitrary JSON object

    @field_validator("data", mode="before")
    @classmethod
    def check_data_size(cls, v):
        import json as _json
        serialized = _json.dumps(v, default=str)
        if len(serialized) > 50 * 1024 * 1024:  # 50MB
            raise ValueError("Workspace data exceeds 50MB limit")
        return v


class LoadWorkspaceParams(BaseModel):
    filepath: str


# ---------------------------------------------------------------------------
# external.py handlers
# ---------------------------------------------------------------------------


class FetchDomainsParams(BaseModel):
    accession: str = ""


class SearchUniprotParams(BaseModel):
    gene_name: str = ""
    organism: str = ""
    translation: str = ""
    known_accession: str = ""


class FetchEsmEmbeddingParams(BaseModel):
    accession: str = ""
    sequence: str = ""


# ---------------------------------------------------------------------------
# misc.py handlers
# ---------------------------------------------------------------------------


class LoadEvolveproParams(BaseModel):
    filepath: str = ""
    top_n: int = Field(default=96, ge=1, le=960)
    max_per_position: int = Field(default=0, ge=0)
    domains: list[Any] = Field(default_factory=list)
    domain_diversity: bool = False
    domain_strategy: str = "proportional"
    pareto_diversity: bool = False
    entropy_weight: float = Field(default=0.0, ge=0.0)


class LandscapeEntry(BaseModel):
    variant: str
    fitness: float


class RunBenchmarkParams(BaseModel):
    landscape: list[LandscapeEntry] = Field(default_factory=list)
    ground_truth: dict[str, Any] = Field(default_factory=dict)
    n_select: int = Field(default=95, ge=1, le=960)
    strategies: list[str] = Field(default_factory=lambda: ["topn", "random", "pareto"])
