# ruff: noqa: S101
"""What ``kuma_core.mame.qc.contamination`` reads out of the demux matrix.

Every fixture below is built so that a plausible wrong implementation gives a
DIFFERENT answer from the right one, which is the only thing that makes a
passing test evidence:

- Geometry: the tokens are ``2_3`` and ``8_1``, never ``r == f``. Both readings
  of the axis produce a valid well label (``B3``/``C2`` and ``H1``/``A8``), so
  the label is the discriminator. A diagonal token would agree with both.
- Buckets: an implementation that sums "reads outside the occupancy" into one
  number passes nothing here, because the two buckets are asserted separately
  and each has a fixture where the other is empty.
- Zero: ``unexpected_well_reads`` has a fixture whose answer is a specific
  non-zero count, so "always return 0" fails.
- Replicates: the shared and single-replicate leaks carry the SAME total, so an
  implementation reading only the sum labels them identically.
"""

from __future__ import annotations

import pytest

from kuma_core.mame.plate_geometry import (
    DEFAULT_ADDRESSING,
    PLATE_CAPACITY,
    seq_to_well,
)
from kuma_core.mame.qc.contamination import (
    POOLED_PLATE_NAME,
    SHARING_SHARED,
    SHARING_SINGLE,
    analyze_contamination,
)

_STAT_KEYS = (
    "total_reads",
    "passed_mapq",
    "passed_coverage",
    "assigned_reads",
    "ambiguous_dropped",
    "chimera_splits",
    "wells_with_reads",
    "wells_with_min_reads",
)


def _plate(name: str, counts: dict[str, int], **stats: int) -> dict:
    """One entry of the ``per_nb_out`` sink ``ingest_run_folder`` fills."""
    return {
        "nb_name": name,
        "sort_barcode_name": name,
        "stats": {key: int(stats.get(key, 0)) for key in _STAT_KEYS},
        "per_well_read_counts": dict(counts),
    }


def _wells(rows: range, cols: range) -> list[str]:
    return [
        seq_to_well(DEFAULT_ADDRESSING.rc_to_seq(row, col))
        for col in cols
        for row in rows
    ]


def _checkerboard() -> list[str]:
    """48 wells that between them use every reverse AND every forward index.

    A block of whole columns would not: occupying A1..H6 uses six forward
    indices and every combination of them, which leaves no unoccupied
    combination for the ``unexpected_well_reads`` fixture to inject into.
    """
    return [
        seq_to_well(DEFAULT_ADDRESSING.rc_to_seq(row, col))
        for col in range(1, 13)
        for row in range(1, 9)
        if (row + col) % 2 == 0
    ]


def _signal(report: dict, name: str) -> dict:
    return report["signals"][name]


# ---------------------------------------------------------------------------
# Geometry comes from plate_geometry, not from a local sum
# ---------------------------------------------------------------------------


def test_stray_wells_are_named_by_the_plate_geometry_convention() -> None:
    """``2_3`` is B3 and ``8_1`` is H1, not C2 and A8.

    The occupancy deliberately holds C2 and A8. Under the transposed reading of
    ``{R}_{F}`` both injected tokens would land ON an occupied well and no stray
    would be reported at all, so this fails loudly rather than mislabelling.
    """
    report = analyze_contamination(
        [_plate("sort_barcode01", {"2_3": 30, "8_1": 40})],
        ["C2", "A8"],
        occupancy_source="inferred_draft_layout",
    )

    unused = _signal(report, "unused_index_reads")
    assert unused["state"] == "ok"
    assert unused["value"] == 70
    assert [w["well"] for w in unused["wells"]] == ["B03", "H01"]


# ---------------------------------------------------------------------------
# The two buckets are separate
# ---------------------------------------------------------------------------


def test_a_read_on_an_unused_index_is_not_a_read_on_an_unexpected_well() -> None:
    """F=1..6 occupied, 30 reads on ``1_9``: 30 unused-index, 0 unexpected-well.

    An implementation that adds the two buckets together reports 30 for both.
    """
    report = analyze_contamination(
        [_plate("sort_barcode01", {"1_9": 30})],
        _wells(range(1, 9), range(1, 7)),
        occupancy_source="inferred_draft_layout",
    )

    assert _signal(report, "unused_index_reads")["value"] == 30
    unexpected = _signal(report, "unexpected_well_reads")
    assert unexpected["state"] == "ok"
    assert unexpected["value"] == 0


def test_unexpected_well_reads_counts_the_unoccupied_combinations_exactly() -> None:
    """48 occupied wells, reads on two unoccupied combinations of used indices.

    Both ``2_3`` (B3) and ``4_5`` (D5) carry a reverse and a forward index this
    campaign uses elsewhere, so neither can be dismissed as a foreign barcode.
    The expected answer is a specific non-zero count, which is what an
    "always 0" implementation fails.
    """
    report = analyze_contamination(
        [_plate("sort_barcode01", {"2_3": 77, "4_5": 23})],
        _checkerboard(),
        occupancy_source="inferred_draft_layout",
    )

    unexpected = _signal(report, "unexpected_well_reads")
    assert unexpected["state"] == "ok"
    assert unexpected["value"] == 100
    assert [w["well"] for w in unexpected["wells"]] == ["B03", "D05"]
    # The same occupancy uses all 8 reverse and all 12 forward indices, so the
    # other bucket has no room and says so rather than reporting 0.
    assert _signal(report, "unused_index_reads")["state"] == "unavailable"


# ---------------------------------------------------------------------------
# No silent skip: a full plate says the question cannot be asked
# ---------------------------------------------------------------------------


def test_a_full_plate_reports_unexpected_well_reads_as_unavailable() -> None:
    """96 wells occupied: the item EXISTS, is unavailable, and carries no value.

    A missing key and a reported 0 are both failures. The first is the silent
    skip this module was written to remove; the second claims a clean plate on
    a question that could not be asked.
    """
    full = [seq_to_well(seq) for seq in range(1, PLATE_CAPACITY + 1)]
    report = analyze_contamination(
        [_plate("sort_barcode01", {"1_1": 500, "2_3": 400})],
        full,
        occupancy_source="explicit_well_layout",
    )

    assert "unexpected_well_reads" in report["signals"]
    unexpected = _signal(report, "unexpected_well_reads")
    assert unexpected["state"] == "unavailable"
    assert unexpected["reason"]
    assert "value" not in unexpected


# ---------------------------------------------------------------------------
# Replicate scope
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("per_replicate", "expected_label"),
    [
        ((400, 410, 395), SHARING_SHARED),
        ((1205, 0, 0), SHARING_SINGLE),
    ],
)
def test_leak_sharing_reads_the_matrix_per_replicate_not_the_total(
    per_replicate: tuple[int, int, int], expected_label: str
) -> None:
    """1205 stray reads either repeat across the copies or sit in one of them.

    Both fixtures carry the same total on purpose: an implementation that sums
    the row before looking at it cannot tell them apart, and labels both the
    same way.
    """
    plates = [
        _plate(f"sort_barcode0{i + 1}", {"2_3": n})
        for i, n in enumerate(per_replicate)
    ]
    report = analyze_contamination(
        plates, _checkerboard(), occupancy_source="inferred_draft_layout"
    )

    sharing = _signal(report, "leak_well_sharing")
    assert sharing["state"] == "ok"
    assert sharing["label"] == expected_label
    assert sharing["wells"][0]["well"] == "B03"
    assert sharing["wells"][0]["reads"] == sum(per_replicate)


def test_plate_yield_skew_is_the_smallest_copy_over_the_largest() -> None:
    plates = [
        _plate("sort_barcode01", {"1_1": 10}, assigned_reads=1000),
        _plate("sort_barcode02", {"1_1": 10}, assigned_reads=500),
        _plate("sort_barcode03", {"1_1": 10}, assigned_reads=250),
    ]
    report = analyze_contamination(
        plates, _checkerboard(), occupancy_source="inferred_draft_layout"
    )

    skew = _signal(report, "plate_yield_skew")
    assert skew["state"] == "ok"
    assert skew["value"] == pytest.approx(0.25)
    assert [p["assigned_reads"] for p in skew["per_replicate"]] == [1000, 500, 250]


def test_a_single_pool_has_no_replicate_scope_but_keeps_the_well_scope() -> None:
    """Pooled runs answer the well questions and refuse the replicate ones."""
    report = analyze_contamination(
        [
            _plate(
                POOLED_PLATE_NAME,
                {"1_9": 30, "2_3": 12},
                passed_coverage=200,
                assigned_reads=180,
                ambiguous_dropped=20,
                chimera_splits=9,
            )
        ],
        _checkerboard(),
        occupancy_source="inferred_draft_layout",
    )

    assert report["replicates"] == 0
    for name in ("leak_well_sharing", "plate_yield_skew"):
        signal = _signal(report, name)
        assert signal["state"] == "unavailable"
        assert "pooled" in signal["reason"]
    # The well-scoped and rate-scoped answers are unaffected: one plate is still
    # a plate, and the gate counters are still counted.
    assert _signal(report, "unexpected_well_reads")["value"] == 12
    assert _signal(report, "ambiguity_rate")["state"] == "ok"
    assert _signal(report, "chimera_rate")["state"] == "ok"


# ---------------------------------------------------------------------------
# Rates and their denominators
# ---------------------------------------------------------------------------


def test_ambiguity_rate_is_dropped_reads_over_reads_that_reached_matching() -> None:
    report = analyze_contamination(
        [
            _plate(
                "sort_barcode01",
                {"1_1": 10},
                total_reads=1000,
                passed_mapq=400,
                passed_coverage=200,
                ambiguous_dropped=50,
            )
        ],
        _checkerboard(),
        occupancy_source="inferred_draft_layout",
    )

    rate = _signal(report, "ambiguity_rate")
    assert rate["state"] == "ok"
    # 50 / 200, NOT 50 / 1000 and not 50 / 400: only the reads that cleared
    # coverage ever reached barcode matching.
    assert rate["value"] == pytest.approx(0.25)
    assert rate["passed_coverage"] == 200


def test_ambiguity_rate_is_unavailable_when_nothing_cleared_coverage() -> None:
    """A zero denominator is a reason, never an exception and never a 0.0."""
    report = analyze_contamination(
        [_plate("sort_barcode01", {}, total_reads=4321, passed_mapq=0, passed_coverage=0)],
        _checkerboard(),
        occupancy_source="inferred_draft_layout",
    )

    rate = _signal(report, "ambiguity_rate")
    assert rate["state"] == "unavailable"
    assert rate["reason"]
    assert "value" not in rate


def test_chimera_rate_is_splits_over_the_demux_assigned_reads() -> None:
    """The denominator is ``DemuxStats.assigned_reads``, stated in the payload."""
    report = analyze_contamination(
        [_plate("sort_barcode01", {"1_1": 10}, assigned_reads=300, chimera_splits=12)],
        _checkerboard(),
        occupancy_source="inferred_draft_layout",
    )

    rate = _signal(report, "chimera_rate")
    assert rate["state"] == "ok"
    assert rate["value"] == pytest.approx(0.04)
    assert rate["assigned_reads"] == 300
    assert rate["chimera_splits"] == 12


def test_chimera_rate_is_unavailable_when_no_read_was_assigned() -> None:
    report = analyze_contamination(
        [_plate("sort_barcode01", {}, chimera_splits=0)],
        _checkerboard(),
        occupancy_source="inferred_draft_layout",
    )

    assert _signal(report, "chimera_rate")["state"] == "unavailable"


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


def test_the_occupancy_source_is_carried_verbatim() -> None:
    """Every signal is measured against the occupancy, so its origin rides along."""
    report = analyze_contamination(
        [_plate("sort_barcode01", {"1_1": 5})],
        _checkerboard(),
        occupancy_source="explicit_well_layout",
    )

    assert report["occupancy_source"] == "explicit_well_layout"
    assert report["occupied_wells"] == 48
    assert report["plate_names"] == ["sort_barcode01"]
