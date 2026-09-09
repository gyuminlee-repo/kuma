"""design_single_sdm ranks across the whole tolerance sweep, not within one step.

The engine widens the Tm tolerance in 0.5 C steps and used to return the moment
any candidate survived the current step, so a primer that only appears at a
looser window could never win even when it was strictly better by the engine
own penalty score.

Both cases below are measured, not invented. The first is the worked example
that exposed the defect: egfp G175A, Q5 SDM, full overlap. There the design
exits at +-2.0 C on GCT with penalty 14.12 while +-4.0 C holds GCC at 12.60.
The example was first seen with an unfiltered synonymous pool, and the shipped
two-codon pool reaches the same pair of codons for S. cerevisiae, so the case
runs on shipped code with nothing stubbed. The second covers the partial
overlap branch, which carries a near-duplicate of the same loop: dmpR P297I,
Q5, exits at +-3.0 C with penalty 28.29 and holds 19.98 at +-4.0 C on the same
codon with a different window.

Neither test can pass vacuously. Each asserts that the tight call succeeds and
that its penalty is strictly worse, so a case that stopped exhibiting the
tighter-is-worse shape would fail here rather than quietly assert nothing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from kuma_core.kuro.mutation import Mutation
from kuma_core.kuro.polymerase import PolymeraseRegistry
from kuma_core.kuro.sdm_engine import design_single_sdm, load_fasta

_ROOT = Path(__file__).parent.parent
_EGFP_FA = _ROOT / "src-tauri" / "samples" / "mame" / "egfp_with_flanks.fa"
_DMPR_FA = _ROOT / "fixtures" / "pSHCE-dmpR.fa"

# CDS starts, 0-based. egfp_with_flanks carries a 720 bp CDS between two 450 bp
# flanks; 1790 is the dmpR CDS start that tests/conftest.py ships as TARGET_START.
_EGFP_CDS = 450
_DMPR_CDS = 1790

_TOL_STEPS = [round(0.5 * i, 1) for i in range(1, 9)]


def _mutation(seq: str, cds_start: int, wt_aa: str, position: int, mt_aa: str) -> Mutation:
    """Build the mutation and check the template still carries the wt codon.

    The codon check is what stops a fixture edit from turning these tests into
    an assertion about some other site.
    """
    codon_start = cds_start + (position - 1) * 3
    wt_codon = seq[codon_start:codon_start + 3]
    from kuma_core.kuro.codon_table import CODON_TO_AA

    assert CODON_TO_AA.get(wt_codon) == wt_aa, (
        f"template no longer codes {wt_aa} at position {position}: {wt_codon}"
    )
    return Mutation(
        raw=f"{wt_aa}{position}{mt_aa}",
        wt_aa=wt_aa,
        position=position,
        mt_aa=mt_aa,
        codon_start=codon_start,
        wt_codon=wt_codon,
        mt_codon="",
    )


@pytest.fixture(scope="module")
def egfp() -> str:
    return load_fasta(_EGFP_FA)[1]


@pytest.fixture(scope="module")
def dmpr() -> str:
    return load_fasta(_DMPR_FA)[1]


# (label, template fixture name, cds start, wt_aa, position, mt_aa, polymerase,
#  overlap mode, organism, the tight tol_max the engine used to stop at)
_CASES = [
    ("egfp G175A full overlap", "egfp", _EGFP_CDS, "G", 175, "A",
     "Q5 SDM", "full", "scerevisiae", 2.0),
    ("dmpR P297I partial overlap", "dmpr", _DMPR_CDS, "P", 297, "I",
     "Q5", "partial", "ecoli", 3.0),
]


@pytest.mark.parametrize(
    "label,template,cds,wt_aa,pos,mt_aa,poly,mode,organism,tight",
    _CASES,
    ids=[c[0] for c in _CASES],
)
def test_a_looser_tolerance_wins_when_it_holds_a_better_primer(
    request, label, template, cds, wt_aa, pos, mt_aa, poly, mode, organism, tight
):
    seq = request.getfixturevalue(template)
    mut = _mutation(seq, cds, wt_aa, pos, mt_aa)
    profile = PolymeraseRegistry().get(poly)

    tight_hit = design_single_sdm(
        seq, mut, profile, organism=organism, tol_max=tight, overlap_mode=mode
    )
    wide_hit = design_single_sdm(
        seq, mut, profile, organism=organism, tol_max=4.0, overlap_mode=mode
    )

    # Non-vacuity: the tight window must actually yield a primer, otherwise the
    # comparison below would be trivially satisfied by an empty result.
    assert tight_hit, f"{label}: no primer at tol_max {tight}, case no longer applies"
    assert wide_hit, f"{label}: no primer at tol_max 4.0"

    assert wide_hit[0].penalty < tight_hit[0].penalty, (
        f"{label}: widening the tolerance did not surface the better primer "
        f"({wide_hit[0].penalty} vs {tight_hit[0].penalty})"
    )
    # The winner really came from a window the old early return never reached.
    assert wide_hit[0].tolerance_used > tight, (
        f"{label}: winner reports tolerance {wide_hit[0].tolerance_used}, "
        f"which the tol_max {tight} run already covered"
    )


@pytest.mark.parametrize(
    "label,template,cds,wt_aa,pos,mt_aa,poly,mode,organism,tight",
    _CASES,
    ids=[c[0] for c in _CASES],
)
def test_penalty_never_rises_as_the_tolerance_budget_widens(
    request, label, template, cds, wt_aa, pos, mt_aa, poly, mode, organism, tight
):
    """A larger tol_max only adds steps, so the best penalty cannot get worse."""
    seq = request.getfixturevalue(template)
    mut = _mutation(seq, cds, wt_aa, pos, mt_aa)
    profile = PolymeraseRegistry().get(poly)

    best = None
    for tol_max in _TOL_STEPS:
        hit = design_single_sdm(
            seq, mut, profile, organism=organism, tol_max=tol_max, overlap_mode=mode
        )
        if not hit:
            continue
        if best is not None:
            assert hit[0].penalty <= best + 1e-9, (
                f"{label}: tol_max {tol_max} returned {hit[0].penalty}, worse than "
                f"{best} from a tighter budget"
            )
        best = hit[0].penalty
    assert best is not None, f"{label}: no primer at any tolerance"


def test_returned_candidates_report_the_window_that_produced_them(egfp):
    """Ranking spans steps; each candidate keeps its own tolerance_used.

    The Tol column is read as a quality signal, so a candidate found at a tight
    window must not be relabelled with the widest one just because the sweep ran
    that far. Here the winner comes from +-4.0 C and the runner-up from +-2.0 C.
    """
    mut = _mutation(egfp, _EGFP_CDS, "G", 175, "A")
    profile = PolymeraseRegistry().get("Q5 SDM")
    hits = design_single_sdm(
        egfp, mut, profile, organism="scerevisiae", tol_max=4.0, overlap_mode="full"
    )

    assert len(hits) >= 2, "expected the losing codon to survive as a runner-up"
    assert [h.penalty for h in hits] == sorted(h.penalty for h in hits)
    assert len({h.tolerance_used for h in hits}) > 1, (
        "every candidate carries the same tolerance, so the sweep is not being "
        "ranked across steps"
    )
    assert hits[0].tolerance_used > hits[1].tolerance_used, (
        "the better primer here is the one from the looser window"
    )
