"""Regression coverage for removal of the legacy reports/rank Step 3 API."""
from __future__ import annotations

import importlib


build_module = importlib.import_module("kuma_core.mame.activity.build_evolvepro_input")


def test_legacy_reports_and_rank_entry_points_are_removed():
    for symbol in (
        "build_evolvepro_input_from_reports",
        "build_id_variant_mapping",
        "_build_fallback_from_prev_evolvepro",
        "_build_fallback_from_raw_report",
    ):
        assert not hasattr(build_module, symbol)
