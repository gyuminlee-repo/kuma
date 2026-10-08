import csv
import json
from pathlib import Path

import numpy as np
import pytest

from al.acquisition import select_indices
from al.attribution import signal_quality_degradation
from al.pilot import extrapolate_ceiling, gate_g1
from al.rugged_sim import load_records_csv, regime_decision_table


@pytest.mark.parametrize("anchor_count", [0, 1, 2, 5])
def test_sigma_keeps_selected_candidates_distinct_from_anchors(anchor_count: int) -> None:
    selected = select_indices(
        "sigma_kuro", mean=[3.0, 2.0, 1.0], n=2,
        rng=np.random.default_rng(7),
        positions=[(1, 1, 1, 1), (1, 1, 1, 0), (0, 0, 1, 1)],
        anchor_positions=[(0, 0, 0, 0)] * anchor_count,
        evolvepro_round=1, round_size=2,
    )
    print(f"BEN-01 anchors={anchor_count} selected={selected}")
    assert selected == ([0, 2] if anchor_count else [2, 1])


@pytest.mark.parametrize(
    "benefits,expected",
    [([0.01, 0.02, 0.03], True), ([0.03, 0.02, 0.01], False),
     ([0.0, 0.0, 0.0], True), ([0.01, 0.03, 0.02], False)],
)
def test_attribution_reports_increasing_benefit_as_signal_weakens(
    tmp_path: Path, benefits: list[float], expected: bool,
) -> None:
    for name, strength, benefit in zip(
        ["pilot.json", "pilot_RASK.json", "pilot_GRB2.json"],
        [0.9, 0.6, 0.3], benefits, strict=True,
    ):
        (tmp_path / name).write_text(json.dumps({
            "per_arm_norm_best_mean": {
                "topn": strength, "random": 0.0, "kuro_ca": strength + benefit,
            },
            "decision_kuro_ca_vs_topn": {"decision_cell": "audit"},
        }), encoding="utf-8")
    result = signal_quality_degradation(tmp_path)
    flag = result["g002_monotone_div_benefit_rises_with_weak_signal"]
    print(f"BEN-02 benefits={benefits} flag={flag}")
    assert result["g002_ranked_by_signal_strength_desc"] == ["F7YBW8", "RASK", "GRB2"]
    assert flag is expected


@pytest.mark.parametrize("empty_kind", ["pilot", "arms", "mixed"])
def test_gate_rejects_missing_pilot_coverage(empty_kind: str) -> None:
    empty_assay = {"per_arm": {}, "axis_relevance": {"axis_relevant": False}}
    valid_assay = {
        "per_arm": {"topn": {"coverage": {"kcenter_radius": 1.0}}},
        "axis_relevance": {"axis_relevant": False},
    }
    pilots = {"pilot": [], "arms": [empty_assay], "mixed": [valid_assay, empty_assay]}
    result = gate_g1(pilots[empty_kind], 1.0, extrapolate_ceiling(6.0))
    print(f"BEN-03 input={empty_kind} result={result}")
    assert result["checks"]["b_coverage_emitted_with_threshold"] is False
    assert result["passed"] is False


@pytest.mark.parametrize(
    "a_seeds,b_seeds",
    [(list(range(6)), list(range(100, 106))),
     (list(range(6)), list(range(1, 7))),
     (list(range(6)), list(range(5))),
     ([0, 0, 1, 2, 3, 4], [0, 0, 1, 2, 3, 4]),
     ([0, 0, 1, 2, 3, 4], list(range(6)))],
)
def test_regime_rejects_unpaired_or_duplicate_seeds(
    tmp_path: Path, a_seeds: list[int], b_seeds: list[int],
) -> None:
    path = tmp_path / "campaigns.csv"
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["K", "arm", "seed", "norm_best"])
        writer.writeheader()
        for arm, seeds, value in [("sigma_kuro", a_seeds, 0.9), ("topn", b_seeds, 0.1)]:
            writer.writerows({"K": 2, "arm": arm, "seed": seed, "norm_best": value}
                             for seed in seeds)
    with pytest.raises(ValueError, match="seed") as error:
        regime_decision_table(load_records_csv(str(path)))
    print(f"BEN-04 rejected a={a_seeds} b={b_seeds}: {error.value}")


def test_regime_aligns_shuffled_unique_seeds_within_each_k() -> None:
    records = []
    for k in (0, 2):
        for seed in range(6):
            base = 0.1 + seed * 0.1
            records.extend([
                {"K": k, "arm": "sigma_kuro", "seed": seed, "norm_best": base + 0.2},
                {"K": k, "arm": "topn", "seed": seed, "norm_best": base},
            ])
    expected = regime_decision_table(records)
    shuffled = [records[int(i)] for i in np.random.default_rng(7).permutation(len(records))]
    actual = regime_decision_table(shuffled)
    print(f"BEN-04 aligned table={actual}")
    assert actual == expected
    assert [row["K"] for row in actual] == [0, 2]
    for row in actual:
        assert row["n_seeds"] == 6
        assert row["median_delta"] == pytest.approx(0.2)
        assert row["wilcoxon_p_raw"] == pytest.approx(0.03125)
        assert row["wilcoxon_p_holm"] == pytest.approx(0.0625)
        assert row["tail_ci"] == pytest.approx((-0.2, -0.2))
