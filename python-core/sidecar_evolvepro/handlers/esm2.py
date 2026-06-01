"""ESM2 RAM-budget recommendation JSON-RPC handler.

Ported from evolvepro-gui/python-core/sidecar/handlers.py.
"""
from __future__ import annotations

from typing import Any

from sidecar_evolvepro.models import Esm2RecommendationResponse

from kuma_core.shared import system_info


def handle_esm2_recommend(params: dict[str, Any]) -> dict[str, Any]:  # noqa: ARG001
    """Return cross-platform ESM2 RAM budget recommendations."""
    return Esm2RecommendationResponse(**system_info.recommend_esm2_model()).model_dump()


__all__ = ["handle_esm2_recommend"]
