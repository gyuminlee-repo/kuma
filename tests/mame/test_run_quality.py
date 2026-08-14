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

import pytest

from kuma_core.mame.ingest.flow_cell import (
    FlowCellHistory,
    PoreScan,
    find_previous_use,
    read_flow_cell_history,
    read_ledger,
    record_use,
)
from kuma_core.mame.compare.verdict import (
    MIXED_FACTOR_ASSUMED_POSITIONS,
    _MIXED_CONFIDENT_DEPTH_FACTOR,
)
from kuma_core.mame.run_quality import (
    REFERENCE_EDGE_MARGIN_BP,
    SEVERITY_BLOCKING,
    SEVERITY_WARNING,
    assess_run_quality,
    serialise_run_quality,
    variants_near_reference_edge,
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


# ---------------------------------------------------------------------------
# Mutations against a reference end, on a reference used unmodified
#
# 260729 ispS. R560 is codon 560 of a 1683 bp CDS, so it sits 4 bp from the end.
# An aligner clips a read at a terminal mismatch it cannot attach, so against a
# bare CDS those positions are covered by a fraction of the reads the well
# reports. This is advisory: the wells on that run still scored.
# ---------------------------------------------------------------------------

ISPS_CDS_LENGTH = 1683


def test_a_mutation_against_the_reference_end_is_named() -> None:
    assert variants_near_reference_edge(
        {"R560D": 560, "R560N": 560}, 0, ISPS_CDS_LENGTH
    ) == ["R560D", "R560N"]


def test_a_mutation_in_the_middle_is_not_named() -> None:
    """A223 sits 1000 bp from either end and no clipping reaches it."""
    assert variants_near_reference_edge({"A223V": 223}, 0, ISPS_CDS_LENGTH) == []


def test_the_first_codon_counts_as_an_edge_too() -> None:
    """Both ends clip. The 5' end is not a special case, it is the same case."""
    assert variants_near_reference_edge({"M1V": 1}, 0, ISPS_CDS_LENGTH) == ["M1V"]


def test_a_flank_wider_than_the_margin_puts_the_mutation_inside() -> None:
    """Geometry alone clears the last codon once the flank exceeds the margin.

    Worth stating what this does NOT prove. The real 260729 amplicon is 1715 bp
    around a 1683 bp CDS, so it carries about 16 bp of flank each side, which is
    UNDER the 30 bp margin: that run's geometry does not clear this test. What
    keeps the notice off an extracted run is the extraction flag, checked in
    ``test_the_warning_needs_both_halves``, not the arithmetic here.
    """
    cds_start = REFERENCE_EDGE_MARGIN_BP + 1
    amplicon_length = cds_start + ISPS_CDS_LENGTH + REFERENCE_EDGE_MARGIN_BP + 1

    assert (
        variants_near_reference_edge({"R560D": 560}, cds_start, amplicon_length) == []
    )


def test_the_warning_needs_both_halves() -> None:
    """An extracted reference is silent even when a mutation is terminal.

    Guards the half of the condition that is easy to drop: without it every run
    on a CDS-length amplicon would carry the notice, and a notice that is always
    on is furniture.
    """
    quality = assess_run_quality(
        well_read_counts=[4777] * 96,
        min_read_count=MIN_READS,
        amplicon_extracted=True,
        edge_variants=["R560D"],
    )

    assert quality.findings == []
    assert quality.severity is None


def test_an_unmodified_reference_with_edge_variants_warns() -> None:
    quality = assess_run_quality(
        well_read_counts=[4777] * 96,
        min_read_count=MIN_READS,
        amplicon_extracted=False,
        edge_variants=["R560D", "R560N"],
    )

    assert _codes(quality) == {"variants_at_reference_edge"}
    # A WARNING and never blocking: on the run this came from, these wells
    # scored. Calling it blocking would throw away a usable plate.
    assert quality.severity == SEVERITY_WARNING
    finding = quality.findings[0]
    assert finding["variants"] == ["R560D", "R560N"]
    assert finding["margin_bp"] == REFERENCE_EDGE_MARGIN_BP


def test_the_edge_margin_is_carried_with_its_source() -> None:
    """Ours and provisional, stated as such, like every other threshold here."""
    payload = serialise_run_quality(
        assess_run_quality(
            well_read_counts=[4777] * 96,
            min_read_count=MIN_READS,
            amplicon_extracted=False,
            edge_variants=["R560D"],
        )
    )

    assert payload["edge_variants"] == ["R560D"]
    assert payload["edge_margin_bp"] == REFERENCE_EDGE_MARGIN_BP
    edge = payload["thresholds"]["reference_edge"]
    assert edge["kind"] == "self_set"
    assert edge["provisional"] is True
    assert edge["enforced"] is False


# ---------------------------------------------------------------------------
# The amplicon length the MIXED depth factor was derived against
# ---------------------------------------------------------------------------
#
# ``_MIXED_CONFIDENT_DEPTH_FACTOR`` multiplies a per-position binomial tail by
# 1500 positions per amplicon to get its "falsely mixed positions per well"
# column. The classifier reads neither a reference length nor a position count,
# so the premise went unchecked on every run. These pin that it is now measured
# and reported, and that measuring it changes no verdict.


def test_a_short_amplicon_is_named_against_the_assumed_1500_positions() -> None:
    """500 eligible positions is a third of the derivation: say so.

    A third of the positions is a third of the trials, so the expected count of
    falsely mixed positions per well is a third of the table the factor was read
    off. That does not make the factor wrong, and this does not touch it. It
    makes the number a reader has to know, and until now nothing said it.
    """
    quality = assess_run_quality(
        well_read_counts=[4777] * 96,
        min_read_count=MIN_READS,
        well_eligible_positions=[500] * 96,
    )

    assert "mixed_depth_factor_amplicon_scale" in _codes(quality)
    finding = next(
        f for f in quality.findings if f["code"] == "mixed_depth_factor_amplicon_scale"
    )
    assert finding["severity"] == SEVERITY_WARNING
    assert finding["positions"] == 500
    assert finding["assumed_positions"] == MIXED_FACTOR_ASSUMED_POSITIONS
    assert finding["positions_basis"] == "measured_eligible_positions"
    # The ratio itself is the report. The band that decided to print it is
    # arbitrary and says so.
    assert finding["ratio"] == pytest.approx(500 / 1500, abs=1e-3)
    assert finding["provisional"] is True
    assert finding["enforced"] is False
    # The gate is untouched: the factor is carried for the reader, not changed.
    assert finding["factor"] == _MIXED_CONFIDENT_DEPTH_FACTOR


def test_an_amplicon_near_the_assumed_length_says_nothing() -> None:
    """A run at the derivation's own scale must not add a warning.

    ``RunQuality.severity`` is WARNING whenever any finding exists, so an
    always-emitted scale line would flip every healthy run to a rendered notice.
    """
    quality = assess_run_quality(
        well_read_counts=[4777] * 96,
        min_read_count=MIN_READS,
        well_eligible_positions=[1400] * 96,
    )

    assert quality.findings == []


def test_zero_eligible_positions_falls_back_to_the_reference_length() -> None:
    """0 means the well never measured it, not a zero-length amplicon.

    Legacy consensus files default the field to 0 (``fasta_parser``), so a run
    made entirely of them has nothing measured and the reference length stands
    in, flagged as the approximation it is.
    """
    quality = assess_run_quality(
        well_read_counts=[4777] * 96,
        min_read_count=MIN_READS,
        well_eligible_positions=[0] * 96,
        reference_length=400,
    )

    finding = next(
        f for f in quality.findings if f["code"] == "mixed_depth_factor_amplicon_scale"
    )
    assert finding["positions"] == 400
    assert finding["positions_basis"] == "reference_length"


def test_nothing_measured_and_no_reference_length_reports_nothing() -> None:
    """Silence over a guess: an unmeasured premise is not a violated one."""
    quality = assess_run_quality(
        well_read_counts=[4777] * 96,
        min_read_count=MIN_READS,
        well_eligible_positions=[0] * 96,
    )

    assert quality.findings == []
