"""Validation contract for the unified Step 3 request."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from sidecar_mame.models import BuildEvolveproInputParams


def _xlsx(path):
    import openpyxl

    openpyxl.Workbook().save(path)
    return str(path)


@pytest.fixture
def files(tmp_path):
    (tmp_path / "activity.csv").write_text("variant,value\n5F,1\n", encoding="utf-8")
    return {
        "activity": str(tmp_path / "activity.csv"),
        "gc": _xlsx(tmp_path / "gc.xlsx"),
        "round1": _xlsx(tmp_path / "round1.xlsx"),
        "verdict": _xlsx(tmp_path / "verdict.xlsx"),
        "layout": _xlsx(tmp_path / "layout.xlsx"),
        "out": str(tmp_path / "out.xlsx"),
    }


def test_accepts_each_single_supported_primary_source(files):
    for source, value in (
        ("activity_path", files["activity"]),
        ("gc_data_xlsx", files["gc"]),
        ("round1_report_xlsx", files["round1"]),
    ):
        if source == "activity_path":
            with open(value, "w", encoding="utf-8") as handle:
                handle.write("variant,value\n5F,1\n")
        params = {
            source: value,
            "verdict_xlsx": files["verdict"],
            "output_xlsx": files["out"],
        }
        if source != "activity_path":
            params["layout_xlsx"] = files["layout"]
        validated = BuildEvolveproInputParams.model_validate(params)
        assert getattr(validated, source) == value


@pytest.mark.parametrize("primary", [None, "two"])
def test_requires_exactly_one_primary_source(files, primary):
    params = {"verdict_xlsx": files["verdict"], "output_xlsx": files["out"]}
    if primary == "two":
        params.update(activity_path=files["activity"], gc_data_xlsx=files["gc"], layout_xlsx=files["layout"])
    with pytest.raises(ValidationError, match="exactly one primary source"):
        BuildEvolveproInputParams.model_validate(params)


@pytest.mark.parametrize("missing", ["verdict_xlsx", "output_xlsx"])
def test_verdict_and_output_are_required(files, missing):
    params = {"activity_path": files["activity"], "verdict_xlsx": files["verdict"], "output_xlsx": files["out"]}
    params.pop(missing)
    with pytest.raises(ValidationError):
        BuildEvolveproInputParams.model_validate(params)


@pytest.mark.parametrize("removed", ["rep_batch_xlsx", "prev_evolvepro_xlsx", "round1_evolvepro_xlsx", "round1_rep_batch_xlsx"])
def test_removed_prior_and_numeric_fields_are_forbidden_extras(files, removed):
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        BuildEvolveproInputParams.model_validate({
            "activity_path": files["activity"],
            "verdict_xlsx": files["verdict"],
            "output_xlsx": files["out"],
            removed: files["gc"],
        })


def test_numeric_sources_need_exactly_one_order_source(files):
    """A numeric sample name is a position, so something has to state the order.

    Both sources at once leaves the answer ambiguous, which is a different
    defect from having none and is refused the same way.
    """
    base = {"verdict_xlsx": files["verdict"], "output_xlsx": files["out"]}
    for numeric in ("numeric_report_xlsx", "remeasure_numeric_xlsx"):
        params = dict(base)
        if numeric == "remeasure_numeric_xlsx":
            params["gc_data_xlsx"] = files["gc"]
        params[numeric] = files["round1"]

        with pytest.raises(ValidationError, match="exactly one order source"):
            BuildEvolveproInputParams.model_validate(params)

        with pytest.raises(ValidationError, match="exactly one order source"):
            BuildEvolveproInputParams.model_validate({
                **params,
                "layout_xlsx": files["layout"],
                "expected_xlsx": files["layout"],
            })

        validated = BuildEvolveproInputParams.model_validate({
            **params, "layout_xlsx": files["layout"],
        })
        assert getattr(validated, numeric) == files["round1"]


def test_numeric_report_is_a_primary_source_of_its_own(files):
    validated = BuildEvolveproInputParams.model_validate({
        "numeric_report_xlsx": files["round1"],
        "expected_xlsx": files["layout"],
        "verdict_xlsx": files["verdict"],
        "output_xlsx": files["out"],
    })
    assert validated.numeric_report_xlsx == files["round1"]

    with pytest.raises(ValidationError, match="exactly one primary source"):
        BuildEvolveproInputParams.model_validate({
            "numeric_report_xlsx": files["round1"],
            "gc_data_xlsx": files["gc"],
            "layout_xlsx": files["layout"],
            "verdict_xlsx": files["verdict"],
            "output_xlsx": files["out"],
        })


def test_only_one_confirmation_source_is_accepted(files):
    with pytest.raises(ValidationError, match="at most one confirmation source"):
        BuildEvolveproInputParams.model_validate({
            "gc_data_xlsx": files["gc"],
            "layout_xlsx": files["layout"],
            "remeasure_report_xlsx": files["round1"],
            "remeasure_numeric_xlsx": files["round1"],
            "verdict_xlsx": files["verdict"],
            "output_xlsx": files["out"],
        })


def test_well_labeled_primary_sources_accept_a_missing_layout(files):
    """A layout file is one way to map wells, not the only one.

    The verdict workbook this request already requires names a mutant_id per
    well, so the builder derives the same mapping from it. Whether that mapping
    covers the measured wells is a data question the builder answers, so the
    request contract no longer refuses the combination up front.
    """
    for source in ("gc_data_xlsx", "round1_report_xlsx"):
        validated = BuildEvolveproInputParams.model_validate({
            source: files["gc"] if source == "gc_data_xlsx" else files["round1"],
            "verdict_xlsx": files["verdict"],
            "output_xlsx": files["out"],
        })
        assert validated.layout_xlsx is None
