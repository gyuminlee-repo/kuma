"""Self-calibrating purity review: a run judged against its own plate."""

from __future__ import annotations

from pathlib import Path

import pytest

from kuma_core.mame.models import BarcodeRecord
from kuma_core.mame.select.purity import (
    plate_baseline,
    review_reason,
    support_lower_bound,
)


def _rec(
    support: float | None = 0.98,
    depth: int = 500,
    positions: int = 1,
    indel: float = 0.01,
) -> BarcodeRecord:
    return BarcodeRecord(
        native_barcode="NB07",
        custom_barcode="1_1",
        consensus_seq="",
        file_size_kb=60.0,
        source_path=Path("/tmp/mock.fasta"),
        min_variant_support=support,
        min_variant_support_depth=depth,
        n_variant_positions=positions,
        max_indel_event_fraction=indel,
    )


class TestSupportLowerBound:
    def test_depth_moves_the_bound(self) -> None:
        shallow = support_lower_bound(_rec(support=0.98, depth=12))
        deep = support_lower_bound(_rec(support=0.98, depth=562))
        assert shallow is not None and deep is not None
        assert shallow < deep < 0.98

    def test_unknown_stays_unknown(self) -> None:
        assert support_lower_bound(_rec(support=None)) is None
        assert support_lower_bound(_rec(positions=0)) is None
        assert support_lower_bound(_rec(depth=0)) is None


class TestPlateBaseline:
    def test_flags_the_indel_outlier_only(self) -> None:
        """The G3 shape: one well carries a deletion the rest do not."""
        clean = [_rec(indel=0.01) for _ in range(20)]
        outlier = _rec(indel=0.22)
        baseline = plate_baseline(clean + [outlier])

        assert review_reason(outlier, baseline).startswith("indel reads")
        assert review_reason(clean[0], baseline) == ""

    def test_flags_the_support_outlier_only(self) -> None:
        clean = [_rec(support=0.97) for _ in range(20)]
        outlier = _rec(support=0.60)
        baseline = plate_baseline(clean + [outlier])

        assert "substitution support" in review_reason(outlier, baseline)
        assert review_reason(clean[0], baseline) == ""

    def test_reports_the_measured_value_and_the_baseline(self) -> None:
        """A reader must be able to disagree without rerunning anything."""
        clean = [_rec(indel=0.01) for _ in range(20)]
        outlier = _rec(indel=0.40)
        reason = review_reason(outlier, plate_baseline(clean + [outlier]))

        assert "0.400" in reason
        assert "MAD" in reason

    def test_a_plate_that_agrees_flags_nobody(self) -> None:
        """Zero spread means no outlier exists, not that the odd well is one."""
        records = [_rec(indel=0.01, support=0.98) for _ in range(20)]
        baseline = plate_baseline(records)

        assert all(review_reason(r, baseline) == "" for r in records)

    def test_too_few_wells_to_have_a_baseline(self) -> None:
        records = [_rec(indel=0.01), _rec(indel=0.90)]
        baseline = plate_baseline(records)

        assert baseline.indel_median is None
        assert review_reason(records[1], baseline) == ""

    def test_a_few_bad_wells_do_not_move_the_baseline(self) -> None:
        """Median and MAD are used precisely so outliers cannot hide each other."""
        clean = [_rec(indel=0.01) for _ in range(17)]
        bad = [_rec(indel=0.35), _rec(indel=0.40), _rec(indel=0.45)]
        baseline = plate_baseline(clean + bad)

        assert all(review_reason(r, baseline) != "" for r in bad)
        assert review_reason(clean[0], baseline) == ""

    @pytest.mark.parametrize("missing", [None])
    def test_unknown_support_never_reads_as_zero(self, missing: None) -> None:
        clean = [_rec(support=0.97) for _ in range(20)]
        unknown = _rec(support=missing)
        baseline = plate_baseline(clean + [unknown])

        assert "substitution support" not in review_reason(unknown, baseline)
