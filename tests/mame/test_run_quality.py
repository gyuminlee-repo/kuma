"""Grading a run before its wells are read.

The fixtures are the three real runs that prompted this, so a change to the
thresholds has to argue with measured plates rather than with invented ones:

    02-12  FBF10847  1150 -> 975 pores  4777 reads per well
    07-29  FBF91250   343 -> 188 pores   515 reads per well
    08-04  FBF91250    40 ->  42 pores     4 reads per well   (cell re-used)

The first is the run that worked, the last is the run that produced a
ninety-six-well verdict table over nothing, and the middle one matters most: it
is the case a naive rule gets wrong. Its cell started at 343 pores, well under
the 800 warranty figure, and it still gave five hundred reads per well. A rule
that refuses a run on pore count alone would have thrown that plate away.
"""

from pathlib import Path

from kuma_core.mame.ingest.flow_cell import (
    FlowCellHistory,
    PoreScan,
    find_previous_use,
    read_flow_cell_history,
    read_ledger,
    record_use,
)
from kuma_core.mame.run_quality import (
    SEVERITY_BLOCKING,
    SEVERITY_WARNING,
    assess_run_quality,
    serialise_run_quality,
)

MIN_READS = 30


def _codes(quality) -> set[str]:
    return {f["code"] for f in quality.findings}


# ---------------------------------------------------------------------------
# Depth: the run-level verdict that decides whether the wells mean anything
# ---------------------------------------------------------------------------

def test_the_run_that_worked_says_nothing() -> None:
    """02-12. A clean run must produce no findings at all or the panel is noise.

    4777 reads per well clears both the ONT consensus-QC floor of 30 and the ONT
    recommendation of 1500, so there is nothing to report even though the cell
    lost pores over the run (1150 to 975), which is what a flow cell does.
    """
    quality = assess_run_quality(
        well_read_counts=[4777] * 96,
        min_read_count=MIN_READS,
        flow_cell_id="FBF10847",
        pore_start=1150,
        pore_end=975,
    )

    assert quality.findings == []
    assert quality.severity is None
    assert quality.depth_ok is True


def test_four_reads_a_well_is_blocking() -> None:
    """08-04. Nothing below this finding is worth reading."""
    quality = assess_run_quality(
        well_read_counts=[4] * 96,
        min_read_count=MIN_READS,
        flow_cell_id="FBF91250",
        pore_start=40,
        pore_end=42,
    )

    assert quality.severity == SEVERITY_BLOCKING
    assert "median_depth_below_floor" in _codes(quality)
    assert quality.median_well_reads == 4
    assert quality.wells_under_floor == 96
    assert quality.depth_ok is False


def test_a_weak_cell_that_still_delivered_is_not_blocked() -> None:
    """07-29. Scorable and under-powered, which is its own grade.

    515 reads per well clears the ONT consensus-QC floor of 30 and falls short
    of the ONT recommendation of 1500, so the run stands with a note about
    depth. The cell started at 343 pores, under the ONT warranty figure of 800,
    and that produces NO finding: a rule keyed on the warranty number would have
    called this plate bad, and it returned five hundred reads a well.
    """
    quality = assess_run_quality(
        well_read_counts=[515] * 96,
        min_read_count=MIN_READS,
        flow_cell_id="FBF91250",
        pore_start=343,
        pore_end=188,
    )

    assert quality.severity == SEVERITY_WARNING
    assert _codes(quality) == {"median_depth_below_recommended"}
    assert quality.depth_ok is True


def test_the_median_not_the_total_decides() -> None:
    """A plate whose reads all landed in two wells is not a deep plate.

    Total reads here are far above any floor, and the typical well has none.
    Grading on the sum would have called this run healthy.
    """
    counts = [50_000, 50_000] + [0] * 94

    quality = assess_run_quality(counts, min_read_count=MIN_READS)

    assert quality.median_well_reads == 0
    assert quality.severity == SEVERITY_BLOCKING


def test_an_unknown_depth_is_not_a_pass() -> None:
    """No reads and no floor leave the verdict undecided rather than clean."""
    quality = assess_run_quality([], min_read_count=None)

    assert quality.depth_ok is None
    assert quality.findings == []


# ---------------------------------------------------------------------------
# Pore counts, read from the file MinKNOW actually writes
# ---------------------------------------------------------------------------

def test_pore_counts_come_from_the_mux_scans(tmp_path: Path) -> None:
    """Shaped exactly like the FBF10847 report json this was measured against."""
    report = {
        "protocol_run_info": {
            "flow_cell": {
                "flow_cell_id": "FBF10847",
                "product_code": "FLO-MIN114",
                "channel_count": 512,
            }
        },
        "acquisitions": [
            {"acquisition_run_info": {"bream_info": {}}},
            {
                "acquisition_run_info": {
                    "bream_info": {
                        "mux_scan_results": [
                            {"mux_scan_timestamp": 211, "counts": {"single_pore": 1150}},
                            {"mux_scan_timestamp": 5819, "counts": {"single_pore": 1252}},
                            {"mux_scan_timestamp": 45047, "counts": {"single_pore": 975}},
                        ]
                    }
                }
            },
        ],
    }
    import json

    (tmp_path / "report_FBF10847_20260212_2231_x.json").write_text(
        json.dumps(report), encoding="utf-8"
    )

    history = read_flow_cell_history(tmp_path)

    assert history.flow_cell_id == "FBF10847"
    assert history.product_code == "FLO-MIN114"
    # First scan is the starting count, last is the ending count, and the peak
    # in between is neither: a max-based reading would report 1252.
    assert history.pore_start == 1150
    assert history.pore_end == 975
    assert len(history.scans) == 3


def test_a_folder_with_no_report_reads_empty_rather_than_zero(tmp_path: Path) -> None:
    """Zero pores and unknown pores must not be the same value."""
    history = read_flow_cell_history(tmp_path)

    assert history.scans == []
    assert history.pore_start is None
    assert history.flow_cell_id is None


def test_a_truncated_report_is_absorbed(tmp_path: Path) -> None:
    (tmp_path / "report_x.json").write_text('{"acquisitions": [', encoding="utf-8")

    assert read_flow_cell_history(tmp_path).scans == []


# ---------------------------------------------------------------------------
# Reuse: the same cell id in two run folders
# ---------------------------------------------------------------------------

def test_the_same_cell_in_a_second_folder_is_a_reuse(tmp_path: Path) -> None:
    """FBF91250 on 07-29 and again on 08-04."""
    first = FlowCellHistory(
        flow_cell_id="FBF91250",
        scans=[PoreScan(200, 343), PoreScan(40000, 188)],
    )
    record_use(tmp_path, first, run_dir="/runs/20260729_FBF91250", started="2026-07-29")

    ledger = read_ledger(tmp_path)
    previous = find_previous_use(ledger, "FBF91250", "/runs/20260804_FBF91250")

    assert previous is not None
    assert previous["pore_end"] == 188
    assert previous["run_dir"] == "/runs/20260729_FBF91250"


def test_analysing_one_folder_twice_is_not_a_reuse(tmp_path: Path) -> None:
    """Otherwise the warning fires on every repeat analysis until nobody reads it."""
    history = FlowCellHistory(flow_cell_id="FBF91250", scans=[PoreScan(200, 343)])
    record_use(tmp_path, history, run_dir="/runs/20260729", started="2026-07-29")
    record_use(tmp_path, history, run_dir="/runs/20260729", started="2026-07-29")

    ledger = read_ledger(tmp_path)

    assert len(ledger) == 1
    assert find_previous_use(ledger, "FBF91250", "/runs/20260729") is None


def test_a_reuse_is_reported_beside_the_pore_count(tmp_path: Path) -> None:
    """08-04 in full: shallow plate, weak cell, and a cell that had a prior run."""
    quality = assess_run_quality(
        well_read_counts=[4] * 96,
        min_read_count=MIN_READS,
        flow_cell_id="FBF91250",
        pore_start=40,
        pore_end=42,
        reused_from={"run_dir": "/runs/20260729", "pore_end": 188},
    )

    # Depth blocks and reuse is reported. The forty starting pores appear as a
    # number on the block, not as a finding.
    assert _codes(quality) == {"median_depth_below_floor", "flow_cell_reused"}
    assert quality.severity == SEVERITY_BLOCKING
    payload = serialise_run_quality(quality)
    assert payload["reused_from"]["pore_end"] == 188
    assert payload["pore_start"] == 40
    assert payload["severity"] == SEVERITY_BLOCKING
    # Every threshold on the block names where it came from, so 30 can never
    # again read as an arbitrary constant.
    thresholds = payload["thresholds"]
    assert thresholds["floor"]["value"] == MIN_READS
    assert "minimum_mean_depth" in thresholds["floor"]["source"]
    assert thresholds["recommended"]["value"] == 1500
    assert thresholds["pore_warranty"]["enforced"] is False
    assert "spectrum.02728-22" in thresholds["mixed_reference"]["source"]
    # The KIND of each source, which is the part that stops a workflow default
    # from being read as a vendor specification. The floor is a default borrowed
    # from a pipeline this app does not run, so it also carries `provisional`;
    # the target is prose that says "We recommend" and does not.
    assert thresholds["floor"]["kind"] == "vendor_default"
    assert thresholds["floor"]["provisional"] is True
    assert thresholds["recommended"]["kind"] == "vendor_recommendation"
    assert thresholds["recommended"]["provisional"] is False
    assert thresholds["mixed_reference"]["kind"] == "literature"


def test_a_ledger_that_cannot_be_read_is_empty_not_an_error(tmp_path: Path) -> None:
    (tmp_path / "mame_flowcells.json").write_text("not json", encoding="utf-8")

    assert read_ledger(tmp_path) == []
