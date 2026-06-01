"""Pydantic models for evolvepro-gui sidecar JSON-RPC."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

ESM2_MODEL_IDS = (
    "esm2_t6_8M_UR50D",
    "esm2_t12_35M_UR50D",
    "esm2_t30_150M_UR50D",
    "esm2_t33_650M_UR50D",
    "esm2_t36_3B_UR50D",
    "esm2_t48_15B_UR50D",
)

Esm2ModelId = Literal[
    "esm2_t6_8M_UR50D",
    "esm2_t12_35M_UR50D",
    "esm2_t30_150M_UR50D",
    "esm2_t33_650M_UR50D",
    "esm2_t36_3B_UR50D",
    "esm2_t48_15B_UR50D",
]


class EvolveProDetectResponse(BaseModel):
    """Response body for evolvepro_detect RPC."""

    env_found: bool
    env_path: Optional[str] = None
    evolvepro_version: Optional[str] = None
    weights_cached: bool = False
    weights_path: Optional[str] = None
    cached_models: dict[str, str] = Field(default_factory=dict)


class Esm2ModelRecommendation(BaseModel):
    """RAM gate for a single ESM2 model."""

    model_id: str
    label: str
    size_label: str
    min_ram_gb: int
    recommended_ram_gb: int
    download_url: str
    # Approximate file size in bytes (fair-esm official).
    # Actual download should verify via Content-Length header.
    expected_bytes: int
    status: Literal["safe", "caution", "blocked", "unknown"]
    reason: str


class Esm2RecommendationResponse(BaseModel):
    """Cross-platform ESM2 model recommendation response."""

    os: str
    arch: str
    ram_gb: Optional[float] = None
    disk_free_gb: Optional[float] = None
    recommended_model_id: Optional[str] = None
    recommended_label: Optional[str] = None
    models: list[Esm2ModelRecommendation] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class EvolveProRunRequest(BaseModel):
    """Request body for evolvepro_run RPC."""

    input_csv: str = Field(min_length=1)
    round_files: list[str] = Field(default_factory=list)
    wt_sequence: str = Field(default="", max_length=4000)
    wt_fasta: Optional[str] = None
    n_rounds: int = Field(ge=1, le=10)
    output_dir: str = Field(min_length=1)
    top_n: int = Field(ge=0, default=20)
    env_name: str = Field(default="evolvepro", min_length=1, max_length=64)
    esm2_model_id: Esm2ModelId


class EvolveProRunStartResponse(BaseModel):
    """Response body for evolvepro_run RPC (returned immediately on spawn)."""

    run_id: str


class EvolveProRunProgress(BaseModel):
    """Progress notification payload streamed during evolvepro_run."""

    run_id: str
    stage: Literal["detect", "loading", "scoring", "selecting", "done", "error"]
    current: int = Field(ge=0)
    total: int = Field(ge=0)
    message: str = ""


class EvolveProRunResult(BaseModel):
    """Terminal result payload for an EVOLVEpro run."""

    run_id: str
    output_csv: str
    top_variants: list[str] = Field(default_factory=list)
    elapsed_sec: float = Field(ge=0)


class EvolveProCancelRequest(BaseModel):
    """Request body for evolvepro_cancel RPC."""

    run_id: str = Field(min_length=1)


class CondaStatusResponse(BaseModel):
    """Response body for conda.detect RPC."""

    installed: bool
    conda_exe: Optional[str] = None
    version: Optional[str] = None


class EnvStatusResponse(BaseModel):
    """Response body for conda.detect_env RPC."""

    exists: bool
    env_path: Optional[str] = None
    packages: dict[str, Optional[str]] = Field(default_factory=dict)


class CondaVerifyResponse(BaseModel):
    """Response body for conda.verify_env RPC."""

    ok: bool
    error: Optional[str] = None


class CondaCreateEnvResponse(BaseModel):
    """Response body for conda.create_env RPC (returned after streaming completes)."""

    ok: bool
    error: Optional[str] = None
