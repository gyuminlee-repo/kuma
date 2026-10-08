"""Placement-overrides-observation unit test for _assign_mutant_ids (PR #50 follow-up).

Discriminating property: when well_to_mutant is provided, a well is attributed to
the mutant PLACED there (sample_map ground truth) even when its consensus OBSERVES
a DIFFERENT mutant.  Without well_to_mutant the existing 4-step heuristic (step 1:
direct label match) governs instead.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import pytest

from kuma_core.mame.models import (
    BarcodeRecord,
    ExpectedMutation,
    TranslatedRecord,
    VerdictClass,
    VerdictRecord,
)
from kuma_core.mame.pipeline import _assign_mutant_ids, _norm_well


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_barcode(custom_barcode: str, native_barcode: str = "NB01") -> BarcodeRecord:
    return BarcodeRecord(
        native_barcode=native_barcode,
        custom_barcode=custom_barcode,
        consensus_seq="",
        file_size_kb=60.0,
        source_path=Path("/tmp/mock.fasta"),
    )


def _make_verdict(
    custom_barcode: str,
    observed_aa: list[str],
    native_barcode: str = "NB01",
) -> VerdictRecord:
    barcode = _make_barcode(custom_barcode, native_barcode)
    translated = TranslatedRecord(
        barcode=barcode,
        aa_sequence="",
        observed_nt_changes=[],
        observed_aa_changes=observed_aa,
    )
    # Verdict class is not evaluated by _assign_mutant_ids (grouping only).
    return VerdictRecord(
        translated=translated,
        expected_mutations=observed_aa,
        verdict=VerdictClass.PASS,
        verdict_notes="",
    )


def _make_expected(mutant_id: str, pos: int, wt: str, mt: str) -> ExpectedMutation:
    return ExpectedMutation(
        mutant_id=mutant_id,
        position=pos,
        wt_aa=wt,
        mt_aa=mt,
        wt_codon="XXX",
        mt_codon="YYY",
        group_id="",
        primer_set_ref=mutant_id,
        notation_type="substitution",
        status="DESIGNED",
    )


# ---------------------------------------------------------------------------
# Discriminating test
# ---------------------------------------------------------------------------

def test_placement_overrides_observation() -> None:
    """The core discriminating assertion.

    Setup
    -----
    - Well A02 (custom_barcode "1_2" -> seq=9 -> seq_to_well -> "A2" -> _norm_well -> "A02")
      PLACED as G2A in sample_map.
      OBSERVES F3W (a different mutant at a different position).

    - Both G2A (pos 2) and F3W (pos 3) are present in `expected`, so step-1
      direct-label-match in the observation path will cleanly attribute the record
      to F3W (observed).  The placement path must override this.

    Assertions
    ----------
    WITH well_to_mutant  -> grouped["G2A"] contains the record (placement wins).
    WITHOUT well_to_mutant -> grouped["F3W"] contains the record (observation wins,
                               step-1 direct match, backward compat unchanged).
    """
    # custom_barcode "1_2": _custom_barcode_to_seq -> seq=(2-1)*8+1=9
    # seq_to_well(9) -> "A2", _norm_well -> "A02"
    vr_placed_g2a_observes_f3w = _make_verdict(
        custom_barcode="1_2",
        observed_aa=["F3W"],          # observes F3W
    )

    expected = [
        _make_expected("G2A", 2, "G", "A"),  # placed mutant
        _make_expected("F3W", 3, "F", "W"),  # observed mutant (different position)
    ]

    # ── WITH placement map: G2A must receive the record ──────────────────────
    well_to_mutant = {_norm_well("A02"): "G2A"}
    grouped_with = _assign_mutant_ids(
        [vr_placed_g2a_observes_f3w], expected, well_to_mutant=well_to_mutant
    )
    assert vr_placed_g2a_observes_f3w in grouped_with["G2A"], (
        "With well_to_mutant, A02 placed as G2A must be grouped under 'G2A' "
        f"regardless of observed F3W; keys found: {list(grouped_with.keys())}"
    )
    assert "F3W" not in grouped_with or vr_placed_g2a_observes_f3w not in grouped_with["F3W"], (
        "The record must NOT appear under observed mutant F3W when placement is active."
    )

    # ── WITHOUT placement map: F3W must receive the record (step-1 label match) ─
    grouped_without = _assign_mutant_ids([vr_placed_g2a_observes_f3w], expected)
    assert vr_placed_g2a_observes_f3w in grouped_without["F3W"], (
        "Without well_to_mutant, observed label 'F3W' in expected -> step-1 match "
        f"must group under 'F3W'; keys found: {list(grouped_without.keys())}"
    )
    assert "G2A" not in grouped_without or vr_placed_g2a_observes_f3w not in grouped_without["G2A"], (
        "The record must NOT appear under G2A when no placement map is given."
    )


# ---------------------------------------------------------------------------
# Backward-compat: well_to_mutant=None preserves existing heuristics
# ---------------------------------------------------------------------------

def test_no_placement_map_uses_observation_heuristics() -> None:
    """Explicit backward-compat check: None well_to_mutant = old behaviour."""
    vr_g2a = _make_verdict(custom_barcode="1_2", observed_aa=["G2A"])
    vr_f3w = _make_verdict(custom_barcode="2_1", observed_aa=["F3W"])

    expected = [
        _make_expected("G2A", 2, "G", "A"),
        _make_expected("F3W", 3, "F", "W"),
    ]

    grouped = _assign_mutant_ids([vr_g2a, vr_f3w], expected, well_to_mutant=None)
    assert vr_g2a in grouped["G2A"], "G2A-observing record must land in G2A group."
    assert vr_f3w in grouped["F3W"], "F3W-observing record must land in F3W group."


# ---------------------------------------------------------------------------
# Non-R_F barcode falls through to heuristics even when map is present
# ---------------------------------------------------------------------------

def test_non_rf_barcode_falls_through_to_heuristics() -> None:
    """A custom_barcode that _custom_barcode_to_seq cannot decode -> heuristic fallback."""
    # "UNKNOWN_BC" is not in R_F format; _custom_barcode_to_seq returns None.
    vr = _make_verdict(custom_barcode="UNKNOWN_BC", observed_aa=["G2A"])

    expected = [_make_expected("G2A", 2, "G", "A")]

    well_to_mutant = {"A02": "G2A"}   # map is present but can't resolve this barcode
    grouped = _assign_mutant_ids([vr], expected, well_to_mutant=well_to_mutant)
    # Falls through to step-1 direct label match -> G2A
    assert vr in grouped["G2A"], (
        "Non-decodable barcode must fall through to heuristics (step-1 label match)."
    )

# ---------------------------------------------------------------------------
# Per-record mutant_id is well-scoped, not native-barcode-collapsed
# ---------------------------------------------------------------------------

def test_per_record_mutant_id_is_well_scoped_across_native_barcodes() -> None:
    """Regression (combinatorial-sort variant-id duplication).

    A sorting run puts the SAME well in many native barcodes (sort bins). Each
    verdict record's ``.mutant_id`` must reflect the well's placed sample
    (sample_map ground truth) and be identical across native barcodes — never
    collapsed onto a single mutant per native_barcode (the old verdict-table
    bug, where every well in a sort bin showed one duplicated variant id).
    """
    from kuma_core.mame.export.excel_writer import _custom_barcode_to_seq
    from kuma_core.mame.export.well_mapper import seq_to_well

    def well_of(custom: str) -> str:
        seq = _custom_barcode_to_seq(custom)
        assert seq is not None
        return _norm_well(seq_to_well(seq))

    nbs = ["sort_barcode06", "sort_barcode20"]
    placed = {"1_1": "V5F", "1_10": "R477Q"}
    records = [
        _make_verdict(custom_barcode=cb, observed_aa=[mut], native_barcode=nb)
        for nb in nbs
        for cb, mut in placed.items()
    ]

    expected = [
        _make_expected("V5F", 5, "V", "F"),
        _make_expected("R477Q", 477, "R", "Q"),
    ]
    well_to_mutant = {well_of(cb): mut for cb, mut in placed.items()}

    _assign_mutant_ids(records, expected, well_to_mutant=well_to_mutant)

    # 1) Every record carries its own well's placed sample, regardless of bin.
    for vr in records:
        cb = vr.translated.barcode.custom_barcode
        assert vr.mutant_id == placed[cb], (
            f"well {cb} in {vr.translated.barcode.native_barcode}: "
            f"mutant_id={vr.mutant_id!r}, expected {placed[cb]!r}"
        )

    # 2) The user's invariant: within each native barcode, the number of distinct
    #    variant ids equals the number of distinct wells — no duplication.
    for nb in nbs:
        nb_recs = [r for r in records if r.translated.barcode.native_barcode == nb]
        distinct_wells = {r.translated.barcode.custom_barcode for r in nb_recs}
        distinct_variants = {r.mutant_id for r in nb_recs}
        assert len(distinct_variants) == len(distinct_wells) == 2, (
            f"{nb}: {len(distinct_variants)} variant ids for "
            f"{len(distinct_wells)} wells (expected equal — no duplication)"
        )
