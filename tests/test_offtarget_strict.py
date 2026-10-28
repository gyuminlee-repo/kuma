"""The opt-in strict off-target check and what turning it on changes."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from kuma_core.kuro import sdm_engine as engine
from kuma_core.kuro.codon_table import CODON_TO_AA
from kuma_core.kuro.mutation import Mutation
from kuma_core.kuro.overlap import reverse_complement
from kuma_core.kuro.polymerase import PolymeraseRegistry
from kuma_core.kuro.sdm_engine import (
    STRICT_OFFTARGET_FAILURE_MARKER,
    STRICT_OFFTARGET_REASON,
    check_offtarget_strict,
    design_single_sdm,
    diagnose_sdm_failure,
)

TEMPLATE = Path(__file__).resolve().parents[1] / "fixtures" / "sample_sdm_template.gb"
CDS_START = 1790


@pytest.fixture(scope="module")
def template_seq() -> str:
    _header, seq, _genes = engine.load_sequence(TEMPLATE)
    return seq


@pytest.fixture(scope="module")
def profile():
    return replace(PolymeraseRegistry().get("Q5"))


def _mutation(seq: str, position: int) -> Mutation:
    codon_start = CDS_START + (position - 1) * 3
    wt_codon = seq[codon_start:codon_start + 3]
    wt_aa = CODON_TO_AA[wt_codon]
    mt_aa = "G" if wt_aa == "A" else "A"
    from kuma_core.kuro.codon_table import best_codon

    return Mutation(
        raw=f"{wt_aa}{position}{mt_aa}",
        wt_aa=wt_aa,
        position=position,
        mt_aa=mt_aa,
        codon_start=codon_start,
        wt_codon=wt_codon,
        mt_codon=best_codon(mt_aa, "ecoli"),
    )


class TestDetection:
    def test_an_internal_window_on_the_antisense_strand_is_reported(self) -> None:
        """Neither primer end is aligned, so no 3'-anchored rule can see it."""
        import random

        rng = random.Random(97)
        template = "".join(rng.choice("ACGT") for _ in range(500))
        primer = "ACGTTGCAGGTACCTTAGCCATTGACGTAA"
        planted = reverse_complement(primer[6:22])
        template = template[:100] + planted + template[100 + len(planted):]

        hits = check_offtarget_strict(primer, template, 300, 330)
        assert [(h.strand, h.position, h.match_length, h.truncation_type) for h in hits] == [
            ("antisense", 100, 16, "internal")
        ]
        assert hits[0].reason == STRICT_OFFTARGET_REASON
        assert not hits[0].extendable

    def test_a_match_shorter_than_the_floor_is_not_reported(self) -> None:
        import random

        rng = random.Random(101)
        template = "".join(rng.choice("ACGT") for _ in range(500))
        primer = "ACGTTGCAGGTACCTTAGCCATTGACGTAA"
        planted = primer[8:22]  # 14 nt, one short of the 15 nt floor
        template = template[:120] + planted + template[120 + len(planted):]

        assert check_offtarget_strict(primer, template, 300, 330) == []

    def test_the_primers_own_site_is_excluded(self, template_seq: str) -> None:
        start = 400
        primer = template_seq[start:start + 28]
        hits = check_offtarget_strict(
            primer, template_seq, start, start + len(primer)
        )
        assert hits == [], [(h.strand, h.position) for h in hits]

    def test_a_full_length_match_is_tagged_full(self, template_seq: str) -> None:
        start = 400
        primer = template_seq[start:start + 28]
        hits = check_offtarget_strict(primer, template_seq, 1000, 1040)
        sense = [h for h in hits if h.strand == "sense" and h.position == start]
        assert sense and sense[0].truncation_type == "full"
        assert sense[0].extendable

    def test_an_origin_spanning_match_needs_a_circular_template(self) -> None:
        import random

        rng = random.Random(113)
        core = "".join(rng.choice("ACGT") for _ in range(600))
        primer = "ACGTTGCAGGTACCTTAGCCATTGACGTAA"
        fragment = primer[4:24]  # 20 nt, neither end of the primer
        head = len(fragment) // 2
        tail = len(fragment) - head
        template = (
            fragment[tail:] + core[head:len(core) - tail] + fragment[:tail]
        )

        assert check_offtarget_strict(primer, template, 300, 330) == []
        hits = check_offtarget_strict(
            primer, template, 300, 330, topology="circular"
        )
        assert hits
        for h in hits:
            assert 0 <= h.position < len(template)


class TestSwitchOff:
    def test_results_are_unchanged_and_the_check_is_not_called(
        self, template_seq: str, profile, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mut = _mutation(template_seq, 58)
        baseline = design_single_sdm(template_seq, mut, profile)
        assert baseline, "fixture must yield candidates for this test to mean anything"

        calls: list[str] = []

        def _tripwire(*_a, **_kw):
            calls.append("called")
            return []

        monkeypatch.setattr(engine, "check_offtarget_strict", _tripwire)
        with_flag_off = design_single_sdm(
            template_seq, mut, profile, strict_offtarget=False
        )

        assert calls == [], "the strict check must not run while the switch is off"
        assert len(with_flag_off) == len(baseline)
        for a, b in zip(baseline, with_flag_off):
            assert a == b


class TestSwitchOn:
    def _planted(self, template_seq: str, fragment: str, at: int) -> str:
        return (
            template_seq[:at] + fragment + template_seq[at + len(fragment):]
        )

    def test_a_planted_internal_match_rejects_that_candidate(
        self, template_seq: str, profile
    ) -> None:
        mut = _mutation(template_seq, 58)
        baseline = design_single_sdm(template_seq, mut, profile)
        assert baseline
        target = baseline[0]

        # 16 nt from the middle of the winning forward primer, planted on the
        # antisense strand far from the CDS. It reaches neither primer end, so
        # the default rules have no failure mode to report for it.
        fragment = reverse_complement(target.forward_seq[6:22])
        planted = self._planted(template_seq, fragment, 300)

        off = design_single_sdm(planted, mut, profile, strict_offtarget=False)
        assert any(c.forward_seq == target.forward_seq for c in off), (
            "planting must not change the default verdict"
        )

        on = design_single_sdm(planted, mut, profile, strict_offtarget=True)
        assert not any(c.forward_seq == target.forward_seq for c in on), (
            "the strict check must drop the candidate carrying the planted match"
        )

    def test_without_the_planted_match_nothing_changes(
        self, template_seq: str, profile
    ) -> None:
        mut = _mutation(template_seq, 58)
        off = design_single_sdm(template_seq, mut, profile, strict_offtarget=False)
        on = design_single_sdm(template_seq, mut, profile, strict_offtarget=True)
        assert [c.forward_seq for c in on] == [c.forward_seq for c in off]


class TestFailureReason:
    def test_the_reason_names_the_switch_when_it_is_the_only_cause(
        self, template_seq: str, profile, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Every Tm/length-valid pair is strict-rejected and nothing else is.

        Forced through the strict check itself rather than through a planted
        template, because what is under test is the message the diagnostic
        writes when the switch is the whole cause, and a template that rejects
        every candidate by sequence alone would also trip the default rules.
        """
        mut = _mutation(template_seq, 58)
        assert design_single_sdm(template_seq, mut, profile), "control"

        def _always_hit(primer_seq: str, *_a, **_kw):
            return [engine.OffTargetHit(
                position=7,
                strand="sense",
                match_seq=primer_seq[:15],
                tm=50.0,
                match_length=15,
                truncation_type="internal",
                extendable=False,
                reason=STRICT_OFFTARGET_REASON,
            )]

        monkeypatch.setattr(engine, "check_offtarget_strict", _always_hit)

        assert design_single_sdm(
            template_seq, mut, profile, strict_offtarget=True
        ) == []
        reason = diagnose_sdm_failure(
            template_seq, mut, profile, strict_offtarget=True
        )
        assert STRICT_OFFTARGET_FAILURE_MARKER in reason
        assert "exact-window match" in reason

        # Off, the same position designs, so the diagnostic has nothing to say.
        assert design_single_sdm(
            template_seq, mut, profile, strict_offtarget=False
        )


class TestFootprintMerge:
    def test_a_merged_footprint_reports_one_window(self) -> None:
        """Position, sequence and length come from the same window.

        Two overlapping footprints on one strand: a 15 nt window of the
        primer's 5' end at template 100, and a longer 20 nt window from the
        primer's middle at template 110. They overlap, so they collapse onto
        the longer one, and the hit has to describe that one window rather
        than take its position from the shorter and its sequence from the
        longer.
        """
        import random

        rng = random.Random(5)
        # The two plants overlap on the template, which is what makes them one
        # footprint, so the primer carries a repeated 5-mer and the shared span
        # reads the same from either window.
        repeat = "GTCAG"
        primer = "ACTTG" + repeat + repeat + "GATCCTTAGCCATTA"
        assert len(primer) == 30
        template = list("".join(rng.choice("ACGT") for _ in range(400)))
        template[100:115] = list(primer[0:15])
        template[110:130] = list(primer[5:25])
        seq = "".join(template)
        assert seq[100:115] == primer[0:15]
        assert seq[110:130] == primer[5:25]

        hits = [
            h for h in check_offtarget_strict(primer, seq, 300, 340)
            if h.strand == "sense"
        ]
        assert len(hits) == 1, [(h.position, h.match_length) for h in hits]
        hit = hits[0]
        assert hit.match_length == len(hit.match_seq)
        assert seq[hit.position:hit.position + hit.match_length] == hit.match_seq


class TestWholePeriodIntendedSite:
    def test_an_intended_span_covering_the_template_leaves_nothing(self) -> None:
        """A primer that wraps the whole plasmid has no site but its own.

        The intended span is then at least one full period long, so every
        candidate site overlaps it on the circle and both checks report
        nothing. That is the answer the circle gives, not a gap: there is no
        position on the template that is outside the intended site.
        """
        template = "ACGTACGTACGTACGTACGTAC"
        primer = (template * 2)[:30]
        assert len(primer) > len(template)

        assert engine.check_offtarget(
            primer, template, 0, len(primer), topology="circular"
        ) == []
        assert check_offtarget_strict(
            primer, template, 0, len(primer), topology="circular"
        ) == []
        assert engine._overlaps_intended(5, 10, 0, len(template), len(template), True)
