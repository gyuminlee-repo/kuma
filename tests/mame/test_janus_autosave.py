"""The Janus mapping is written when the analysis finishes, not on demand.

A run produces two artefacts: the result workbook and the Janus mapping that
tells the robot which stock to pick. Until now only the first was written
automatically and the second waited behind a dialog, so a run could finish with
nothing to hand the instrument.

Three properties are pinned here, and the second and third matter more than the
first: an empty mapping must not be written (an empty file reads like a finished
plate), and a mapping that cannot be built must not cost the analysis, which by
then has already run to completion.

Fixtures are self-contained barcode-mode consensus FASTA, shared byte-for-byte
with ``test_analyze_liveness``: no minimap2 needed.
"""

from __future__ import annotations

import csv
from pathlib import Path

import openpyxl
import pytest

# Reference ATG GGG TTT -> M G F (9 bp, table 11).
_REFERENCE_NT = "ATGGGGTTT"
_G2A_NT = "ATGGCGTTT"  # well A02, custom_barcode "1_2"
_F3W_NT = "ATGGGGTGG"  # well B01, custom_barcode "2_1"
_PAD = "\n" * (52 * 1024)

# The liquid class has no default: it sets the pipetting behaviour of the robot,
# so the export refuses to write without one. Every test that expects a file has
# to name it, exactly as the operator does in the dialog.
_LIQUID_CLASS = "cell_stock_100"


def _write_fasta(path: Path, header: str, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f">{header} depth=100\n{body}\n{_PAD}", encoding="utf-8")


def _make_kuro_xlsx(dest: Path) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "expected_mutations"
    ws.append(["mutant_id", "position", "wt_aa", "mt_aa", "wt_codon", "mt_codon",
               "group_id", "primer_set_ref", "notation_type", "status"])
    ws.append(["G2A", 2, "G", "A", "GGG", "GCG", "", "G2A", "substitution", "DESIGNED"])
    ws.append(["F3W", 3, "F", "W", "TTT", "TGG", "", "F3W", "substitution", "DESIGNED"])
    dest.parent.mkdir(parents=True, exist_ok=True)
    wb.save(dest)
    return dest


def _make_reference_fasta(tmp_path: Path) -> Path:
    ref = tmp_path / "reference.fasta"
    ref.write_text(f">ref\n{_REFERENCE_NT}\n", encoding="utf-8")
    return ref


def _run(tmp_path: Path, bodies: dict[str, str], **extra) -> dict:
    """Run ``handle_analyze`` over one well per entry of *bodies*."""
    ingest = tmp_path / "consensus"
    for barcode, body in bodies.items():
        _write_fasta(ingest / "NB01" / f"{barcode}.fasta", barcode, body)
    from sidecar_mame.handlers.analyze import handle_analyze

    return handle_analyze(
        {
            "input_dir": str(ingest),
            "reference": str(_make_reference_fasta(tmp_path)),
            "expected": str(_make_kuro_xlsx(tmp_path / "kuro.xlsx")),
            "output": str(tmp_path / "260804_ref_MAME.xlsx"),
            "cds_start": 0,
            "cds_end": 9,
            "min_file_size_kb": 0.0,
            "ingest_mode": "barcode",
            **extra,
        }
    )


def test_janus_mapping_is_written_next_to_the_result_workbook(tmp_path: Path) -> None:
    """Same folder, same stem as the workbook, so one run reads as one run."""
    result = _run(
        tmp_path,
        {"1_2": _G2A_NT, "2_1": _F3W_NT},
        janus_settings={"liquid_class": _LIQUID_CLASS},
    )

    autosave = result["janus_autosave"]
    assert autosave["status"] == "saved", autosave
    written = Path(autosave["output_path"])
    assert written == tmp_path / "260804_ref_MAME_janus.csv"
    assert written.exists()
    assert autosave["format"] == "csv"


def test_autosaved_mapping_carries_only_the_selected_replicate(tmp_path: Path) -> None:
    """Three copies of one mutant contribute the one pick, not three rows.

    Well ``2_1`` is B1, the layout position the draft assigns to F3W, so all
    three plates carry the same declared mutant and the selector has a real
    choice to make.
    """
    ingest = tmp_path / "consensus"
    for plate in ("NB01", "NB02", "NB03"):
        _write_fasta(ingest / plate / "2_1.fasta", "2_1", _F3W_NT)
    from sidecar_mame.handlers.analyze import handle_analyze

    result = handle_analyze(
        {
            "input_dir": str(ingest),
            "reference": str(_make_reference_fasta(tmp_path)),
            "expected": str(_make_kuro_xlsx(tmp_path / "kuro.xlsx")),
            "output": str(tmp_path / "260804_ref_MAME.xlsx"),
            "cds_start": 0,
            "cds_end": 9,
            "min_file_size_kb": 0.0,
            "ingest_mode": "barcode",
            "janus_settings": {"liquid_class": _LIQUID_CLASS},
        }
    )

    autosave = result["janus_autosave"]
    assert autosave["status"] == "saved", autosave
    assert autosave["row_count"] == 1
    with open(autosave["output_path"], newline="", encoding="utf-8-sig") as handle:
        body = [row for row in csv.reader(handle) if row and any(c.strip() for c in row)]
    # Header plus exactly one pick, whatever the replicate count behind it.
    assert len(body) == 2, body


def test_no_pass_writes_no_file_and_says_so(tmp_path: Path) -> None:
    """An empty mapping reads like a finished plate, so none is written."""
    # A well whose consensus is the reference carries no designed mutation, so
    # nothing reaches the mapping.
    result = _run(
        tmp_path,
        {"1_2": _REFERENCE_NT},
        janus_settings={"liquid_class": _LIQUID_CLASS},
    )

    autosave = result["janus_autosave"]
    assert autosave["status"] == "skipped", autosave
    assert autosave["row_count"] == 0
    assert autosave["output_path"] is None
    assert not (tmp_path / "260804_ref_MAME_janus.csv").exists()
    # The analysis itself is untouched.
    assert result["output_path"] == str(tmp_path / "260804_ref_MAME.xlsx")


def test_a_missing_liquid_class_is_reported_not_guessed(tmp_path: Path) -> None:
    """No default exists for it, so the automatic path must not invent one."""
    result = _run(tmp_path, {"1_2": _G2A_NT, "2_1": _F3W_NT})

    autosave = result["janus_autosave"]
    assert autosave["status"] == "failed", autosave
    assert [e["code"] for e in autosave["errors"]] == ["missing_liquid_class"]
    assert autosave["output_path"] is None
    # The analysis survives it.
    assert len(result["verdicts"]) == 2


def test_an_export_failure_does_not_cost_the_analysis(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The run is already complete by then; losing it to a file write is worse."""
    from kuma_core.mame.export import janus_mapping as janus_mod

    def _boom(*_args, **_kwargs):
        raise OSError("disk went away")

    monkeypatch.setattr(janus_mod, "export_mame_janus_csv", _boom)
    monkeypatch.setattr(
        "kuma_core.mame.export.export_mame_janus_csv", _boom, raising=False
    )

    result = _run(
        tmp_path,
        {"1_2": _G2A_NT, "2_1": _F3W_NT},
        janus_settings={"liquid_class": _LIQUID_CLASS},
    )

    autosave = result["janus_autosave"]
    assert autosave["status"] == "failed", autosave
    assert autosave["errors"][0]["code"] == "autosave_failed"
    assert "disk went away" in autosave["errors"][0]["message"]
    assert len(result["verdicts"]) == 2
    assert result["summary"]["total"] == 2


def test_autosave_path_derives_from_the_workbook_name() -> None:
    """The workbook name is the rule; the mapping only appends its own token."""
    from sidecar_mame.handlers.analyze import janus_autosave_path

    workbook = Path("/runs/260804_pTSN-PtIspS-idi_KanR_MAME_95verdicts.xlsx")

    assert janus_autosave_path(workbook) == Path(
        "/runs/260804_pTSN-PtIspS-idi_KanR_MAME_95verdicts_janus.csv"
    )
