"""``run_quality`` on the analyze response, from a real run folder shape.

What is pinned here is the join, not the grading: the grading is covered in
``tests/mame/test_run_quality.py``. This asks whether the handler reads the pore
counts out of the file MinKNOW writes, whether the depth it grades is the depth
of the wells it SCORED, and whether the ledger makes a second campaign on one
cell visible.
"""

import json
from pathlib import Path

import openpyxl

from sidecar_mame.handlers.analyze import handle_analyze


#: The reference every fixture here reads, ATG AAA GTT TTT = M K V F. The
#: expected mutation has to agree with it at its own coordinate or the
#: classifier refuses the run before any of this is reached.
_REFERENCE_NT = "ATGAAAGTTTTT"
#: K2R: the second codon AAA (K) becomes CGT (R).
_K2R_NT = "ATGCGTGTTTTT"


def _expected(dest: Path) -> Path:
    """One designed mutation, K2R, matching ``_REFERENCE_NT``."""
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "expected_mutations"
    ws.append(["mutant_id", "position", "wt_aa", "mt_aa", "wt_codon", "mt_codon",
               "group_id", "primer_set_ref", "notation_type", "status"])
    ws.append(["K2R", 2, "K", "R", "AAA", "CGT", "", "K2R",
               "substitution", "DESIGNED"])
    wb.save(dest)
    return dest


def _report(run_dir: Path, flow_cell_id: str, pores: list[int]) -> None:
    """A report json shaped like the FBF10847 one this was measured against."""
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / f"report_{flow_cell_id}_20260212_2231_x.json").write_text(
        json.dumps(
            {
                "protocol_run_info": {
                    "flow_cell": {
                        "flow_cell_id": flow_cell_id,
                        "product_code": "FLO-MIN114",
                        "channel_count": 512,
                    }
                },
                "acquisitions": [
                    {
                        "acquisition_run_info": {
                            "bream_info": {
                                "mux_scan_results": [
                                    {
                                        "mux_scan_timestamp": 200 * (i + 1),
                                        "counts": {"single_pore": p},
                                    }
                                    for i, p in enumerate(pores)
                                ]
                            }
                        }
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def _consensus_run(tmp_path: Path, wells: dict[str, str], depth: int) -> Path:
    """A consensus-directory run: one FASTA per well with a stated depth."""
    ingest = tmp_path / "consensus" / "NB01"
    ingest.mkdir(parents=True, exist_ok=True)
    for token, seq in wells.items():
        (ingest / f"{token}.fasta").write_text(
            f">{token} depth={depth}\n{seq}\n", encoding="utf-8"
        )
    return tmp_path / "consensus"


def _params(tmp_path: Path, expected: Path, input_dir: Path) -> dict:
    reference = tmp_path / "ref.fasta"
    reference.write_text(f">ref\n{_REFERENCE_NT}\n", encoding="utf-8")
    # The handler refuses an output whose parent does not exist, and the ledger
    # is written beside that output, so the directory is part of the fixture.
    (tmp_path / "out").mkdir(parents=True, exist_ok=True)
    return {
        "input_dir": str(input_dir),
        "reference": str(reference),
        "expected": str(expected),
        "output": str(tmp_path / "out" / "result.xlsx"),
        "cds_start": 0,
        "cds_end": 12,
        "min_file_size_kb": 0.0,
        "ingest_mode": "barcode",
    }


def test_pore_counts_and_depth_reach_the_response(tmp_path: Path) -> None:
    """A deep run on a healthy cell: numbers reported, nothing flagged."""
    expected = _expected(tmp_path / "expected.xlsx")
    input_dir = _consensus_run(
        tmp_path, {"1_1": _K2R_NT, "2_1": _REFERENCE_NT}, depth=4777
    )
    _report(input_dir.parent, "FBF10847", [1150, 1252, 975])

    result = handle_analyze(_params(tmp_path, expected, input_dir))

    quality = result["run_quality"]
    assert quality["flow_cell_id"] == "FBF10847"
    assert quality["pore_start"] == 1150
    assert quality["pore_end"] == 975
    assert quality["median_well_reads"] == 4777
    assert quality["severity"] is None
    # Provenance rides with the block so a workflow default cannot be mistaken
    # for a vendor specification on screen.
    assert quality["thresholds"]["floor"]["kind"] == "vendor_default"
    assert quality["thresholds"]["floor"]["provisional"] is True
    # The recurrence tally rides the same block, and it is present on EVERY
    # response including one with nothing to report: a block that appeared only
    # when a position recurred could not be told apart from a sidecar that never
    # tallied one. These consensus fixtures carry no mix-eligible position, so
    # the table is empty and every count is zero.
    recurrence = quality["position_recurrence"]
    assert recurrence["lower_bound"] is True
    assert recurrence["positions"] == []
    assert recurrence["wells_contributing"] == 0
    assert recurrence["positions_single_well"] == 0
    # No grading anywhere on it, which is the whole point of the tally.
    assert "severity" not in recurrence
    assert "findings" not in recurrence


def test_a_shallow_run_blocks_and_a_weak_cell_alone_does_not(tmp_path: Path) -> None:
    """The 08-04 shape: 40 starting pores and four reads a well.

    Depth is what blocks. The pore count appears as a number, not a finding,
    because a cell that started at 343 pores returned five hundred reads a well
    on the same project.
    """
    expected = _expected(tmp_path / "expected.xlsx")
    input_dir = _consensus_run(
        tmp_path, {"1_1": _K2R_NT, "2_1": _REFERENCE_NT}, depth=4
    )
    _report(input_dir.parent, "FBF91250", [40, 42])

    result = handle_analyze(_params(tmp_path, expected, input_dir))

    quality = result["run_quality"]
    assert quality["severity"] == "blocking"
    codes = {f["code"] for f in quality["findings"]}
    assert codes == {"median_depth_below_floor"}
    assert quality["pore_start"] == 40
    assert quality["median_well_reads"] == 4


def test_a_second_run_on_one_cell_is_reported_as_a_reuse(tmp_path: Path) -> None:
    """The ledger is what makes 343 -> 188 -> 40 visible across campaigns."""
    expected = _expected(tmp_path / "expected.xlsx")
    shared_output = tmp_path / "out" / "result.xlsx"

    first_dir = _consensus_run(
        tmp_path / "runA", {"1_1": _K2R_NT, "2_1": _REFERENCE_NT}, depth=515
    )
    _report(first_dir.parent, "FBF91250", [343, 188])
    first = _params(tmp_path, expected, first_dir)
    first["output"] = str(shared_output)
    handle_analyze(first)

    second_dir = _consensus_run(
        tmp_path / "runB", {"1_1": _K2R_NT, "2_1": _REFERENCE_NT}, depth=4
    )
    _report(second_dir.parent, "FBF91250", [40, 42])
    second = _params(tmp_path, expected, second_dir)
    second["output"] = str(shared_output)

    result = handle_analyze(second)

    quality = result["run_quality"]
    assert quality["reused_from"] is not None
    assert quality["reused_from"]["pore_end"] == 188
    codes = {f["code"] for f in quality["findings"]}
    assert "flow_cell_reused" in codes


def test_analysing_one_folder_twice_reports_no_reuse(tmp_path: Path) -> None:
    """The ledger counts campaigns, not analyse clicks."""
    expected = _expected(tmp_path / "expected.xlsx")
    input_dir = _consensus_run(
        tmp_path, {"1_1": _K2R_NT, "2_1": _REFERENCE_NT}, depth=515
    )
    _report(input_dir.parent, "FBF91250", [343, 188])
    params = _params(tmp_path, expected, input_dir)

    handle_analyze(params)
    result = handle_analyze(params)

    assert result["run_quality"]["reused_from"] is None


def test_a_folder_with_no_report_json_reports_no_pores(tmp_path: Path) -> None:
    """Unknown pores and zero pores must not be the same value."""
    expected = _expected(tmp_path / "expected.xlsx")
    input_dir = _consensus_run(
        tmp_path, {"1_1": _K2R_NT, "2_1": _REFERENCE_NT}, depth=4777
    )

    result = handle_analyze(_params(tmp_path, expected, input_dir))

    quality = result["run_quality"]
    assert quality["pore_start"] is None
    assert quality["flow_cell_id"] is None
    assert quality["reused_from"] is None
