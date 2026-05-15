"""Tests for EVOLVEpro CSV loading and column compatibility."""

from __future__ import annotations

import pytest

from kuma_core.kuro.evolvepro import VARIANT_COLUMNS, domain_aware_select, load_evolvepro_csv


class TestLoadEvolveproCsv:
    def test_load_variant_csv_backward_compat(self, tmp_path):
        """Legacy CSV with 'variant' and 'y_pred' columns loads without error."""
        csv_file = tmp_path / "legacy.csv"
        csv_file.write_text(
            "variant,y_pred\n"
            "Q10A,0.90\n"
            "Q11A,0.85\n"
        )

        result = load_evolvepro_csv(csv_file, top_n=10)

        assert result["selected_count"] == 2
        assert "Q10A" in result["variants"]
        assert "Q11A" in result["variants"]
        assert result["y_preds"][0] == pytest.approx(0.90)

    def test_top_n_zero_returns_all(self, tmp_path):
        """top_n=0 selects all variants without count limit."""
        csv_file = tmp_path / "all.csv"
        csv_file.write_text(
            "variant,y_pred\n"
            "A1P,1.0\n"
            "A2P,0.9\n"
            "A3P,0.8\n"
            "A4P,0.7\n"
            "A5P,0.6\n"
        )

        result = load_evolvepro_csv(csv_file, top_n=0)

        assert result["selected_count"] == 5
        assert set(result["variants"]) == {"A1P", "A2P", "A3P", "A4P", "A5P"}

    def test_load_csv_missing_column(self, tmp_path):
        """CSV with no supported variant column raises ValueError with column list."""
        csv_file = tmp_path / "bad.csv"
        csv_file.write_text(
            "seq_id,score\n"
            "seq1,1.0\n"
        )

        with pytest.raises(ValueError) as exc_info:
            load_evolvepro_csv(csv_file)

        error_msg = str(exc_info.value)
        # Error message must mention at least one supported column name
        assert any(col in error_msg for col in VARIANT_COLUMNS), (
            f"Expected supported column names in error message, got: {error_msg}"
        )


class TestDomainAwareSelect:
    def test_domain_quota_min_does_not_oversubscribe_top_n(self):
        rows = [
            ("A5P", 1.0),
            ("A15P", 0.9),
            ("A25P", 0.8),
        ]
        domains = [
            {"name": "D1", "start": 1, "end": 10},
            {"name": "D2", "start": 11, "end": 20},
            {"name": "D3", "start": 21, "end": 30},
        ]

        selected, stats = domain_aware_select(
            rows,
            domains,
            top_n=2,
            strategy="proportional",
            domain_quota_min=1,
        )

        assert len(selected) == 2
        assert sum(item["quota"] for item in stats.values()) == 2


class TestRefSeqConversion:
    """v0.3 §4: ref_seq enables 89W → F89W conversion (EVOLVEpro short notation)."""

    def test_short_form_converts_with_ref_seq(self, tmp_path):
        csv_file = tmp_path / "ep_short.csv"
        csv_file.write_text(
            "variant,y_pred\n"
            "2W,1.5\n"
            "5K,1.2\n"
        )
        # ref_seq pos 1=M, 2=F, 3=L, 4=S, 5=I
        result = load_evolvepro_csv(csv_file, top_n=10, ref_seq="MFLSI")
        assert "F2W" in result["variants"]
        assert "I5K" in result["variants"]

    def test_short_form_passthrough_without_ref_seq(self, tmp_path):
        csv_file = tmp_path / "ep_short_noref.csv"
        csv_file.write_text(
            "variant,y_pred\n"
            "2W,1.5\n"
        )
        result = load_evolvepro_csv(csv_file, top_n=10)
        assert result["variants"] == ["2W"]

    def test_internal_form_passes_through(self, tmp_path):
        csv_file = tmp_path / "ep_internal.csv"
        csv_file.write_text(
            "variant,y_pred\n"
            "F89W,1.5\n"
        )
        result = load_evolvepro_csv(csv_file, top_n=10, ref_seq="M" * 100)
        assert result["variants"] == ["F89W"]

    def test_out_of_range_position_not_converted(self, tmp_path):
        csv_file = tmp_path / "ep_oor.csv"
        csv_file.write_text(
            "variant,y_pred\n"
            "100W,1.5\n"
        )
        result = load_evolvepro_csv(csv_file, top_n=10, ref_seq="MFLSI")
        assert result["variants"] == ["100W"]
