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

from typing import Any, Literal, Optional, TypedDict

from pydantic import BaseModel, Field, field_validator


class DomainEntry(TypedDict):
    """A single protein domain passed from the frontend to selection/benchmark handlers."""
    name: str
    start: int
    end: int


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
    # None → resolved from polymerase profile (slide spec: 18). le=18 hard-caps user input.
    overlap_len: Optional[int] = Field(default=None, ge=8, le=18)
    codon_strategy: str = "closest"
    organism: str = "ecoli"

    # Optional Tm targets (None = use polymerase defaults)
    tm_fwd_target: Optional[float] = Field(default=None, ge=20.0, le=80.0)
    tm_rev_target: Optional[float] = Field(default=None, ge=20.0, le=80.0)
    tm_overlap_target: Optional[float] = Field(default=None, ge=20.0, le=80.0)

    # GC% constraints
    gc_min: float = Field(default=40.0, ge=0.0, le=100.0)
    gc_max: float = Field(default=60.0, ge=0.0, le=100.0)

    # Primer length constraints (None → resolved from polymerase profile)
    fwd_len_min: Optional[int] = Field(default=None, ge=10, le=60)
    fwd_len_max: Optional[int] = Field(default=None, ge=10, le=100)
    rev_len_min: Optional[int] = Field(default=None, ge=10, le=60)
    rev_len_max: Optional[int] = Field(default=None, ge=10, le=100)

    # Position rescue
    rescue_pool: list[str] = Field(default_factory=list)
    auto_relax: bool = Field(default=True)


class RetryFailedParams(BaseModel):
    mutation: str = ""
    fasta_path: str
    polymerase: str = "Benchling"
    target_start: int = Field(default=0, ge=0)
    # rescue may explore overlap lengths outside the design spec (le=40)
    overlap_len: Optional[int] = Field(default=None, ge=8, le=40)
    codon_strategy: str = "closest"
    organism: str = "ecoli"
    tm_fwd_target: float = Field(default=62.0, ge=20.0, le=80.0)
    tm_rev_target: float = Field(default=58.0, ge=20.0, le=80.0)
    tm_overlap_target: float = Field(default=42.0, ge=20.0, le=80.0)
    gc_min: float = Field(default=40.0, ge=0.0, le=100.0)
    gc_max: float = Field(default=60.0, ge=0.0, le=100.0)
    # None → resolved from polymerase profile
    fwd_len_min: Optional[int] = Field(default=None, ge=10, le=60)
    fwd_len_max: Optional[int] = Field(default=None, ge=10, le=100)
    rev_len_min: Optional[int] = Field(default=None, ge=10, le=60)
    rev_len_max: Optional[int] = Field(default=None, ge=10, le=100)
    tol_max: float = Field(default=3.0, ge=0.5, le=10.0)
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
    # evaluates user-provided primers (including legacy designs), so no le=18 cap
    overlap_len: int = Field(default=18, ge=8, le=40)


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
    mt_codon: Optional[str] = None


class ExportExcelParams(BaseModel):
    filepath: str
    mappings: Optional[list[PlateMappingItem]] = None
    dedup_info: Optional[dict[str, list[str]]] = None


class OrderResultItem(BaseModel):
    mutation: str
    forward_seq: str
    reverse_seq: str


class ExportOrderParams(BaseModel):
    filepath: str
    format: str = "idt"
    scale: str = "25nm"
    purification: str = "STD"
    results: Optional[list[OrderResultItem]] = None


class ExportMappingParams(BaseModel):
    filepath: str
    format: Literal["echo", "janus"] = "echo"
    transfer_vol: Optional[float] = None  # nL for echo, µL for janus; None = format default
    mappings: Optional[list[PlateMappingItem]] = None
    dedup_info: Optional[dict[str, list[str]]] = None


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


class BenchmarkResultDict(TypedDict, total=False):
    """Metrics returned by evaluate_selection() for a single strategy."""
    n_selected: int
    hit_rate: float
    mean_fitness: float
    unique_positions: int
    position_coverage: float
    domain_coverage: float
    structural_spread: float
    hits: int
    threshold: float
    n_trials: int


class ExportBenchmarkCsvParams(BaseModel):
    filepath: str
    results: dict[str, BenchmarkResultDict] = Field(default_factory=dict)


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


class FetchStructureParams(BaseModel):
    accession: str = ""


# ---------------------------------------------------------------------------
# misc.py handlers
# ---------------------------------------------------------------------------


class ExcludedRange(BaseModel):
    start: int
    end: int


class LoadEvolveproParams(BaseModel):
    filepath: str = ""
    top_n: int = Field(default=96, ge=0, le=960)
    max_per_position: int = Field(default=0, ge=0)
    domains: list[DomainEntry] = Field(default_factory=list)
    excluded_ranges: list[ExcludedRange] = Field(default_factory=list)
    domain_diversity: bool = False
    domain_strategy: str = "proportional"
    domain_overlap_policy: Literal["first", "largest"] = "first"
    linker_handling: Literal["include", "exclude", "separate-bin"] = "include"
    domain_quota_min: int = Field(default=1, ge=0, le=20)
    pareto_diversity: bool = False
    entropy_weight: float = Field(default=0.0, ge=0.0)
    pool_multiplier: float = Field(default=2.0, ge=1.0, le=10.0)
    distance_mode: Literal["auto", "1d", "3d"] = "auto"
    structure_accession: Optional[str] = None
    evolvepro_round: int = Field(default=0, ge=0)
    round_size: int = Field(default=96, ge=1, le=960)


class LandscapeEntry(BaseModel):
    variant: str
    fitness: float


class RunBenchmarkParams(BaseModel):
    landscape: list[LandscapeEntry] = Field(default_factory=list)
    ground_truth: dict[str, float] = Field(default_factory=dict)
    n_select: int = Field(default=95, ge=1, le=960)
    n_random_trials: int = Field(default=100, ge=1, le=1000)
    top_percentile: float = Field(default=10.0, gt=0.0, le=100.0)
    strategies: list[str] = Field(default_factory=lambda: ["topn", "random", "pareto_1d", "pareto_3d", "pareto_entropy"])
    domains: list[DomainEntry] = Field(default_factory=list)
    domain_strategy: str = "proportional"
    max_per_position: int = Field(default=1, ge=1)
    entropy_weight: float = Field(default=0.3, ge=0.0, le=1.0)
    pool_multiplier: float = Field(default=2.0, ge=1.0, le=10.0)
    distance_mode: Literal["auto", "1d", "3d"] = "auto"
    structure_accession: Optional[str] = None
    random_seed: Optional[int] = None
