"""Regression coverage for the single supported Step 3 builder surface."""
from __future__ import annotations

import inspect

from kuma_core.mame import activity
from kuma_core.mame.activity.build_evolvepro_input import build_evolvepro_input


def test_public_activity_api_exposes_only_the_unified_builder():
    assert activity.build_evolvepro_input is build_evolvepro_input
    for symbol in (
        "BuildEvolveproReportsResult",
        "IdVariantMapping",
        "MappingRow",
        "build_evolvepro_input_axes",
        "build_evolvepro_input_from_reports",
        "build_id_variant_mapping",
    ):
        assert symbol not in activity.__all__
        assert not hasattr(activity, symbol)


def test_unified_builder_signature_has_no_rank_or_prior_input():
    parameters = inspect.signature(build_evolvepro_input).parameters
    assert {"activity_path", "gc_data_xlsx", "round1_report_xlsx"} <= parameters.keys()
    assert "verdict_xlsx" in parameters
    assert not {
        "rep_batch_xlsx",
        "rank_evolvepro_xlsx",
        "prev_evolvepro_xlsx",
        "round1_evolvepro_xlsx",
    } & parameters.keys()
