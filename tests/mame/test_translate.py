"""Translate/diff unit tests (normal, silent, missense)."""

from __future__ import annotations

from pathlib import Path

import pytest

from kuma_core.mame.models import BarcodeRecord
from kuma_core.mame.translate import extract_aa_changes, translate_and_diff


def _br(seq: str, size_kb: float = 60.0) -> BarcodeRecord:
    return BarcodeRecord(
        native_barcode="NB01",
        custom_barcode="1_1",
        consensus_seq=seq,
        file_size_kb=size_kb,
        source_path=Path("/tmp/mock.fasta"),
    )


def test_translate_normal_passthrough(reference_seq: str, cds_params: dict[str, int]) -> None:
    """Identical query -> no AA changes, AA sequence length matches CDS / 3."""

    rec = _br(reference_seq)
    translated = translate_and_diff(
        record=rec,
        reference_seq=reference_seq,
        cds_start=cds_params["cds_start"],
        cds_end=cds_params["cds_end"],
    )
    assert translated.observed_aa_changes == []
    # Literal reference is 177 bp = 59 codons (58 AA + trailing stop).
    assert len(translated.aa_sequence) >= 50


def test_translate_silent_substitution(reference_seq: str, cds_params: dict[str, int]) -> None:
    """Synonymous codon swap: codon 2 GTG -> GTT (both Val) yields no AA diff."""

    # Codon 2 occupies ref[3:6] and is GTG (Val) in the literal reference.
    assert reference_seq[3:6] == "GTG"
    mutated = reference_seq[:3] + "GTT" + reference_seq[6:]
    rec = _br(mutated)
    translated = translate_and_diff(
        record=rec,
        reference_seq=reference_seq,
        cds_start=cds_params["cds_start"],
        cds_end=cds_params["cds_end"],
    )
    assert translated.observed_aa_changes == []


def test_translate_missense_v2f(reference_seq: str, cds_params: dict[str, int]) -> None:
    """Codon 2 GTG -> TTT = V2F substitution on the literal reference."""

    assert reference_seq[3:6] == "GTG"
    mutated = reference_seq[:3] + "TTT" + reference_seq[6:]
    rec = _br(mutated)
    translated = translate_and_diff(
        record=rec,
        reference_seq=reference_seq,
        cds_start=cds_params["cds_start"],
        cds_end=cds_params["cds_end"],
    )
    assert "V2F" in translated.observed_aa_changes


def test_translate_no_spurious_indel_past_cds_end(
    reference_seq: str, cds_params: dict[str, int]
) -> None:
    """Regression: when the reference is longer than the CDS (e.g. a SnapGene /
    GenBank plasmid map carrying backbone/UTR), a clean well whose consensus
    equals the full reference must NOT emit a {pos}_INDEL for every base past
    cds_end. Those spurious INDELs previously tripped _has_frameshift and
    mislabeled clean wells FRAMESHIFT."""

    cds_end = cds_params["cds_end"]
    assert cds_end == len(reference_seq)  # fixture reference IS the bare CDS
    extended_ref = reference_seq + "ACGT" * 20  # 80 bp of out-of-CDS backbone
    # Clean consensus == the full extended reference (CDS + backbone intact).
    rec = _br(extended_ref)
    translated = translate_and_diff(
        record=rec,
        reference_seq=extended_ref,
        cds_start=cds_params["cds_start"],
        cds_end=cds_end,  # strictly less than len(extended_ref)
    )
    assert translated.observed_aa_changes == []
    # The NT diff must be bounded to [cds_start, cds_end): no trailing INDELs.
    assert translated.observed_nt_changes == []
    assert not any("INDEL" in c for c in translated.observed_nt_changes)


def test_translate_n_codon_is_no_call_not_mutation(
    reference_seq: str, cds_params: dict[str, int]
) -> None:
    """An N-bearing codon translates to ambiguous 'X' (no-call): it is excluded
    from observed_aa_changes (so it neither floods the table nor inflates the
    MANY count) and is counted in n_no_call_aa instead."""

    assert reference_seq[3:6] == "GTG"  # codon 2 = Val
    mutated = reference_seq[:3] + "NNN" + reference_seq[6:]
    rec = _br(mutated)
    translated = translate_and_diff(
        record=rec,
        reference_seq=reference_seq,
        cds_start=cds_params["cds_start"],
        cds_end=cds_params["cds_end"],
    )
    assert translated.observed_aa_changes == []
    assert all(not c.endswith("X") for c in translated.observed_aa_changes)
    assert translated.n_no_call_aa == 1


def test_consensus_too_short_for_the_cds_window_is_refused() -> None:
    """A consensus that cannot cover the CDS must not be diffed.

    Consensus sequences carry one base per reference position, so a consensus
    ending before cds_end cannot have come from this reference. On 2026-08-04 a
    resumed run diffed 1,683 bp consensus files (CDS-scoped) against a 1,715 bp
    amplicon whose CDS ends at 1,699 and reported about 530 amino-acid changes
    per well. Reinterpreting the shorter sequence would hide that; refusing it
    names the problem.
    """
    codons = ["ATG", "GCT", "TGC", "TCT", "GTA", "TCC", "ACT", "TAA"]
    cds = "".join(codons)
    left_tail = "CACAGGAGGTTAAACC"
    right_tail = "TGCGTTGCGCTCTAG"
    reference = left_tail + cds + right_tail
    cds_start = len(left_tail)
    cds_end = cds_start + len(cds)

    with pytest.raises(ValueError) as excinfo:
        translate_and_diff(
            record=_br(cds),
            reference_seq=reference,
            cds_start=cds_start,
            cds_end=cds_end,
        )

    message = str(excinfo.value)
    assert f"consensus {len(cds)} bp" in message
    assert f"reference {len(reference)} bp" in message
    assert f"CDS ending at {cds_end}" in message
    assert "reused" in message

    # The same consensus in reference coordinates is diffed normally.
    mutated_cds = cds[:12] + "ATA" + cds[15:]
    translated = translate_and_diff(
        record=_br(left_tail + mutated_cds + right_tail),
        reference_seq=reference,
        cds_start=cds_start,
        cds_end=cds_end,
    )
    assert translated.observed_aa_changes == ["V5I"]


def test_consensus_longer_than_the_reference_is_still_diffed() -> None:
    """Trailing sequence past the CDS is an insertion, not a coordinate error.

    An externally supplied consensus may run past the reference; the query is
    bounded to the CDS window, so the refusal above must not catch this.
    """
    codons = ["ATG", "GCT", "TGC", "TCT", "GTA", "TCC", "ACT", "TAA"]
    cds = "".join(codons)
    mutated = cds[:12] + "ATA" + cds[15:]
    translated = translate_and_diff(
        record=_br(mutated + "CC"),
        reference_seq=cds,
        cds_start=0,
        cds_end=len(cds),
    )
    assert translated.observed_aa_changes == ["V5I"]


def test_bare_cds_reference_is_diffed_normally(
    reference_seq: str, cds_params: dict[str, int]
) -> None:
    """cds_start 0 over a reference that IS the CDS stays untouched."""
    mutated = reference_seq[:3] + "TTT" + reference_seq[6:]
    translated = translate_and_diff(
        record=_br(mutated),
        reference_seq=reference_seq,
        cds_start=cds_params["cds_start"],
        cds_end=cds_params["cds_end"],
    )
    assert translated.observed_aa_changes == ["V2F"]


def test_extract_aa_changes_basic() -> None:
    assert extract_aa_changes("MVFK", "MVFK") == []
    assert extract_aa_changes("MFFK", "MVFK") == ["V2F"]
    assert extract_aa_changes("MV", "MVFK") == ["F3-", "K4-"]
