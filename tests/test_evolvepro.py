"""Tests for EVOLVEpro CSV loading and column compatibility."""

from __future__ import annotations

import pytest

from kuma_core.kuro.evolvepro import SCORE_COLUMNS, VARIANT_COLUMNS, domain_aware_select, load_evolvepro_csv


class TestLoadEvolveproCsv:
    def test_load_multievolve_csv(self, tmp_path):
        """MULTI-evolve CSV with 'mutation' and 'property_value' columns loads correctly."""
        csv_file = tmp_path / "multievolve.csv"
        csv_file.write_text(
            "mutation,property_value\n"
            "A40P,1.23\n"
            "E61Y,0.95\n"
            "K100R,0.80\n"
        )

        result = load_evolvepro_csv(csv_file, top_n=10)

        assert result["selected_count"] == 3
        assert "A40P" in result["variants"]
        assert "E61Y" in result["variants"]
        assert "K100R" in result["variants"]
        # Scores should be read from property_value
        assert result["y_preds"][0] == pytest.approx(1.23)

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
