"""Checks shared by the resequencing sample generator and bundled-data tests."""

from pathlib import Path
import re

import python_calamine

from kuma_core.mame.activity.build_evolvepro_input import build_evolvepro_input
from kuma_core.mame.activity.verdict_ngs import parse_verdict_rows


def compare_original_workbooks(old: Path, new: Path) -> None:
    """Refuse changed decisions, including nonselected plate copies."""
    assert parse_verdict_rows(old) == parse_verdict_rows(new), "original Final decisions changed"
    before = python_calamine.CalamineWorkbook.from_path(str(old))
    after = python_calamine.CalamineWorkbook.from_path(str(new))
    assert set(before.sheet_names) == set(after.sheet_names)
    stable = {
        "well_id", "well", "mutant_id", "mutant", "verdict", "selected_plate",
        "selected_NB", "selected", "failed", "is_fallback", "manual_confirmation",
        "custom_barcode", "fallback_reason", "verdict_notes", "notes", "recovered",
    }
    changed: set[str] = set()
    for name in before.sheet_names:
        rows_old = before.get_sheet_by_name(name).to_python()
        rows_new = after.get_sheet_by_name(name).to_python()
        if name == "__kuma_meta__":
            meta_old = {str(row[0]): row[1] for row in rows_old[1:]}
            meta_new = {str(row[0]): row[1] for row in rows_new[1:]}
            changed.update(f"{name}.{k}" for k in meta_old.keys() | meta_new.keys()
                           if meta_old.get(k) != meta_new.get(k))
            continue
        header_old, header_new = rows_old[0], rows_new[0]
        well_column = next((k for k in ("well_id", "well") if k in header_old), None)
        if well_column:
            # The result sheet also carries run-condition footnotes below
            # the well table. Added provenance is not a new plate occupant.
            oi, ni = header_old.index(well_column), header_new.index(well_column)
            filtered_old = [row for row in rows_old[1:] if re.fullmatch(r"[A-H](?:0?[1-9]|1[0-2])", str(row[oi]))]
            filtered_new = [row for row in rows_new[1:] if re.fullmatch(r"[A-H](?:0?[1-9]|1[0-2])", str(row[ni]))]
            if len(rows_old) != len(rows_new):
                changed.add(f"{name}.metadata_rows")
            rows_old, rows_new = [header_old, *filtered_old], [header_new, *filtered_new]
        assert len(rows_old) == len(rows_new), f"{name} row count changed"
        for field in set(header_old) | set(header_new):
            values_old = [row[header_old.index(field)] for row in rows_old[1:]] if field in header_old else None
            values_new = [row[header_new.index(field)] for row in rows_new[1:]] if field in header_new else None
            if field in stable:
                assert values_old == values_new, f"{name}.{field} decisions changed"
            if values_old != values_new:
                changed.add(f"{name}.{field}")
        if name.startswith("NB"):
            assert "well_id" in header_old and "verdict" in header_old
    print(f"original workbook stable rows and NB calls match; differing fields: {sorted(changed)}")


def verify_step4(samples: Path, output: Path) -> None:
    """Exercise the same ten branches as campaign.verify without rewriting 08."""
    # Use staged 13 with the unchanged bundled inputs. Outputs live only in
    # the caller's temporary directory, never in 08_mame_evolvepro_raw.xlsx.
    layout = samples / "06_mame_plate_layout.xlsx"
    expected = samples / "03_mame_expected_mutations.xlsx"
    cases = [
        {"activity_path": samples / "07_mame_activity_long.csv",
         "activity_scale": "relative_to_wt", "layout_xlsx": layout},
        {"activity_path": samples / "07_mame_activity_long.csv",
         "activity_scale": "relative_to_wt"},
        {"activity_path": samples / "07_mame_activity_long.xlsx",
         "activity_scale": "relative_to_wt", "layout_xlsx": layout},
        {"activity_path": samples / "14_mame_activity_long_raw.csv",
         "activity_scale": "raw", "layout_xlsx": layout},
        {"activity_path": samples / "15_mame_activity_variant.csv",
         "activity_scale": "relative_to_wt"},
        {"gc_data_xlsx": samples / "10_mame_gc_prenormalised.xlsx", "layout_xlsx": layout},
        {"round1_report_xlsx": samples / "11_mame_gc_fid_round1_raw.xlsx", "layout_xlsx": layout},
        {"numeric_report_xlsx": samples / "12_mame_agilent_numeric_index.xlsx",
         "layout_xlsx": layout, "expected_xlsx": expected},
        {"activity_path": samples / "07_mame_activity_long.csv",
         "activity_scale": "relative_to_wt", "layout_xlsx": layout,
         "remeasure_report_xlsx": samples / "09_mame_agilent_rep_batch.xlsx"},
        {"activity_path": samples / "07_mame_activity_long.csv",
         "activity_scale": "relative_to_wt", "expected_xlsx": expected,
         "remeasure_numeric_xlsx": samples / "16_mame_agilent_numeric_confirmation.xlsx"},
    ]
    for index, params in enumerate(cases, 1):
        built = build_evolvepro_input(output / f"step4_{index}.xlsx",
                                     verdict_xlsx=samples / "13_mame_verdict.xlsx", **params)
        assert built.n_variants == 16, f"step4 case {index} lost variants"
        print(f"verified step4 branch {index}/10: {built.n_variants} variants")
