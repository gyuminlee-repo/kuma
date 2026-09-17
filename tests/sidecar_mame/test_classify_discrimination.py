"""Discrimination regression for the MAME transition classifier.

What this pins
--------------
``strategy.classify_round`` advises whether the next round should stay on the
single-walk path or move to a combinatorial plate.  A recommender is only worth
reading if its answer moves with the campaign.  These tests build campaigns
whose right answer is known by construction and measure how often the handler
gives it.

Everything runs through ``handle_classify_round``.  The defects these tests are
written against live in the handler (it reads the wild-type replicates of the
last round only and hands every earlier round ``sigma_assay=None``), so a
harness that assembled ``RoundState`` itself would keep passing while the
product stayed broken.  The one exception is the T3-NA control at the bottom,
which cannot be expressed through the handler at all; its reason is written
there.

Assumptions, and where the numbers come from
--------------------------------------------
- ``SIGMA_LOG2 = 0.1575`` is the measured wild-type spread, not an assumption.
  ``docs/2026-08-19-mame-assay-noise-model.md:137-140`` reports two campaign
  plates read through the product parser: ``251001_report.xlsx`` at 0.15747 and
  ``260327_Ep_R1_positive.xlsx`` at 0.14475 log2.  The larger is used.
- 88 designed variants per plate, 3 wild-type wells per plate, 5 rounds.  Three
  is what the WT block carries and is also ``wt_replicate_min`` in the handler.
- A round file holds one activity per variant, already a ratio to the WT block
  mean, so ``activity > 1.0`` is the beneficial call the handler makes.
- Non-beneficial variants are drawn deleterious rather than neutral.  A neutral
  variant would cross 1.0 half the time on noise alone and every scenario would
  carry a hit rate near 0.5 regardless of its biology.
- Randomness is a fixed ``random.Random`` seed per test so a failure reproduces.
"""

from __future__ import annotations

import random
from collections import Counter
from pathlib import Path

import openpyxl
import pytest

from sidecar_mame.handlers import classify_round as classify_round_mod
from sidecar_mame.handlers.classify_round import handle_classify_round

# Measured wild-type spread on the log2 scale.
# docs/2026-08-19-mame-assay-noise-model.md:137-140 (plates 251001_report.xlsx
# = 0.15747, 260327_Ep_R1_positive.xlsx = 0.14475).  The pessimistic one.
SIGMA_LOG2 = 0.1575

N_VARIANTS = 88   # designed variants on one plate
N_WT_WELLS = 3    # WT_1..WT_3, the block a plate carries
N_ROUNDS = 5      # enough that N_min=3 is cleared and T3 has a window

# Campaign repeats per scenario.  Enough that a 10 % rate is not one campaign
# either way (60 campaigns resolves ~1.7 % steps), few enough that the whole
# module stays inside a CI minute.
N_CAMPAIGNS = 60

# The handler hardcodes 1000 bootstrap draws.  The draws only sharpen the
# confidence estimate behind an already-chosen branch, so lowering it cannot
# change which branch the decision tree proposes; it only blurs the gate at
# 0.7, and the confidences this classifier produces sit at the extremes.
BOOTSTRAP_N_FOR_TESTS = 50

AMINO_ACIDS = "ACDEFGHIKLMNPQRSTVWY"

# Labels that recommend leaving the single-walk path.
TRANSITION_LABELS = frozenset({"switch_combinatorial", "stop"})


# ---------------------------------------------------------------------------
# Campaign synthesis
# ---------------------------------------------------------------------------

def _beneficial_fraction_flat(_round_n: int) -> float:
    """A constant share of the plate is beneficial.

    This is the shape that separates the two scenarios below, because it holds
    the hit rate still and leaves the *size* of the improvement as the only
    thing that differs.  A campaign finding fewer but much better variants is
    ordinary, and the best activity is what T2 measures.
    """
    return 0.10


def _beneficial_fraction_halving(round_n: int) -> float:
    # The beneficial pool is being used up: 0.16, 0.08, 0.04, 0.02, 0.01.
    return 0.16 * (0.5 ** (round_n - 1))


def _write_round_xlsx(path: Path, records: list[tuple[str, float]]) -> None:
    """Write one round file in the shape ``_load_xlsx`` demands.

    Headers are exactly ``Variant`` and ``activity``; the handler matches them
    case-sensitively and raises otherwise.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None  # a fresh Workbook always has an active sheet
    ws.append(["Variant", "activity"])
    for variant, activity in records:
        ws.append([variant, activity])
    wb.save(path)
    wb.close()


def _make_campaign(
    tmp_dir: Path,
    rng: random.Random,
    *,
    tag: str,
    mu_step: float,
    fraction,
) -> list[dict]:
    """Build one campaign of ``N_ROUNDS`` round files and return ``round_files``.

    ``mu_step`` is the log2 gain the beneficial pool acquires per round, so 1.0
    doubles the typical hit each round and 2.0 quadruples it.  ``fraction``
    returns the beneficial fraction of the plate for a round number.

    ``wt_values`` rides on **every** entry, which is what the frontend sends
    (``src/lib/round/roundArtifacts.ts:87-99``).  The handler reading only the
    last one is the defect, not the input.
    """
    round_files: list[dict] = []
    for round_n in range(1, N_ROUNDS + 1):
        mu = 1.0 + mu_step * (round_n - 1)
        n_beneficial = round(N_VARIANTS * fraction(round_n))

        positions = rng.sample(range(10, 500), N_VARIANTS)
        records: list[tuple[str, float]] = []
        for i, position in enumerate(positions):
            if i < n_beneficial:
                true_log2 = rng.gauss(mu, 0.4)
            else:
                # Most single mutants lose activity; 1.2 log2 down keeps them
                # from crossing the beneficial line on assay noise alone.
                true_log2 = rng.gauss(-1.2, 0.6)
            measured_log2 = true_log2 + rng.gauss(0.0, SIGMA_LOG2)
            activity = 2.0 ** measured_log2
            variant = f"{position}{rng.choice(AMINO_ACIDS)}"
            records.append((variant, activity))
        rng.shuffle(records)

        path = tmp_dir / f"{tag}_r{round_n}.xlsx"
        _write_round_xlsx(path, records)

        wt_values = [2.0 ** rng.gauss(0.0, SIGMA_LOG2) for _ in range(N_WT_WELLS)]
        round_files.append({"n": round_n, "path": str(path), "wt_values": wt_values})

    return round_files


def _outcome(result: dict) -> str:
    """Collapse the two response shapes into one label for tallying."""
    if result.get("advisory") == "not_assessable":
        return f"not_assessable:{result['reason']}"
    return f"{result['label']}:{result['reason']}"


def _run_scenario(
    tmp_path: Path,
    *,
    tag: str,
    seed: int,
    mu_step: float,
    fraction,
) -> Counter:
    rng = random.Random(seed)
    tally: Counter = Counter()
    scenario_dir = tmp_path / tag
    scenario_dir.mkdir(parents=True, exist_ok=True)
    for i in range(N_CAMPAIGNS):
        round_files = _make_campaign(
            scenario_dir, rng, tag=f"{tag}_{i}", mu_step=mu_step, fraction=fraction
        )
        result = handle_classify_round({"round_files": round_files, "c_next": 96})
        tally[_outcome(result)] += 1
    return tally


def _transition_rate(tally: Counter) -> float:
    transitions = sum(
        count for outcome, count in tally.items()
        if outcome.split(":")[0] in TRANSITION_LABELS
    )
    return transitions / sum(tally.values())


def _report(tag: str, tally: Counter) -> str:
    lines = [f"{tag}: transition rate {_transition_rate(tally):.1%}"]
    for outcome, count in sorted(tally.items(), key=lambda kv: -kv[1]):
        lines.append(f"    {outcome}: {count}/{sum(tally.values())}")
    return "\n".join(lines)


@pytest.fixture
def cheap_bootstrap(monkeypatch):
    monkeypatch.setitem(
        classify_round_mod._DEFAULT_REGISTERED, "bootstrap_n", BOOTSTRAP_N_FOR_TESTS
    )


# ---------------------------------------------------------------------------
# Known-answer corpus
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("tag", "seed", "mu_step"),
    [
        ("improving_2x", 20260918, 1.0),   # best hit doubles each round
        ("improving_4x", 20260919, 2.0),   # best hit quadruples each round
    ],
)
def test_improving_campaign_is_not_told_to_switch(
    tmp_path, cheap_bootstrap, tag, seed, mu_step
):
    """A campaign still gaining ground must be told to keep walking.

    The beneficial pool gains 1.0 or 2.0 log2 every round while its size stays
    put, so the walk is delivering a best variant two or four times better each
    time.  The plateau threshold these gains are judged against is
    1.96 * sigma * sqrt(2) = 0.44 log2, so every round clears it by a factor of
    2.3 or more.  No round of such a campaign is plateaued, and every
    transition recommendation here is a false positive.
    """
    tally = _run_scenario(
        tmp_path, tag=tag, seed=seed, mu_step=mu_step,
        fraction=_beneficial_fraction_flat,
    )
    rate = _transition_rate(tally)
    # 10 %: a recommender that misfires on one campaign in eight is not read as
    # advice, and the measured baseline before the fix sat at 13 %.  This is the
    # bar the fix has to clear, not a bar drawn around current behaviour.
    assert rate <= 0.10, _report(tag, tally)


def test_stagnant_campaign_is_told_to_transition(tmp_path, cheap_bootstrap):
    """A campaign that gains nothing across five rounds must propose leaving.

    Same plate shape as the improving scenarios with the per-round gain set to
    zero: the beneficial fraction and the beneficial effect size are both
    constant, so the best variant moves only on assay noise, well under the
    0.44 log2 plateau threshold.
    """
    tally = _run_scenario(
        tmp_path, tag="stagnant", seed=20260920, mu_step=0.0,
        fraction=_beneficial_fraction_flat,
    )
    rate = _transition_rate(tally)
    # 80 %: five rounds of zero gain against a threshold the campaign never
    # approaches is a plateau by the classifier's own definition, so a detector
    # that reads its own signals should find nearly all of them.  The allowance
    # is for the hysteresis rule, which legitimately withholds a verdict when
    # the penultimate round happens to look alive.
    assert rate >= 0.80, _report("stagnant", tally)


def test_exhausting_campaign_is_told_to_transition(tmp_path, cheap_bootstrap):
    """A campaign whose beneficial pool halves each round must propose leaving.

    Hits arrive early and dry up: 14, 7, 4, 2, 1 beneficial variants of 88.
    That is the textbook case for moving to a combinatorial plate built from
    the singles already in hand.
    """
    tally = _run_scenario(
        tmp_path, tag="exhausting", seed=20260921, mu_step=0.0,
        fraction=_beneficial_fraction_halving,
    )
    rate = _transition_rate(tally)
    # 80 %: same bar as the stagnant campaign, for the same reason.  Holding
    # both directions in one module is what stops a fix from suppressing false
    # switches by never switching.
    assert rate >= 0.80, _report("exhausting", tally)


# ---------------------------------------------------------------------------
# Control: T2 alone cannot reach a decision
# ---------------------------------------------------------------------------

def test_t2_alone_never_reaches_a_transition():
    """With T3 unavailable, a fully plateaued campaign still says continue.

    This one case calls ``classify`` directly rather than the handler, because
    it cannot be built through the handler at all: T3 is NA only when fewer
    than two hit rates exist, ``hit_rates`` has one entry per round file, and a
    single round file puts ``n`` below ``N_min=3`` so classify() returns
    ``calibration_period`` before any signal is read.  The state below is
    otherwise exactly what the handler assembles -- in particular
    ``previous_signals`` carries ``T2=None`` because the handler hands every
    interim round ``sigma_assay=None`` (classify_round.py:596).

    What it pins: ``sat_prev`` can only ever be lit by T3, so T2 is structurally
    excluded from the two-round hysteresis rule however certain it is.  Here T2
    is True (a 0.0 log2 gain against a 0.44 threshold) and T1 is True, and the
    answer is still continue_walking.
    """
    from kuma_core.strategy.classify import RoundState, Signals, classify

    registered = dict(classify_round_mod._DEFAULT_REGISTERED)

    # What the handler builds for an interim round: sigma_assay=None makes T2
    # and T_model NA, and a one-entry hit-rate history makes T3 NA too.
    previous = Signals(
        T1=True, T2=None, T3=None, T4=None, T_active=None, T_model=None, T_unused=False
    )

    state = RoundState(
        n=N_ROUNDS,
        previous_signals=previous,
        cumulative_beneficial=40,          # >= K_throughput(96) = 14, so T1 True
        K_throughput=14,
        delta_best_ema=0.0,                # no gain at all -> T2 True
        sigma_assay=SIGMA_LOG2,
        r=1,
        hit_rates=[0.10],                  # one entry -> T3 NA
        top_k_positions_n=set(range(14)),
        top_k_positions_n1=set(range(14)),
        top_k_positions=list(range(14)),
        active_residues=[],
        unused_beneficial_count=0,
        n_designed=N_VARIANTS,
        wt_values=[0.0, 0.05, -0.05],      # log2 scale, as the handler passes them
        current_round_activities=[0.0] * N_VARIANTS,
    )

    decision = classify(state, registered)

    # Not a threshold, an exact outcome: the campaign is as plateaued as the
    # inputs allow and the classifier still cannot say so.
    assert decision.label == "continue_walking"
    assert decision.reason == "hysteresis_pending"
