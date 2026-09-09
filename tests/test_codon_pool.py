"""The design codon pool: what it may offer and what it may never offer.

design_single_sdm used to receive at most two codons per mutation, the one
closest to the WT codon and the one the host uses most. It now receives every
synonymous codon the host uses at least CODON_USAGE_FLOOR of the time, and
ranks the primers they produce by penalty. Two things had to be pinned when
that changed: the pool cannot smuggle in a codon the host barely uses, and its
order has to be a function of the table rather than of dict iteration, because
that order is what breaks an exact penalty tie.
"""

from __future__ import annotations

import pytest

from kuma_core.kuro.codon_table import (
    CODON_TO_AA,
    CODON_USAGE_FLOOR,
    codon_to_aa,
    codon_usage_fraction,
    get_codon_table,
    mt_codons_for_design,
)
from kuma_core.kuro.mutation import Mutation
from kuma_core.kuro.polymerase import PolymeraseRegistry
from kuma_core.kuro.sdm_engine import (
    USAGE_WEIGHT,
    OverlapMode,
    design_single_sdm,
)

ORGANISMS = ["ecoli", "bsubtilis", "scerevisiae", "hsapiens", "mextorquens"]
AMINO_ACIDS = sorted(aa for aa in get_codon_table("ecoli") if aa != "*")
SENSE_CODONS = sorted(c for c, aa in CODON_TO_AA.items() if aa != "*")

_DMPR = "fixtures/pSHCE-dmpR.fa"
#: ``tests/conftest.py`` ships this offset for the dmpR design template.
_DMPR_CDS = 1790


def _dmpr(repo_root) -> str:
    text = (repo_root / _DMPR).read_text(encoding="utf-8")
    return "".join(
        line.strip() for line in text.splitlines() if not line.startswith(">")
    ).upper()


@pytest.fixture(scope="module")
def dmpr_template() -> str:
    from pathlib import Path

    return _dmpr(Path(__file__).resolve().parents[1])


def _mutation(seq: str, position: int, mt_aa: str) -> Mutation:
    codon_start = _DMPR_CDS + (position - 1) * 3
    wt_codon = seq[codon_start:codon_start + 3]
    return Mutation(
        raw=f"{codon_to_aa(wt_codon)}{position}{mt_aa}",
        wt_aa=codon_to_aa(wt_codon),
        position=position,
        mt_aa=mt_aa,
        codon_start=codon_start,
        wt_codon=wt_codon,
        mt_codon=wt_codon,
    )


class TestTheFloorHolds:
    """No codon below the floor may reach a design, for any organism."""

    @pytest.mark.parametrize("organism", ORGANISMS)
    def test_no_offered_codon_falls_below_the_floor(self, organism: str):
        """Every (WT codon, target amino acid) pair the engine could ask for.

        The one documented exception is a silent request whose WT codon is the
        only one the host uses often enough; the pool then has nothing above the
        floor left to offer and returns the remainder rather than refusing to
        design. Asserted separately below so it cannot hide a real leak here.
        """
        for aa in AMINO_ACIDS:
            above_floor = [
                codon for codon, freq in get_codon_table(organism)[aa]
                if freq >= CODON_USAGE_FLOOR
            ]
            for wt_codon in SENSE_CODONS:
                offered = mt_codons_for_design(wt_codon, aa, organism=organism)
                if [c for c in above_floor if c != wt_codon]:
                    below = [
                        c for c in offered
                        if codon_usage_fraction(c, organism) < CODON_USAGE_FLOOR
                    ]
                    assert not below, (
                        f"{organism} {wt_codon}->{aa} offers {below}, "
                        f"below the {CODON_USAGE_FLOOR} floor"
                    )

    @pytest.mark.parametrize("organism", ORGANISMS)
    def test_the_pool_is_never_empty(self, organism: str):
        for aa in AMINO_ACIDS:
            for wt_codon in SENSE_CODONS:
                offered = mt_codons_for_design(wt_codon, aa, organism=organism)
                assert offered, f"{organism} {wt_codon}->{aa} offered nothing"
                assert all(codon_to_aa(c) == aa for c in offered)
                assert len(set(offered)) == len(offered)

    def test_a_silent_request_may_fall_through_the_floor(self):
        """The one path that returns a sub-floor codon, stated rather than hidden.

        M. extorquens uses TTC for 0.93 of its Phe and TTT for 0.07. Asking for
        a silent F->F on a TTC codon removes the only codon above the floor, and
        the pool offers the remainder instead of refusing the design. A missense
        request cannot reach this: fractions of one amino acid sum to 1 over at
        most six codons, so its most-used codon always clears 0.10.
        """
        assert codon_usage_fraction("TTC", "mextorquens") >= CODON_USAGE_FLOOR
        assert codon_usage_fraction("TTT", "mextorquens") < CODON_USAGE_FLOOR
        assert mt_codons_for_design("TTC", "F", organism="mextorquens") == ["TTT"]

    def test_a_single_codon_amino_acid_still_answers(self):
        """Met and Trp have one codon each, so a silent request leaves nothing."""
        assert mt_codons_for_design("ATG", "M") == ["ATG"]
        assert mt_codons_for_design("TGG", "W") == ["TGG"]

    def test_the_wt_codon_is_never_offered_back(self):
        for organism in ORGANISMS:
            for wt_codon in SENSE_CODONS:
                aa = codon_to_aa(wt_codon)
                if len(get_codon_table(organism)[aa]) == 1:
                    continue  # Met and Trp, covered above
                offered = mt_codons_for_design(wt_codon, aa, organism=organism)
                assert wt_codon not in offered, (
                    f"{organism} {wt_codon}->{aa} offers the WT codon back"
                )


class TestOrdering:
    """Hamming ascending, then usage descending, then the codon itself."""

    @pytest.mark.parametrize("organism", ORGANISMS)
    def test_the_order_is_the_declared_key(self, organism: str):
        for aa in AMINO_ACIDS:
            for wt_codon in SENSE_CODONS:
                offered = mt_codons_for_design(wt_codon, aa, organism=organism)
                keys = [
                    (
                        sum(a != b for a, b in zip(wt_codon, codon)),
                        -codon_usage_fraction(codon, organism),
                        codon,
                    )
                    for codon in offered
                ]
                assert keys == sorted(keys), (
                    f"{organism} {wt_codon}->{aa} came back as {offered}"
                )

    def test_the_order_is_stable_across_repeated_calls(self):
        first = mt_codons_for_design("AAA", "A", organism="ecoli")
        for _ in range(5):
            assert mt_codons_for_design("AAA", "A", organism="ecoli") == first

    def test_the_strategy_argument_no_longer_orders_anything(self):
        """It ordered a two-element list; there is no two-element list left.

        Kept in the signature because design_single_sdm, diagnose_sdm_failure,
        the sidecar request model, the TypeScript design input and a persisted
        workspace field all pass it.
        """
        for organism in ORGANISMS:
            for wt_codon in ("AAA", "CGG", "GCG", "TTT"):
                for aa in ("A", "R", "L", "S"):
                    assert mt_codons_for_design(
                        wt_codon, aa, strategy="closest", organism=organism
                    ) == mt_codons_for_design(
                        wt_codon, aa, strategy="optimal", organism=organism
                    )

    def test_a_lower_hamming_codon_outranks_a_more_used_one(self):
        """The two keys disagree here, so the case tells them apart.

        E. coli uses GCG most for Ala, but GCG is three changes from AAA and
        GCA is two, so GCA leads. Ordering by usage first would put GCG there.
        """
        offered = mt_codons_for_design("AAA", "A", organism="ecoli")
        assert offered[0] == "GCA"
        assert codon_usage_fraction("GCG", "ecoli") > codon_usage_fraction("GCA", "ecoli")
        assert offered.index("GCA") < offered.index("GCG")


class TestTheRareLandingIsGone:
    """The M. extorquens Leu case the widened pool used to walk into.

    Before the floor, dmpR I472L on M. extorquens with Q5 SDM and partial
    overlap chose TTA: a codon M. extorquens never uses (fraction 0.00) and two
    template mismatches away, while CTC at 0.44 and one mismatch sat in the same
    pool. Nothing in the penalty saw the difference, because the penalty scores
    Tm, GC and nucleotide changes and knows nothing about usage.
    """

    def test_tta_is_not_in_the_m_extorquens_leucine_pool(self):
        assert codon_usage_fraction("TTA", "mextorquens") == 0.0
        pool = mt_codons_for_design("ATC", "L", organism="mextorquens")
        assert "TTA" not in pool
        assert "CTC" in pool

    def test_the_i472l_design_lands_on_ctc(self, dmpr_template):
        mut = _mutation(dmpr_template, 472, "L")
        assert mut.wt_codon == "ATC", "the fixture template moved under this test"
        hits = design_single_sdm(
            dmpr_template,
            mut,
            PolymeraseRegistry().get("Q5 SDM"),
            organism="mextorquens",
            tol_max=4.0,
            overlap_mode="partial",
        )
        assert hits, "no primer designed for the case this test exists for"
        assert hits[0].mutation.mt_codon == "CTC"
        assert codon_usage_fraction(hits[0].mutation.mt_codon, "mextorquens") >= (
            CODON_USAGE_FLOOR
        )

    @pytest.mark.parametrize("organism", ORGANISMS)
    @pytest.mark.parametrize("overlap_mode", ["partial", "full"])
    def test_no_winner_falls_below_the_floor(
        self, dmpr_template, organism: str, overlap_mode: OverlapMode
    ):
        """Nine dmpR substitutions that between them reach eight amino acids."""
        profile = PolymeraseRegistry().get("Q5 SDM")
        cases = [
            (472, "L"), (438, "I"), (297, "R"), (237, "A"),
            (209, "P"), (125, "S"), (211, "S"), (13, "L"), (8, "V"),
        ]
        seen = 0
        for position, mt_aa in cases:
            hits = design_single_sdm(
                dmpr_template,
                _mutation(dmpr_template, position, mt_aa),
                profile,
                organism=organism,
                tol_max=4.0,
                overlap_mode=overlap_mode,
            )
            for hit in hits:
                seen += 1
                fraction = codon_usage_fraction(hit.mutation.mt_codon, organism)
                assert fraction >= CODON_USAGE_FLOOR, (
                    f"{organism} {overlap_mode} position {position}->{mt_aa} "
                    f"returned {hit.mutation.mt_codon} at {fraction}"
                )
        assert seen > 0, "no candidate was examined, so this asserted nothing"


class TestTheUsageTermReachesThePenalty:
    """The fraction has to arrive at the scoring site, not be looked up there."""

    def test_the_weight_is_the_declared_one(self):
        assert USAGE_WEIGHT == 4.0

    @pytest.mark.parametrize("overlap_mode", ["partial", "full"])
    def test_a_rarer_codon_costs_the_declared_amount(
        self, dmpr_template, monkeypatch, overlap_mode: OverlapMode
    ):
        """Same design, same organism, only the usage table moved.

        Halving the winning codon's fraction has to raise its penalty by
        USAGE_WEIGHT * (that difference) and change nothing else, which is only
        true if the term is wired into both branches with the fraction of the
        codon actually chosen.
        """
        import kuma_core.kuro.codon_table as codon_table

        mut = _mutation(dmpr_template, 472, "L")
        profile = PolymeraseRegistry().get("Q5 SDM")
        base = design_single_sdm(
            dmpr_template, mut, profile, organism="ecoli",
            tol_max=4.0, overlap_mode=overlap_mode,
        )
        assert base, "no primer designed"
        winner = base[0]
        original = codon_usage_fraction(winner.mutation.mt_codon, "ecoli")

        real = codon_table.codon_usage_fraction

        def halved(codon: str, organism: str = "ecoli") -> float:
            if codon == winner.mutation.mt_codon:
                return original / 2
            return real(codon, organism)

        monkeypatch.setattr("kuma_core.kuro.sdm_engine.codon_usage_fraction", halved)
        after = design_single_sdm(
            dmpr_template, mut, profile, organism="ecoli",
            tol_max=4.0, overlap_mode=overlap_mode,
        )
        moved = [h for h in after if h.forward_seq == winner.forward_seq]
        assert moved, "the primer under test disappeared from the results"
        assert moved[0].penalty == pytest.approx(
            winner.penalty + USAGE_WEIGHT * original / 2, abs=0.02
        )
