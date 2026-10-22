#!/usr/bin/env python3
"""Replay the bundled campaign and add an independent NB04-06 run.

PYTHONPATH=.:python-core <project-python> python-core/scripts/generate_mame_resequence_samples.py

The bundled 03 workbook, 06 placement and reference are the campaign identity.
The older campaign generator no longer reproduces these constructs (K53A vs
K239A and synonymous codon drift). Its synthesis helpers are reused, not its
candidate selection. The original JSON fixture is also stale: length_true_nt
is null there, whereas the current translator computes the molecule.
consensus_net_indel_bp and temporary source_path values differ too.
Stable identities, calls and selections must
still agree; every differing serialized field is printed without rewriting the
old fixture. Response file paths are bundle filenames; consensus source paths
are documented sample-consensus placeholders (no raw reads are bundled).
The pre-provenance 13 workbook has no reference hash/coding window/mode.
Only that existing file is regenerated; its complete parsed verdict rows and
each native-barcode sheet's decisions are proven unchanged before replacement.
All ten existing Step 4 branches and both relationships build before publication.
Synthetic workbook timestamps are fixed to 2026-01-01 for byte-identical replay.
"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
from pathlib import Path
from typing import Final
from unittest.mock import patch
from zipfile import ZipFile

import generate_mame_step4_samples as campaign
from mame_resequence_sample_checks import compare_original_workbooks, verify_step4
from kuma_core.mame.activity.build_evolvepro_input import build_evolvepro_input
from kuma_core.mame.activity.plate_layout_xlsx import parse_plate_layout_xlsx
from kuma_core.mame.activity.resequence_evidence import (
    CloneEvidenceLink, ResequenceEvidence, validate_resequence_links,
)
from kuma_core.mame.activity.verdict_ngs import parse_verdict_rows
from kuma_core.mame.io.variant_list import read_variant_source
from kuma_core.mame.layout import build_draft_layout
from sidecar_mame.handlers.analyze import handle_analyze
from sidecar_mame.handlers.export import handle_get_plate_data
from sidecar_mame.handlers.health import handle_get_run_health

REPEATED: Final = "18_mame_resequence_verdict.xlsx"
MEASURED: Final = "19_mame_activity_resequence_clone.csv"
VARIANT: Final = "F28A"
FREE_WELL: Final = "A3"
BARCODES: Final = ("NB04", "NB05", "NB06")
DEFECTS: Final = {
    "F28A": ("LOWDEPTH", "NB04"),
    "H78A": ("MIXED", "NB05"),
    "A88V": ("WRONG_AA", "NB06"),
}
STABLE: Final = (
    "mutant_id", "well", "well_id", "native_barcode", "custom_barcode",
    "barcode", "verdict", "selected", "is_fallback",
)


def verify(samples: Path) -> None:
    """Build both declarations from staged bytes and reject a duplicate link."""
    original, repeated = samples / "13_mame_verdict.xlsx", samples / REPEATED
    source_well, source = next((w, r) for w, r in parse_verdict_rows(original).items() if r.mutant_id == VARIANT)
    repeat_well, repeat = next((w, r) for w, r in parse_verdict_rows(repeated).items() if r.mutant_id == VARIANT)
    evidence: ResequenceEvidence | None = None
    with tempfile.TemporaryDirectory(prefix="resequence_verify_") as temporary:
        verify_step4(samples, Path(temporary))
        for relationship, activity in (
            ("same_clone", "14_mame_activity_long_raw.csv"),
            ("measured_resequence_clone", MEASURED),
        ):
            link = CloneEvidenceLink.model_validate({
                "relationship": relationship, "mutant_id": VARIANT,
                "original_well": source_well, "original_plate": source.selected_plate,
                "resequence_well": repeat_well, "resequence_plate": repeat.selected_plate,
                "activity_well": FREE_WELL,
            })
            evidence = ResequenceEvidence(original_verdict_xlsx=str(original), verdict_xlsx=str(repeated), links=[link])
            mapped = validate_resequence_links(evidence, original)
            built = build_evolvepro_input(
                Path(temporary) / f"{relationship}.xlsx", verdict_xlsx=original,
                activity_path=samples / activity, activity_scale="raw",
                layout_xlsx=samples / "06_mame_plate_layout.xlsx", resequence_evidence=evidence,
            )
            assert built.n_variants == len(campaign.ACTIVITY)
            print(f"verified {relationship}: {source.selected_plate}/{source_well} -> "
                  f"{repeat.selected_plate}/{repeat_well}, activity {mapped}, {built.n_variants} variants")
        assert evidence is not None
        duplicate = evidence.model_copy(update={"links": evidence.links * 2})
        try:
            validate_resequence_links(duplicate, original)
        except ValueError as error:
            assert "Duplicate clone mapping" in str(error)
        else:
            raise AssertionError("duplicate resequencing link was accepted")
        print("verified duplicate link rejected")


def stable_workbook(path: Path) -> None:
    """Fix ZIP and document timestamps on the new workbook only."""
    with ZipFile(path) as archive:
        entries = [(info, archive.read(info.filename)) for info in archive.infolist()]
    with ZipFile(path, "w") as archive:
        for info, content in entries:
            info.date_time = (2026, 1, 1, 0, 0, 0)
            if info.filename == "docProps/core.xml":
                content = re.sub(
                    rb"(<dcterms:(?:created|modified)[^>]*>).*?(</dcterms:(?:created|modified)>)",
                    rb"\g<1>2026-01-01T00:00:00Z\2", content,
                )
            if info.filename.startswith("xl/worksheets/"):
                content = re.sub(rb"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z",
                                 b"2026-01-01T00:00:00Z", content)
            archive.writestr(info, content)


def main() -> None:
    cds = campaign.read_reference_cds()
    expected = campaign.SAMPLES / "03_mame_expected_mutations.xlsx"
    read = read_variant_source(expected)
    variants = [
        campaign.Variant(row.mutant_id, row.position, row.wt_aa, row.mt_aa,
                         row.wt_codon, row.mt_codon, "bundled campaign")
        for row in read.expected
    ]
    assert {variant.mutant_id for variant in variants} == set(campaign.ACTIVITY)
    by_id = {variant.mutant_id: variant for variant in variants}
    draft = build_draft_layout(read.expected, wt_ordinal=read.wt_ordinal)
    assert not draft.dropped_mutant_ids
    layout = dict(draft.layout)
    bundled_layout = {entry.well_id: entry.mutant for entry in parse_plate_layout_xlsx(campaign.SAMPLES / "06_mame_plate_layout.xlsx")}
    assert {f"{w[0]}{int(w[1:]):02d}": mid for w, mid in layout.items()} == bundled_layout
    assert FREE_WELL not in layout
    fixture = json.loads((campaign.SAMPLES / "sample_analysis_result.json").read_text())
    with tempfile.TemporaryDirectory(prefix="mame_resequence_") as temporary:
        work = Path(temporary)
        staged = work / "samples"
        staged.mkdir()
        for sample in campaign.SAMPLES.iterdir():
            if sample.is_file():
                shutil.copyfile(sample, staged / sample.name)
        generated: list[str] = []
        for name, barcodes, response_name in (
            ("original.xlsx", campaign.NATIVE_BARCODES, "sample_analyze_response.json"),
            (REPEATED, BARCODES, "sample_resequence_response.json"),
        ):
            run = work / name.removesuffix(".xlsx")
            run.mkdir()
            profiles = dict(zip(BARCODES, (campaign._NB_PROFILE[nb] for nb in campaign.NATIVE_BARCODES)))
            targets = dict(campaign._TARGET_VERDICT) if barcodes == campaign.NATIVE_BARCODES else DEFECTS
            with patch.dict(campaign._NB_PROFILE, profiles), patch.dict(campaign._TARGET_VERDICT, targets, clear=True):
                consensus = campaign.build_consensus_dir(run, cds, layout, by_id, barcodes)
            output = run / name
            response = handle_analyze({
                "input_dir": str(consensus), "reference": str(campaign.REFERENCE),
                "expected": str(expected), "output": str(output),
                "cds_start": 0, "cds_end": len(cds), "mode": "amplicon",
                "min_file_size_kb": 0.0, "min_read_count": 30,
                "max_consensus_n_fraction": 0.0, "many_cutoff": 5,
                "ingest_mode": "barcode", "well_layout": layout,
            })
            if barcodes == campaign.NATIVE_BARCODES:
                differing: set[str] = set()
                for actual, recorded in zip(response["verdicts"], fixture["verdicts"], strict=True):
                    assert [actual.get(k) for k in STABLE] == [recorded.get(k) for k in STABLE]
                    differing.update(k for k in actual.keys() | recorded.keys() if actual.get(k) != recorded.get(k))
                for actual, recorded in zip(response["replicates"], fixture["replicates"], strict=True):
                    for key in ("mutant_id", "selected_plate", "failed", "is_fallback", "manual", "plate_keys"):
                        assert actual.get(key) == recorded.get(key), f"replicate {key} drift"
                    assert actual["plate_verdicts"].keys() == recorded["plate_verdicts"].keys()
                    for plate, verdict in actual["plate_verdicts"].items():
                        old = recorded["plate_verdicts"][plate]
                        assert [verdict.get(k) for k in STABLE] == [old.get(k) for k in STABLE]
                        differing.update(k for k in verdict.keys() | old.keys() if verdict.get(k) != old.get(k))
                compare_original_workbooks(staged / "13_mame_verdict.xlsx", output)
                shutil.copyfile(output, staged / "13_mame_verdict.xlsx")
                stable_workbook(staged / "13_mame_verdict.xlsx")
                generated.append("13_mame_verdict.xlsx")
                print(f"original stable decisions/workbook rows match; differing fixture fields: {sorted(differing)}")
                response["output_path"] = "13_mame_verdict.xlsx"
            else:
                shutil.copyfile(output, staged / name)
                stable_workbook(staged / name)
                generated.append(name)
                response["output_path"] = name
            response["wells"] = handle_get_plate_data({})["wells"]
            response["runHealth"] = handle_get_run_health({})
            response["layout_provenance"]["expected_path"] = expected.name
            picks = response["janus_autosave"]
            assert picks["status"] == "saved", picks
            pick_name = "sample_original_picks.csv" if barcodes == campaign.NATIVE_BARCODES else "18_mame_resequence_verdict_picks.csv"
            shutil.copyfile(picks["output_path"], staged / pick_name)
            picks["output_path"] = pick_name
            generated.append(pick_name)
            # No absolute temp paths may escape. source_path is informational:
            # the full cached verdict, not a nonexistent consensus, serves RPCs.
            payload = json.dumps(response, indent=2, ensure_ascii=False)
            payload = payload.replace(str(run) + "/", "sample-consensus/")
            assert temporary not in payload
            (staged / response_name).write_text(payload + "\n", encoding="utf-8")
            generated.append(response_name)
        # Replace the old F28A clone's rows, not the other occupants or WT.
        # Re-measurements use ACTIVITY[F28A] * mean(WT_RAW), the same explicit
        # raw-scale derivation as the original plate, with no ad-hoc values.
        measured_layout = {well: mid for well, mid in layout.items() if mid != VARIANT}
        measured_layout[FREE_WELL] = VARIANT
        campaign.write_long_raw(measured_layout, staged / MEASURED)
        generated.append(MEASURED)
        verify(staged)
        for name in generated:
            shutil.copyfile(staged / name, campaign.SAMPLES / name)
        print(f"published {len(generated)} files (13 regenerated, six new); defects: {DEFECTS}; measured {VARIANT} -> {FREE_WELL}")


if __name__ == "__main__":
    main()

