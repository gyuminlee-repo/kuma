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

    def test_shortfall_does_not_oversubscribe_high_score_domain(self):
        """회귀 감지: D1에 high y_pred가 몰려 있어도 D1이 자기 quota를 초과해서 가져가지 않음."""
        # D1: high y_pred 20개 (positions 1-100)
        # D2: mid y_pred 2개 (positions 101-200)
        # D3: low y_pred 1개 (positions 201-300)
        rows: list[tuple[str, float]] = []
        for i, pos in enumerate(range(5, 100, 5)):
            rows.append((f"A{pos}P", 0.95 - i * 0.01))
        rows.append(("R150K", 0.55))
        rows.append(("R160K", 0.50))
        rows.append(("E250Q", 0.20))

        domains = [
            {"name": "D1", "start": 1, "end": 100},
            {"name": "D2", "start": 101, "end": 200},
            {"name": "D3", "start": 201, "end": 300},
        ]

        selected, stats = domain_aware_select(
            rows, domains, top_n=9,
            strategy="equal",
            domain_quota_min=1,
        )

        # Hard constraint: D1은 quota 초과 금지
        d1_count = sum(1 for v, _ in selected if 1 <= int(v[1:-1]) <= 100)
        assert d1_count <= stats["D1"]["quota"], (
            f"D1 oversubscribed: {d1_count} > quota {stats['D1']['quota']}"
        )
        # top_n 미충족 허용 (D3 후보 부족 → 총 선택 < 9)
        assert len(selected) <= 9

    def test_proportional_rebalances_when_domain_understaffed(self):
        """Pre-quota rebalance: D2 candidate가 quota보다 적으면 결손이 D1로 재분배되어 top_n 충족."""
        # D1 (pos 10-100): 50 candidates
        # D2 (pos 150-160): 5 candidates only
        rows: list[tuple[str, float]] = [
            (f"A{pos}P", 0.99 - i * 0.001) for i, pos in enumerate(range(10, 100))
        ] + [
            (f"R{pos}K", 0.40 - i * 0.01) for i, pos in enumerate(range(150, 155))
        ]

        domains = [
            {"name": "D1", "start": 1, "end": 100},
            {"name": "D2", "start": 101, "end": 200},
        ]

        selected, stats = domain_aware_select(
            rows, domains, top_n=40,
            strategy="proportional",
            domain_quota_min=1,
        )

        d2_count = sum(1 for v, _ in selected if 101 <= int(v[1:-1]) <= 200)
        d1_count = sum(1 for v, _ in selected if 1 <= int(v[1:-1]) <= 100)

        # D2 candidate=5 → quota clamp to 5, deficit (~15) flows to D1
        assert stats["D2"]["quota"] == 5
        assert d2_count == 5
        assert d1_count >= 35
        assert len(selected) == 40

    def test_equal_strategy_does_not_rebalance(self):
        """equal strategy는 의도 보존: 후보 부족 도메인 결손이 다른 도메인으로 흐르지 않는다."""
        rows: list[tuple[str, float]] = []
        for i, pos in enumerate(range(10, 60)):
            rows.append((f"A{pos}P", 0.99 - i * 0.001))
        rows.append(("R150K", 0.30))
        rows.append(("R151K", 0.29))

        domains = [
            {"name": "D1", "start": 1, "end": 100},
            {"name": "D2", "start": 101, "end": 200},
        ]

        selected, stats = domain_aware_select(
            rows, domains, top_n=20,
            strategy="equal",
            domain_quota_min=1,
        )

        # equal: each domain has quota=10. D2 caps at 2 candidates, no flow-over.
        assert stats["D1"]["quota"] == 10
        assert stats["D2"]["quota"] == 10
        d1_count = sum(1 for v, _ in selected if 1 <= int(v[1:-1]) <= 100)
        d2_count = sum(1 for v, _ in selected if 101 <= int(v[1:-1]) <= 200)
        assert d1_count == 10
        assert d2_count == 2  # only 2 available, no redistribution
        assert len(selected) == 12  # top_n=20 not met by design


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
