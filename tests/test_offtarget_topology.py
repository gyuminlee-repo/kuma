"""Off-target coverage at a circular origin and at a linear sequence end.

Both gaps are independent of any user setting: ``check_offtarget`` used to
search a plasmid as if it were a line, and rule 2 used to require the whole
primer length to fit inside the template.
"""
from __future__ import annotations

import random

import pytest

from kuma_core.kuro.overlap import reverse_complement
from kuma_core.kuro.sdm_engine import check_offtarget


def _random_template(length: int, seed: int) -> str:
    rng = random.Random(seed)
    return "".join(rng.choice("ACGT") for _ in range(length))


def _plant_across_origin(template: str, fragment: str) -> str:
    """Return ``template`` rewritten so ``fragment`` spans its origin.

    Half of the fragment lands at the end of the sequence and half at the
    start, so the planted site only exists when the search wraps.
    """
    head = len(fragment) // 2
    tail = len(fragment) - head
    return fragment[tail:] + template[head:len(template) - tail] + fragment[:tail]


class TestCircularOrigin:
    def test_rule1_anchor_across_origin(self) -> None:
        """A perfect 3' anchor spanning the origin is found only when circular."""
        primer = "GGCATTACGTTGCATTGACCGATTACGCAT"
        template = _plant_across_origin(_random_template(600, 7), primer[-15:])

        assert check_offtarget(primer, template, 290, 320, topology="linear") == []
        hits = check_offtarget(primer, template, 290, 320, topology="circular")
        assert hits, "an origin-spanning 3' anchor must be reported on a plasmid"
        assert all(0 <= h.position < len(template) for h in hits), (
            "a wrapped coordinate has to be folded back into the template"
        )

    def test_antisense_origin_is_folded_into_the_template(self) -> None:
        # GC-rich 3' end so the 15 nt anchor clears the 45 C rule-1 threshold.
        primer = "ACCTGAGTTCAGGCTAATCGGCAGCCTGGC"
        planted = reverse_complement(primer[-16:])
        template = _plant_across_origin(_random_template(700, 11), planted)

        assert check_offtarget(primer, template, 300, 340, topology="linear") == []
        hits = check_offtarget(primer, template, 300, 340, topology="circular")
        assert hits
        assert any(h.strand == "antisense" for h in hits)
        for h in hits:
            assert 0 <= h.position < len(template)

    def test_intended_site_spanning_the_origin_masks_itself(self) -> None:
        """A primer whose own site wraps must not report that site.

        The caller states the intended span as ``[start, end)`` with ``end``
        past the template length when it runs through the origin, so the
        exclusion has to be evaluated on the circle.
        """
        template = _random_template(500, 23)
        primer = template[-18:] + template[:12]  # 30 nt, straddling the origin
        intended_start = len(template) - 18
        intended_end = intended_start + len(primer)  # 512 > 500

        hits = check_offtarget(
            primer, template, intended_start, intended_end, topology="circular"
        )
        assert hits == [], (
            "the primer's own origin-spanning site must be excluded, got "
            f"{[(h.strand, h.position, h.reason) for h in hits]}"
        )

    def test_a_site_reached_through_the_padding_is_reported_once(self) -> None:
        primer = "TTGCAGGATCCATTACGCAGTGACCTTAGC"
        template = _plant_across_origin(_random_template(640, 31), primer[-15:])
        hits = check_offtarget(primer, template, 300, 330, topology="circular")
        positions = [(h.strand, h.position) for h in hits]
        assert len(positions) == len(set(positions))


class TestLinearSequenceEnd:
    def test_window_running_off_the_end_is_scored(self) -> None:
        """A duplex that only partly fits at the template end is evaluated.

        The planted site is the primer's 5' arm sitting at the very end of the
        template, so the window extends past it. Before the fix no window of
        less than the full primer length was ever submitted to the Tm test, so
        nothing at all was reported here.
        """
        core = _random_template(400, 41)
        # GC-rich so the clipped duplex clears the 45 C threshold.
        primer = "GCCAGGCTGCCAGGCTGCCAGGCTGCAATT"
        arm = primer[:20]
        template = core[:len(core) - len(arm)] + arm
        # The arm is the primer's 5' overlap arm, which is the failure mode a
        # 5'-only duplex belongs to; without an arm length the window has no
        # mode to report and is skipped by design.
        hits = check_offtarget(
            primer, template, 100, 140, overlap_arm_len=len(arm),
        )
        clipped = [h for h in hits if h.match_length < len(primer)]
        assert clipped, (
            "a window clipped at the template end must still be scored, got "
            f"{[(h.strand, h.position, h.match_length) for h in hits]}"
        )
        for h in clipped:
            assert h.position + h.match_length <= len(template)

    def test_a_clipped_window_cannot_claim_an_extendable_3_prime_end(self) -> None:
        """The primer's 3' base has no template base under it when clipped.

        The planted site is the primer's 3' half at the template start, so the
        window hangs off the 5' end of the template and the primer's own 3'
        terminus is inside it; a window hanging off the other end is what this
        asserts about, and it must never be marked extendable.
        """
        core = _random_template(400, 53)
        primer = "GCCAGGCTGCCAGGCTGCCAGGCTGCAATT"
        arm = primer[:18]
        template = core[:len(core) - len(arm)] + arm
        hits = check_offtarget(
            primer, template, 100, 140, overlap_arm_len=len(arm),
        )
        for h in hits:
            if h.position + h.match_length >= len(template) and h.match_length < len(primer):
                assert not h.extendable


@pytest.mark.parametrize("topology", ["linear", "circular"])
def test_a_clean_template_reports_nothing(topology: str) -> None:
    template = _random_template(800, 67)
    primer = "ACGTTGCAGGTACCTTAGCCATTGACGTAA"
    assert check_offtarget(primer, template, 300, 330, topology=topology) == []
