"""Phase 1 (core) tests for MAME well-layout: build_draft_layout + WT-aware scoping.

Covers:
- build_draft_layout column-major order, WT placement, and 96-well clamping.
- well_layout injection into run_analyze: mutant wells scoped by ground truth,
  WT well carries an empty expected scope (clean -> PASS, variant -> fail), and a
  contaminated WT well is NOT mis-grouped into a real mutant's replicate group.

Self-contained fixtures; no minimap2 dependency (barcode-mode FASTA ingest).
"""

from __future__ import annotations

from pathlib import Path

import openpyxl
import pytest

from kuma_core.mame.ingest import IngestMode
from kuma_core.mame.layout import build_draft_layout
from kuma_core.mame.models import ExpectedMutation, VerdictClass
from kuma_core.mame.pipeline import _norm_well, run_analyze

# Reference ATG GGG TTT -> M G F (9 bp, table 11).
_REFERENCE_NT = "ATGGGGTTT"
# Well A02 (custom_barcode "1_2"): G2A -> M A F
_G2A_NT = "ATGGCGTTT"
# Well B01 (custom_barcode "2_1"): F3W -> M G W
_F3W_NT = "ATGGGGTGG"
# Clean WT consensus == reference -> M G F
_WT_NT = "ATGGGGTTT"
_PAD = "\n" * (52 * 1024)


def _em(mutant_id: str, position: int, wt_aa: str, mt_aa: str) -> ExpectedMutation:
    return ExpectedMutation(
        mutant_id=mutant_id, position=position, wt_aa=wt_aa, mt_aa=mt_aa,
        wt_codon="", mt_codon="", group_id="", primer_set_ref="",
        notation_type="substitution", status="DESIGNED",
    )


# ---------------------------------------------------------------------------
# build_draft_layout
# ---------------------------------------------------------------------------

def test_build_draft_layout_column_major_order_and_wt_position() -> None:
    """well 1..N column-major -> mutant_id; well N+1 -> WT."""
    expected = [_em("M1", 1, "A", "B"), _em("M2", 2, "C", "D"), _em("M3", 3, "E", "F")]
    layout = build_draft_layout(expected)
    # seq 1->A1, 2->B1, 3->C1 (column-major), WT at seq 4 -> D1
    assert layout["A1"] == "M1"
    assert layout["B1"] == "M2"
    assert layout["C1"] == "M3"
    assert layout["D1"] == "WT"
    assert len(layout) == 4


def test_build_draft_layout_wt_omitted_at_full_plate() -> None:
    """N == 96: every well is a mutant, WT well (97) is omitted."""
    expected = [_em(f"M{i}", i, "A", "B") for i in range(1, 97)]
    layout = build_draft_layout(expected)
    assert len(layout) == 96
    assert "WT" not in layout.values()


def test_build_draft_layout_clamps_mutants_above_96() -> None:
    """N > 96: only the first 96 mutants are placed, WT omitted."""
    expected = [_em(f"M{i}", i, "A", "B") for i in range(1, 110)]
    layout = build_draft_layout(expected)
    assert len(layout) == 96
    assert "WT" not in layout.values()
    assert layout["A1"] == "M1"


# ---------------------------------------------------------------------------
# well_layout injection into run_analyze
# ---------------------------------------------------------------------------

def _write_fasta(path: Path, header: str, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f">{header}\n{body}\n{_PAD}", encoding="utf-8")


def _make_kuro_xlsx(dest: Path) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Fwd List"
    ws.append(["Well", "Primer Name", "Sequence", "Length", "Tm", "Tm_Overlap",
               "WT_Codon", "MT_Codon", "Mutation"])
    ws2 = wb.create_sheet("expected_mutations")
    ws2.append(["mutant_id", "position", "wt_aa", "mt_aa", "wt_codon", "mt_codon",
                "group_id", "primer_set_ref", "notation_type", "status"])
    ws2.append(["G2A", 2, "G", "A", "GGG", "GCG", "", "G2A", "substitution", "DESIGNED"])
    ws2.append(["F3W", 3, "F", "W", "TTT", "TGG", "", "F3W", "substitution", "DESIGNED"])
    dest.parent.mkdir(parents=True, exist_ok=True)
    wb.save(dest)


def _make_reference_fasta(tmp_path: Path) -> Path:
    ref = tmp_path / "reference.fasta"
    ref.write_text(f">ref\n{_REFERENCE_NT}\n", encoding="utf-8")
    return ref


def test_well_layout_scopes_mutant_wells_and_clean_wt_passes(tmp_path: Path) -> None:
    """well_layout injection: mutant wells scoped (PASS), clean WT well PASSes.

    Layout: A02 -> G2A, B01 -> F3W, C01 -> WT.
      custom_barcode "1_2" -> seq 9 -> A2;  "2_1" -> seq 2 -> B1;  "3_1" -> seq 3 -> C1
    """
    ingest = tmp_path / "consensus"
    _write_fasta(ingest / "NB01" / "1_2.fasta", "1_2", _G2A_NT)   # A02 G2A
    _write_fasta(ingest / "NB01" / "2_1.fasta", "2_1", _F3W_NT)   # B01 F3W
    _write_fasta(ingest / "NB01" / "3_1.fasta", "3_1", _WT_NT)    # C01 WT (clean)
    reference = _make_reference_fasta(tmp_path)
    kuro = tmp_path / "kuro.xlsx"
    _make_kuro_xlsx(kuro)

    well_layout = {"A2": "G2A", "B1": "F3W", "C1": "WT"}

    verdicts, _ = run_analyze(
        input_dir=ingest, reference_path=reference, expected_path=kuro,
        output_path=tmp_path / "out.xlsx", cds_start=0, cds_end=9,
        min_file_size_kb=0.0, ingest_mode=IngestMode.BARCODE, well_layout=well_layout,
    )
    by_custom = {v.translated.barcode.custom_barcode: v for v in verdicts}
    assert by_custom["1_2"].verdict is VerdictClass.PASS, by_custom["1_2"].verdict_notes
    assert by_custom["2_1"].verdict is VerdictClass.PASS, by_custom["2_1"].verdict_notes
    # WT well scoped to [] (empty expected); clean consensus == reference -> PASS.
    wt = by_custom["3_1"]
    assert wt.expected_mutations == [], wt.expected_mutations
    assert wt.verdict is VerdictClass.PASS, wt.verdict_notes


def test_well_layout_wt_well_with_variant_fails_and_not_mis_grouped(tmp_path: Path) -> None:
    """A WT well observing a variant at a real mutant's position must fail AND must
    not be grouped under that mutant (ground-truth attribution beats the heuristic)."""
    ingest = tmp_path / "consensus"
    # WT well C01 is contaminated with G2A (matches mutant G2A's position 2).
    _write_fasta(ingest / "NB01" / "3_1.fasta", "3_1", _G2A_NT)   # C01 declared WT, observes G2A
    reference = _make_reference_fasta(tmp_path)
    kuro = tmp_path / "kuro.xlsx"
    _make_kuro_xlsx(kuro)

    well_layout = {"C1": "WT"}

    verdicts, replicates = run_analyze(
        input_dir=ingest, reference_path=reference, expected_path=kuro,
        output_path=tmp_path / "out.xlsx", cds_start=0, cds_end=9,
        min_file_size_kb=0.0, ingest_mode=IngestMode.BARCODE, well_layout=well_layout,
    )
    wt = verdicts[0]
    assert wt.expected_mutations == []
    # Empty expected + observed variant -> not a PASS (WRONG_AA: unexpected extra).
    assert wt.verdict is not VerdictClass.PASS, wt.verdict_notes
    # Must NOT be grouped under the real mutant G2A; ground truth pins it to "WT".
    mutant_ids = {r.mutant_id for r in replicates}
    assert "G2A" not in mutant_ids, (
        f"contaminated WT well mis-grouped into G2A; groups={mutant_ids}"
    )
    assert "WT" in mutant_ids, f"WT well not attributed to WT group; groups={mutant_ids}"
