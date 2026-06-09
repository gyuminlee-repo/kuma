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
        """top_n=0 selects all variants without count limit.

        Data uses positions 2-6 (not position 1) so the start-codon filter
        does not interfere with the count assertion.
        """
        csv_file = tmp_path / "all.csv"
        csv_file.write_text(
            "variant,y_pred\n"
            "A2P,1.0\n"
            "A3P,0.9\n"
            "A4P,0.8\n"
            "A5P,0.7\n"
            "A6P,0.6\n"
        )

        result = load_evolvepro_csv(csv_file, top_n=0)

        assert result["selected_count"] == 5
        assert set(result["variants"]) == {"A2P", "A3P", "A4P", "A5P", "A6P"}

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

    def test_pool_autoexpand_fills_understaffed_domain(self):
        """D2 후보가 점수상 낮아 초기 풀에서 누락되어도, autoexpand가 풀을 확장해 quota를 채운다."""
        # D1 (pos 1-100): 50 high-fitness candidates (0.99..0.50)
        # D2 (pos 101-200): 50 low-fitness candidates (0.49..0.00)
        # top_n=20, pool_multiplier=2.0 → initial pool=40 (all D1)
        # quota proportional (equal length): D1=10, D2=10
        # autoexpand should grow pool to include D2 candidates so D2 quota is met.
        rows: list[tuple[str, float]] = []
        for i in range(50):
            rows.append((f"A{i + 1}P", 0.99 - i * 0.01))
        for i in range(50):
            rows.append((f"R{101 + i}K", 0.49 - i * 0.01))
        # rows already in descending score order.

        domains = [
            {"name": "D1", "start": 1, "end": 100},
            {"name": "D2", "start": 101, "end": 200},
        ]

        selected, stats = domain_aware_select(
            rows, domains, top_n=20,
            strategy="proportional",
            domain_quota_min=1,
            pool_multiplier=2.0,
            domain_pool_autoexpand=True,
        )

        d1_count = sum(1 for v, _ in selected if 1 <= int(v[1:-1]) <= 100)
        d2_count = sum(1 for v, _ in selected if 101 <= int(v[1:-1]) <= 200)
        assert stats["D1"]["quota"] == 10
        assert stats["D2"]["quota"] == 10
        assert d1_count == 10
        assert d2_count == 10
        assert len(selected) == 20

    def test_pool_autoexpand_disabled_lets_rebalance_take_over(self):
        """autoexpand=False면 풀 확장 없음. 후보가 진짜 부족하면 기존 pre-quota rebalance가 결손을 처리."""
        # D1: 50 candidates, D2: only 5 candidates available in the dataset.
        rows: list[tuple[str, float]] = [
            (f"A{pos}P", 0.99 - i * 0.001) for i, pos in enumerate(range(10, 60))
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
            pool_multiplier=2.0,
            domain_pool_autoexpand=False,
        )

        # Same expectations as the existing pre-quota rebalance test:
        # D2 truly depleted, deficit flows to D1.
        assert stats["D2"]["quota"] == 5
        d2_count = sum(1 for v, _ in selected if 101 <= int(v[1:-1]) <= 200)
        d1_count = sum(1 for v, _ in selected if 1 <= int(v[1:-1]) <= 100)
        assert d2_count == 5
        assert d1_count >= 35
        assert len(selected) == 40

    def test_pool_autoexpand_skips_equal_strategy(self):
        """equal strategy는 autoexpand 미적용 (사용자 의도 보존)."""
        rows: list[tuple[str, float]] = []
        for i in range(50):
            rows.append((f"A{i + 1}P", 0.99 - i * 0.01))
        for i in range(50):
            rows.append((f"R{101 + i}K", 0.49 - i * 0.01))
        domains = [
            {"name": "D1", "start": 1, "end": 100},
            {"name": "D2", "start": 101, "end": 200},
        ]

        selected, _stats = domain_aware_select(
            rows, domains, top_n=20,
            strategy="equal",
            domain_quota_min=1,
            pool_multiplier=2.0,
            domain_pool_autoexpand=True,
        )
        # equal strategy under autoexpand=True still hits the equal quota
        # via the existing logic because both domains have plenty of rows;
        # the loop is skipped (equal is excluded), and selection proceeds
        # against the full unrestricted rows list.
        d1_count = sum(1 for v, _ in selected if 1 <= int(v[1:-1]) <= 100)
        d2_count = sum(1 for v, _ in selected if 101 <= int(v[1:-1]) <= 200)
        assert d1_count == 10
        assert d2_count == 10


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



class TestStartCodonFilter:
    """Position-1 variants (initiator Met substitutions) are excluded from load_evolvepro_csv results."""

    def test_position_one_variant_excluded(self, tmp_path):
        """Single position-1 variant is removed; other variants pass through."""
        csv_file = tmp_path / "pos1.csv"
        csv_file.write_text(
            "variant,y_pred\n"
            "M1V,0.95\n"
            "A30G,0.80\n"
            "Q50K,0.70\n"
        )

        result = load_evolvepro_csv(csv_file, top_n=10)

        assert "M1V" not in result["variants"], "position-1 variant must be excluded"
        assert "A30G" in result["variants"]
        assert "Q50K" in result["variants"]
        assert result["selected_count"] == 2
        assert result["start_codon_removed"] == 1

    def test_multi_variant_containing_position_one_excluded(self, tmp_path):
        """Multi-variant string with a position-1 token is excluded as a whole."""
        csv_file = tmp_path / "pos1_multi.csv"
        csv_file.write_text(
            "variant,y_pred\n"
            "M1V/A30G,0.90\n"
            "Q50K,0.75\n"
        )

        result = load_evolvepro_csv(csv_file, top_n=10)

        # The compound variant "M1V/A30G" is excluded because one token is position 1.
        assert not any("M1V" in v for v in result["variants"]), (
            "compound variant containing position-1 token must be excluded"
        )
        assert "Q50K" in result["variants"]
        assert result["start_codon_removed"] == 1

    def test_start_codon_removed_count_is_zero_when_no_position_one(self, tmp_path):
        """start_codon_removed is 0 when no position-1 variants are present."""
        csv_file = tmp_path / "no_pos1.csv"
        csv_file.write_text(
            "variant,y_pred\n"
            "A5G,0.85\n"
            "Q50K,0.70\n"
        )

        result = load_evolvepro_csv(csv_file, top_n=10)

        assert result["start_codon_removed"] == 0
        assert result["selected_count"] == 2


    def test_start_codon_removed_variants_list(self, tmp_path):
        """start_codon_removed_variants lists excluded variant strings in input order."""
        csv_file = tmp_path / "pos1_variants.csv"
        csv_file.write_text(
            "variant,y_pred\n"
            "M1V,0.95\n"
            "A30G,0.80\n"
            "Q50K,0.70\n"
        )

        result = load_evolvepro_csv(csv_file, top_n=10)

        assert result["start_codon_removed_variants"] == ["M1V"]
        assert len(result["start_codon_removed_variants"]) == result["start_codon_removed"]
        assert result["step_stats"]["start_codon_removed_variants"] == ["M1V"]

    def test_start_codon_removed_variants_empty_when_none(self, tmp_path):
        """start_codon_removed_variants is [] when no position-1 variants are present."""
        csv_file = tmp_path / "no_pos1_variants.csv"
        csv_file.write_text(
            "variant,y_pred\n"
            "A5G,0.85\n"
            "Q50K,0.70\n"
        )

        result = load_evolvepro_csv(csv_file, top_n=10)

        assert result["start_codon_removed_variants"] == []
        assert len(result["start_codon_removed_variants"]) == result["start_codon_removed"]


class TestRankedCandidates:
    """Validate the ranked_candidates field of load_evolvepro_csv."""

    def test_sorted_descending_by_y_pred(self, tmp_path):
        """ranked_candidates must be ordered by y_pred descending (global sort order)."""
        csv_file = tmp_path / "ranked.csv"
        csv_file.write_text(
            "variant,y_pred\n"
            "A10V,0.50\n"
            "A20V,0.90\n"
            "A30V,0.70\n"
        )

        result = load_evolvepro_csv(csv_file, top_n=2)

        rc = result["ranked_candidates"]
        assert len(rc) >= 2, "at least selected_count items expected"
        scores = [item["y_pred"] for item in rc]
        assert scores == sorted(scores, reverse=True), (
            f"ranked_candidates not sorted descending: {scores}"
        )

    def test_length_capped_at_selected_plus_buffer(self, tmp_path):
        """ranked_candidates length <= selected_count + EVOLVEPRO_RANKED_BUFFER."""
        from kuma_core.kuro.evolvepro import EVOLVEPRO_RANKED_BUFFER

        rows = "\n".join(f"A{i}V,{0.99 - i * 0.01}" for i in range(2, 202))
        csv_file = tmp_path / "big.csv"
        csv_file.write_text("variant,y_pred\n" + rows)

        result = load_evolvepro_csv(csv_file, top_n=10)

        expected_max = result["selected_count"] + EVOLVEPRO_RANKED_BUFFER
        assert len(result["ranked_candidates"]) <= expected_max, (
            f"ranked_candidates has {len(result['ranked_candidates'])} items, "
            f"expected <= {expected_max}"
        )

    def test_y_pred_rounded_to_4_places(self, tmp_path):
        """y_pred in each item is rounded to 4 decimal places."""
        csv_file = tmp_path / "precise.csv"
        csv_file.write_text(
            "variant,y_pred\n"
            "A10V,0.123456789\n"
        )

        result = load_evolvepro_csv(csv_file, top_n=5)

        for item in result["ranked_candidates"]:
            assert item["y_pred"] == round(item["y_pred"], 4), (
                f"y_pred not rounded to 4 places: {item['y_pred']}"
            )

    def test_aa_position_extracted_correctly(self, tmp_path):
        """aa_position must match the numeric part of a standard variant string."""
        csv_file = tmp_path / "positions.csv"
        csv_file.write_text(
            "variant,y_pred\n"
            "A42V,0.90\n"
            "Q100K,0.80\n"
        )

        result = load_evolvepro_csv(csv_file, top_n=5)

        pos_map = {item["variant"]: item["aa_position"] for item in result["ranked_candidates"]}
        assert pos_map["A42V"] == 42, f"Expected aa_position=42, got {pos_map.get('A42V')}"
        assert pos_map["Q100K"] == 100, f"Expected aa_position=100, got {pos_map.get('Q100K')}"

    def test_aa_position_none_for_unparseable_variant(self, tmp_path):
        """aa_position is None (not 0) for variant strings without a position digit."""
        csv_file = tmp_path / "no_pos.csv"
        csv_file.write_text(
            "variant,y_pred\n"
            "WT,0.50\n"
        )

        result = load_evolvepro_csv(csv_file, top_n=5)

        wt_items = [i for i in result["ranked_candidates"] if i["variant"] == "WT"]
        assert wt_items, "WT variant should appear in ranked_candidates"
        assert wt_items[0]["aa_position"] is None, (
            f"Expected None for WT aa_position, got {wt_items[0]['aa_position']}"
        )

    def test_position_filter_does_not_affect_buffer_pool(self, tmp_path):
        """ranked_candidates uses the full sorted list, not the position-filtered one.

        When max_per_position=1, some variants are removed from selection, but
        ranked_candidates must still include them if they fall within
        selected_count + BUFFER from the top of the global score ranking.
        """
        from kuma_core.kuro.evolvepro import EVOLVEPRO_RANKED_BUFFER

        # Two variants at position 10 — only one passes max_per_position=1
        csv_file = tmp_path / "pos_filter.csv"
        csv_file.write_text(
            "variant,y_pred\n"
            "A10V,0.99\n"
            "A10G,0.98\n"  # same position, will be filtered from selection
            "A20V,0.50\n"
        )

        result = load_evolvepro_csv(csv_file, top_n=3, max_per_position=1)

        # A10G may be excluded from selected variants but must still appear in
        # ranked_candidates since it is the 2nd-highest overall score
        rc_variants = {item["variant"] for item in result["ranked_candidates"]}
        assert "A10G" in rc_variants, (
            "A10G filtered from selection but must appear in ranked_candidates "
            "(ranked_candidates uses pre-filter pool)"
        )

    def test_selected_always_subset_of_ranked_candidates_after_position_filter(self, tmp_path):
        """Regression: selected variants must always appear in ranked_candidates.

        Reproduces the buffer-overflow bug: when high-scoring variants cluster at
        a few positions and max_per_position=1, the lowest-ranked selected variants
        can have global scores that fall beyond selected_count + BUFFER from the top.
        Under the old ranked_full[:len(selected)+BUFFER] slice they were silently
        dropped from ranked_candidates, causing the frontend to lose them on load.

        Scenario: 60 variants at 2 positions (scores 1.00-0.41 step 0.01),
        max_per_position=1, top_n=20. Only 2 variants can be selected (one per
        position). But up to 58 unselected variants outrank those 2 selections in
        the global ordering — under the old logic the lower-scoring selected
        variant fell outside ranked_full[:2+50] and was dropped.
        """
        # Build 60 variants: 30 at position 10 (scores 1.00-0.71), 30 at position 20 (scores 0.70-0.41)
        lines = ["variant,y_pred"]
        for i in range(30):
            lines.append(f"A10{chr(ord('A') + i % 20)},{1.00 - i * 0.01:.2f}")
        for i in range(30):
            lines.append(f"B20{chr(ord('A') + i % 20)},{0.70 - i * 0.01:.2f}")
        csv_file = tmp_path / "pos_cluster.csv"
        csv_file.write_text("\n".join(lines))

        result = load_evolvepro_csv(csv_file, top_n=20, max_per_position=1)

        # max_per_position=1 means at most 1 selected per position.
        # selected_count will be ≤ 2 (one per position).
        selected_set = set(result["variants"])
        rc_variants = {item["variant"] for item in result["ranked_candidates"]}

        missing = selected_set - rc_variants
        assert not missing, (
            f"Selected variants missing from ranked_candidates: {missing}. "
            f"selected={sorted(selected_set)}, rc_sample={sorted(rc_variants)[:5]}"
        )

    def test_aa_position_multi_substitution_first_token(self, tmp_path):
        """aa_position returns the first token position for multi-substitution variants.

        Tokens separated by space, comma, or slash — only the first token's
        position is extracted.  This keeps ranked_candidates consistent with
        the design table's per-position representation.
        """
        from kuma_core.kuro.evolvepro import _extract_aa_position

        assert _extract_aa_position("A42V A56T") == 42, "space-separated: first token position"
        assert _extract_aa_position("A42V,A56T") == 42, "comma-separated: first token position"
        assert _extract_aa_position("A42V/A56T") == 42, "slash-separated: first token position"

    def test_aa_position_none_when_first_token_has_no_position(self, tmp_path):
        """aa_position is None when the first token carries no parseable position.

        A leading non-positional token (e.g. WT) must not cause a later token
        to be extracted as the position.
        """
        from kuma_core.kuro.evolvepro import _extract_aa_position

        assert _extract_aa_position("WT") is None, "standalone WT must return None"
        assert _extract_aa_position("del42") is None, "deletion notation without trailing AA must return None"

