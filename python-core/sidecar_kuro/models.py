"""Pydantic input-validation models for KURO sidecar JSON-RPC handlers.

All models use field names that match the exact keys the frontend sends
(verified from params.get() calls in each handler).  Pydantic v2
ValidationError is a subclass of ValueError, so the dispatcher's
``except (KeyError, ValueError)`` block catches it automatically — no
per-handler try/except is required.

Usage in handlers::

    from sidecar_kuro.models import DesignSdmPrimersParams
    p = DesignSdmPrimersParams(**params)
    # access as p.fasta_path, p.polymerase, etc.
"""

from typing import Annotated, Any, Literal, Optional

from typing_extensions import TypedDict

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator


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


class WorkspaceModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class SortingEntry(WorkspaceModel):
    id: str
    desc: bool


class OffTargetHitModel(WorkspaceModel):
    position: int
    strand: Literal["sense", "antisense"]
    match_seq: str
    tm: float
    match_length: int


class FailedMutationModel(WorkspaceModel):
    mutation: str
    rank: int
    reason: str


class RescuedMutationModel(WorkspaceModel):
    original: str
    rescued_by: str
    type: Literal["pool_cascade", "auto_relax"]
    penalty: Optional[float] = None
    tolerance_used: Optional[float] = None


class RescueStatsModel(WorkspaceModel):
    pool_cascade: int
    auto_relax: int
    positions_attempted: int
    pool_variants_tried: int


class DomainInfoModel(WorkspaceModel):
    name: str
    id: str
    start: int
    end: int
    db: str


class EvolveproStepStatsModel(WorkspaceModel):
    position_filter_removed: Optional[int] = None
    domain_selected: Optional[int] = None
    pareto_exchanges: Optional[int] = None


class BenchmarkResultModel(WorkspaceModel):
    n_selected: int
    hit_rate: float
    mean_fitness: float
    unique_positions: int
    position_coverage: float
    domain_coverage: float
    structural_spread: float
    hits: int
    threshold: float
    n_trials: Optional[int] = None


class SdmPrimerResultModel(WorkspaceModel):
    mutation: str
    aa_position: int
    codon_pos: int
    forward_seq: str
    reverse_seq: str
    fwd_len: int
    rev_len: int
    overlap_len: int
    candidate_count: Optional[int] = None
    candidate_fwd_count: Optional[int] = None
    candidate_rev_count: Optional[int] = None
    tm_no_fwd: float
    tm_no_rev: float
    tm_overlap: float
    tm_condition_met: bool
    tolerance_used: float
    tolerance_fwd: Optional[float] = None
    tolerance_rev: Optional[float] = None
    has_offtarget: bool
    offtarget_fwd: Optional[list[OffTargetHitModel]] = None
    offtarget_rev: Optional[list[OffTargetHitModel]] = None
    penalty: float
    gc_fwd: float
    gc_rev: float
    wt_codon: str
    mt_codon: str
    overlap_seq: str
    hairpin_tm_fwd: Optional[float] = None
    hairpin_tm_rev: Optional[float] = None
    homodimer_tm_fwd: Optional[float] = None
    homodimer_tm_rev: Optional[float] = None
    hairpin_dg_fwd: Optional[float] = None
    hairpin_dg_rev: Optional[float] = None
    homodimer_dg_fwd: Optional[float] = None
    homodimer_dg_rev: Optional[float] = None
    synthesis_score_fwd: Optional[float] = None
    synthesis_score_rev: Optional[float] = None
    warnings: list[str] = Field(default_factory=list)


class PolymeraseProfileModel(WorkspaceModel):
    name: str
    tm_method: str
    salt_correction: str
    opt_tm: float
    min_tm: float
    max_tm: float
    opt_size: int
    min_size: int
    max_size: int
    min_gc: float
    max_gc: float
    salt_monovalent: float
    salt_divalent: float
    dntp_conc: float
    dna_conc: float
    max_tm_diff: float
    opt_tm_fwd: Optional[float] = None
    opt_tm_rev: Optional[float] = None
    opt_tm_overlap: Optional[float] = None
    min_3prime_dist: Optional[int] = None
    overlap_len: Optional[int] = None
    fwd_len_min: Optional[int] = None
    fwd_len_max: Optional[int] = None
    rev_len_min: Optional[int] = None
    rev_len_max: Optional[int] = None


class AlternativesResultModel(WorkspaceModel):
    mutation: Optional[str] = None
    count: Optional[int] = None
    candidates: list[SdmPrimerResultModel] = Field(default_factory=list)


class DesignResultResponseModel(WorkspaceModel):
    results: list[SdmPrimerResultModel] = Field(default_factory=list)
    success_count: int
    total_count: int
    failed_mutations: list[FailedMutationModel] = Field(default_factory=list)
    rescue_stats: Optional[RescueStatsModel] = None
    rescued_mutations: Optional[list[RescuedMutationModel]] = None
    cancelled: Optional[bool] = None


class FileExportResultModel(WorkspaceModel):
    success: Literal[True] = True
    filepath: str


class ExportOrderResultModel(FileExportResultModel):
    format: Literal["idt", "twist"]
    primer_count: int


class ExportMappingResultModel(FileExportResultModel):
    format: Literal["echo", "janus"]
    primer_count: int


class SaveCustomPolymeraseResultModel(WorkspaceModel):
    success: Literal[True] = True
    name: str


class WorkspaceInputsModel(WorkspaceModel):
    fastaPath: str
    mutationInputMode: Literal["text", "evolvepro", "multi-evolve"]
    mutationText: str
    evolveproCsvPath: str
    selectedGene: str


class WorkspaceSettingsModel(WorkspaceModel):
    selectedPolymerase: Optional[str] = None
    codonStrategy: Literal["closest", "optimal"]
    maxPrimers: int
    tmFwdTarget: float
    tmRevTarget: float
    tmOverlapTarget: float
    gcMin: float
    gcMax: float
    primerLenEnabled: Optional[bool] = None
    fwdLenMin: Optional[int] = None
    fwdLenMax: Optional[int] = None
    revLenMin: Optional[int] = None
    revLenMax: Optional[int] = None
    fillOnFailure: Optional[bool] = None
    uniprotAccession: Optional[str] = None
    domains: Optional[list[DomainInfoModel]] = None
    domainDiversityEnabled: Optional[bool] = None
    domainStrategy: Optional[Literal["proportional", "equal"]] = None
    domainOverlapPolicy: Optional[Literal["first", "largest"]] = None
    linkerHandling: Optional[Literal["include", "exclude", "separate-bin"]] = None
    domainQuotaMin: Optional[int] = None
    paretoDiversityEnabled: Optional[bool] = None
    disabledDomains: Optional[list[str]] = None
    rescuedMutations: Optional[list[str]] = None
    entropyWeightEnabled: Optional[bool] = None
    entropyWeight: Optional[float] = None
    paretoPoolMultiplier: Optional[float] = None
    distanceMode: Optional[Literal["auto", "1d", "3d"]] = None
    benchmarkTopPercentile: Optional[float] = None
    benchmarkRandomTrials: Optional[int] = None
    benchmarkRandomSeed: Optional[int] = None
    autoRedesignOnLoad: Optional[bool] = None
    saveCache: Optional[bool] = None
    organism: Optional[str] = None
    pipelineMode: Optional[bool] = None
    positionDiversityEnabled: Optional[bool] = None
    maxPerPosition: Optional[int] = None
    evolveproRound: Optional[int] = None
    roundSize: Optional[int] = None


class WorkspaceResultsModel(WorkspaceModel):
    designResults: list[SdmPrimerResultModel]
    successCount: int
    totalCount: int
    failedMutations: list[FailedMutationModel]
    plateMappings: list[PlateMappingItem]
    dedupInfo: dict[str, list[str]]
    manuallySwapped: dict[str, Literal["fwd", "rev", "both"]]
    customCandidates: dict[str, list[SdmPrimerResultModel]]


class WorkspaceUiModel(WorkspaceModel):
    tableSorting: list[SortingEntry]


class WorkspaceCacheModel(WorkspaceModel):
    evolveproTotalCount: Optional[int] = None
    evolveproFilteredCount: Optional[int] = None
    evolveproParetoExchanges: Optional[int] = None
    evolveproStepStats: Optional[EvolveproStepStatsModel] = None
    benchmarkResults: Optional[dict[str, BenchmarkResultModel]] = None


class WorkspaceV1Data(WorkspaceModel):
    version: Literal[1]
    fastaPath: str
    mutationInputMode: Literal["text", "evolvepro", "multi-evolve"]
    mutationText: str
    evolveproCsvPath: str
    selectedGene: str
    codonStrategy: Literal["closest", "optimal"]
    maxPrimers: int
    designResults: list[SdmPrimerResultModel]
    successCount: int
    totalCount: int
    failedMutations: list[FailedMutationModel]
    plateMappings: list[PlateMappingItem]
    dedupInfo: dict[str, list[str]]
    tableSorting: list[SortingEntry]
    manuallySwapped: dict[str, Literal["fwd", "rev", "both"]]
    customCandidates: dict[str, list[SdmPrimerResultModel]]
    tmFwdTarget: float
    tmRevTarget: float
    tmOverlapTarget: float
    gcMin: float
    gcMax: float
    primerLenEnabled: Optional[bool] = None
    fwdLenMin: Optional[int] = None
    fwdLenMax: Optional[int] = None
    revLenMin: Optional[int] = None
    revLenMax: Optional[int] = None
    fillOnFailure: Optional[bool] = None
    uniprotAccession: Optional[str] = None
    domains: Optional[list[DomainInfoModel]] = None
    domainDiversityEnabled: Optional[bool] = None
    domainStrategy: Optional[Literal["proportional", "equal"]] = None
    paretoDiversityEnabled: Optional[bool] = None
    disabledDomains: Optional[list[str]] = None
    rescuedMutations: Optional[list[str]] = None
    entropyWeightEnabled: Optional[bool] = None
    entropyWeight: Optional[float] = None
    organism: Optional[str] = None
    pipelineMode: Optional[bool] = None
    positionDiversityEnabled: Optional[bool] = None
    maxPerPosition: Optional[int] = None
    evolveproRound: Optional[int] = None
    roundSize: Optional[int] = None
    evolveproTotalCount: Optional[int] = None
    evolveproFilteredCount: Optional[int] = None
    evolveproParetoExchanges: Optional[int] = None
    evolveproStepStats: Optional[EvolveproStepStatsModel] = None


class WorkspaceV2Data(WorkspaceModel):
    version: Literal[2]
    inputs: WorkspaceInputsModel
    settings: WorkspaceSettingsModel
    results: WorkspaceResultsModel
    ui: WorkspaceUiModel
    cache: Optional[WorkspaceCacheModel] = None


WorkspaceDataModel = Annotated[WorkspaceV1Data | WorkspaceV2Data, Field(discriminator="version")]
_WORKSPACE_DATA_ADAPTER = TypeAdapter(WorkspaceDataModel)


def validate_workspace_data(data: Any) -> WorkspaceV1Data | WorkspaceV2Data:
    """Validate versioned workspace payloads against the sidecar contract."""
    return _WORKSPACE_DATA_ADAPTER.validate_python(data)


class ExportExcelParams(BaseModel):
    filepath: str
    mappings: Optional[list[PlateMappingItem]] = None
    dedup_info: Optional[dict[str, list[str]]] = None
    project_id: Optional[str] = None
    kuma_version: Optional[str] = None


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
        validate_workspace_data(v)
        serialized = _json.dumps(v, default=str)
        if len(serialized) > 50 * 1024 * 1024:  # 50MB
            raise ValueError("Workspace data exceeds 50MB limit")
        return v


class SaveJsonParams(BaseModel):
    filepath: str
    data: Any

    @field_validator("data", mode="before")
    @classmethod
    def check_data_size(cls, v):
        import json as _json
        serialized = _json.dumps(v, default=str)
        if len(serialized) > 50 * 1024 * 1024:  # 50MB
            raise ValueError("JSON data exceeds 50MB limit")
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


class CheckStructuresParams(BaseModel):
    accessions: list[str] = Field(default_factory=list, max_length=20)


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
    top_n: int = Field(default=96, ge=0, le=10000)
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
    round_size: int = Field(default=96, ge=1, le=10000)


class LandscapeEntry(BaseModel):
    variant: str
    fitness: float


class RunBenchmarkParams(BaseModel):
    landscape: list[LandscapeEntry] = Field(default_factory=list)
    ground_truth: dict[str, float] = Field(default_factory=dict)
    n_select: int = Field(default=95, ge=1, le=10000)
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
