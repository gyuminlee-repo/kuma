"""Bundled independent runs support explicit physical-clone evidence."""

import csv
import hashlib
import json
from pathlib import Path

import pytest
import python_calamine

from kuma_core.mame.activity.build_evolvepro_input import build_evolvepro_input
from kuma_core.mame.activity.evolvepro_xlsx import read_evolvepro_rows
from kuma_core.mame.activity.plate_layout_xlsx import parse_plate_layout_xlsx
from kuma_core.mame.activity.resequence_evidence import (
    CloneEvidenceLink, ResequenceEvidence, validate_resequence_links,
)
from kuma_core.mame.activity.verdict_ngs import parse_verdict_rows
from scripts.mame_resequence_sample_checks import verify_step4

SAMPLES = Path(__file__).resolve().parents[2] / "src-tauri" / "samples" / "mame"
ORIGINAL = SAMPLES / "13_mame_verdict.xlsx"
REPEATED = SAMPLES / "18_mame_resequence_verdict.xlsx"


def test_bundled_workbooks_record_compatible_reference_and_coding_window():
    # Given both workbook metadata sheets and the actual bundled reference.
    metadata = []
    for path in (ORIGINAL, REPEATED):
        book = python_calamine.CalamineWorkbook.from_path(str(path))
        metadata.append({str(row[0]): str(row[1]) for row in book.get_sheet_by_name("__kuma_meta__").to_python()})
    cds = "".join(line for line in (SAMPLES / "reference.fasta").read_text().splitlines() if not line.startswith(">"))

    # When comparing the recorded analysis identity.
    identity = [{key: meta[key] for key in ("reference_sha256", "coding_window", "mode")} for meta in metadata]

    # Then both runs describe the same reference and full coding window.
    assert identity[0] == identity[1] == {
        "reference_sha256": hashlib.sha256(cds.encode("ascii")).hexdigest(),
        "coding_window": f"0-{len(cds)}",
        "mode": "amplicon",
    }


@pytest.fixture
def evidence() -> ResequenceEvidence:
    source = parse_verdict_rows(ORIGINAL)["A01"]
    repeated = parse_verdict_rows(REPEATED)["A01"]
    assert source.mutant_id == repeated.mutant_id == "F28A"
    return ResequenceEvidence(
        original_verdict_xlsx=str(ORIGINAL), verdict_xlsx=str(REPEATED),
        links=[CloneEvidenceLink(
            relationship="same_clone", mutant_id="F28A",
            original_well="A1", original_plate=source.selected_plate,
            resequence_well="A1", resequence_plate=repeated.selected_plate,
        )],
    )


@pytest.mark.parametrize("relationship,filename,activity_well", [
    ("same_clone", "14_mame_activity_long_raw.csv", "A01"),
    ("measured_resequence_clone", "19_mame_activity_resequence_clone.csv", "A03"),
])
def test_bundled_links_build_only_the_declared_activity_source(tmp_path, evidence, relationship, filename, activity_well):
    # Given an explicit selected clone, never a link inferred from mutant names.
    link = CloneEvidenceLink.model_validate({
        **evidence.links[0].model_dump(), "relationship": relationship, "activity_well": activity_well,
    })
    evidence = evidence.model_copy(update={"links": [link]})
    mapped = validate_resequence_links(evidence, ORIGINAL)
    with (SAMPLES / filename).open() as handle:
        rows = list(csv.DictReader(handle))
    raw = [float(row["value"]) for row in rows if row["well_id"] == activity_well.replace("0", "")]
    wt = [float(row["value"]) for row in rows if row["well_id"].startswith("WT_")]

    # When the final activity plate is built against both bundled workbooks.
    built = build_evolvepro_input(
        tmp_path / "activity.xlsx", verdict_xlsx=ORIGINAL, activity_path=SAMPLES / filename,
        activity_scale="raw", layout_xlsx=SAMPLES / "06_mame_plate_layout.xlsx",
        resequence_evidence=evidence,
    )

    # Then one physical source contributes all three F28A measurements.
    assert mapped == {"28A": activity_well}
    assert len(raw) == len(wt) == 3
    assert built.n_variants == 16
    assert dict(read_evolvepro_rows(built.output_path))["28A"] == pytest.approx(sum(raw) / sum(wt))
    assert built.variant_replicates["28A"] == pytest.approx([value / (sum(wt) / len(wt)) for value in raw])
    assert built.manifest_path is not None
    manifest = json.loads(built.manifest_path.read_text())
    assert manifest["resequence_evidence"]["links"][0]["relationship"] == relationship


def test_bundled_repeat_requires_the_automatically_selected_plate(evidence):
    # Given a PASS sibling copy rather than the selected NB05 clone.
    link = evidence.links[0].model_copy(update={"resequence_plate": "NB06"})
    wrong_copy = evidence.model_copy(update={"links": [link]})

    # When a user declares that nonselected copy as evidence.
    with pytest.raises(ValueError, match="not the automatically selected clone"):
        validate_resequence_links(wrong_copy, ORIGINAL)


def test_bundled_measured_plate_replaces_the_old_clone_without_moving_other_samples():
    # Given the original physical plate and both activity sources.
    layout = {entry.well_id: entry.mutant for entry in parse_plate_layout_xlsx(SAMPLES / "06_mame_plate_layout.xlsx")}
    with (SAMPLES / "14_mame_activity_long_raw.csv").open() as handle:
        original = list(csv.DictReader(handle))
    with (SAMPLES / "19_mame_activity_resequence_clone.csv").open() as handle:
        measured = list(csv.DictReader(handle))

    # When comparing the final plate to the old measurements.
    moved_back = [{**row, "well_id": "A1" if row["well_id"] == "A3" else row["well_id"]} for row in measured]

    # Then A3 was free and exactly F28A moved, including its raw values.
    assert layout["A01"] == "F28A"
    assert "A03" not in layout
    assert not any(row["well_id"] == "A1" for row in measured)
    key = lambda row: (row["well_id"], row["replicate_idx"])
    assert sorted(moved_back, key=key) == sorted(original, key=key)


def test_original_step4_ten_branches_still_build_with_regenerated_provenance(tmp_path):
    # Given unchanged activity inputs and the regenerated original workbook.
    # When every campaign.verify branch builds in a temporary directory.
    verify_step4(SAMPLES, tmp_path)
    # Then each branch produced its own workbook, without rewriting sample 08.
    assert len(list(tmp_path.glob("step4_*.xlsx"))) == 10
