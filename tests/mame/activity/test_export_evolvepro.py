from pathlib import Path
import csv
from typing import Any
from kuma_core.mame.activity.export_evolvepro import (
    export_evolvepro_csv,
    export_evolvepro_xlsx,
)
from kuma_core.mame.activity.models import MergedRow


def _row(**kwargs: Any) -> MergedRow:
    base: dict[str, Any] = dict(
        plate_id="P01", well_id="A01", mutation="F89W",
        mutation_source="kuro_design", expected_mutation="F89W",
        called_mutation="F89W", ngs_success=True,
        activity_raw_mean=2.0, activity_raw_sd=0.1,
        activity_replicates=[2.0], replicate_n=1,
        fold_change=2.0, log2_fc=1.0,
    )
    base.update(kwargs)
    return MergedRow(**base)


def test_export_includes_kept_rows(tmp_path: Path) -> None:
    rows = [
        _row(),
        _row(well_id="B01", mutation="WT", mutation_source="kuro_design",
             expected_mutation="WT", called_mutation="WT", log2_fc=0.0),
    ]
    out = tmp_path / "evolvepro.csv"
    n = export_evolvepro_csv(rows, out, round_n=1)
    assert n == 1  # WT 제외
    with open(out) as f:
        reader = csv.DictReader(f)
        records = list(reader)
    assert len(records) == 1
    assert records[0]["variant"] == "F89W"
    assert abs(float(records[0]["y_pred"]) - 1.0) < 1e-6


def test_export_excluded_csv(tmp_path: Path) -> None:
    rows = [
        _row(),
        _row(well_id="C01", ngs_success=False, mutation="L70V"),
    ]
    out = tmp_path / "evo.csv"
    export_evolvepro_csv(rows, out, round_n=1)
    excluded = tmp_path / "evo.excluded.csv"
    assert excluded.exists()
    with open(excluded) as f:
        reader = csv.DictReader(f)
        excl = list(reader)
    assert len(excl) == 1
    reason = excl[0]["reason"].lower()
    assert "ngs_success" in reason or "ngs" in reason


# ---------------------------------------------------------------------------
# UTF-8 BOM option tests — §17 Cross-platform
# ---------------------------------------------------------------------------

BOM = b"\xef\xbb\xbf"


def test_export_evolvepro_csv_bom_true(tmp_path: Path) -> None:
    """encoding='utf-8-sig': first 3 bytes must be UTF-8 BOM."""
    rows = [_row()]
    out = tmp_path / "evolvepro_bom.csv"
    export_evolvepro_csv(rows, out, round_n=1, encoding="utf-8-sig")
    assert out.read_bytes()[:3] == BOM, "Expected UTF-8 BOM with encoding='utf-8-sig'"


def test_export_evolvepro_csv_bom_false(tmp_path: Path) -> None:
    """Default encoding='utf-8': no BOM."""
    rows = [_row()]
    out = tmp_path / "evolvepro_nobom.csv"
    export_evolvepro_csv(rows, out, round_n=1, encoding="utf-8")
    assert out.read_bytes()[:3] != BOM, "Unexpected BOM with encoding='utf-8'"


def test_export_evolvepro_csv_default_no_bom(tmp_path: Path) -> None:
    """Default (encoding omitted): no BOM — backward compat."""
    rows = [_row()]
    out = tmp_path / "evolvepro_default.csv"
    export_evolvepro_csv(rows, out, round_n=1)
    assert out.read_bytes()[:3] != BOM, "Unexpected BOM with default params"


# ---------------------------------------------------------------------------
# xlsx export — Hyemin spec v0.3 §2.4
# ---------------------------------------------------------------------------


def test_export_evolvepro_xlsx_spec_2col(tmp_path: Path) -> None:
    """Strict [Variant, activity] 2-column EVOLVEpro format with 89W notation.

    Spec: notes/specs/2026-05-06-mame-activity-v0.3-xlsx-pipeline.md §2.4
    """
    import openpyxl

    rows = [
        _row(relative_activity=1.78),
        _row(
            well_id="B01",
            mutation="WT",
            mutation_source="kuro_design",
            expected_mutation="WT",
            called_mutation="WT",
            log2_fc=0.0,
        ),
    ]
    out = tmp_path / "evolvepro.xlsx"
    n_written, excluded = export_evolvepro_xlsx(rows, out)
    assert n_written == 1
    assert any(reason == "mutation=WT" for _label, reason in excluded)

    wb = openpyxl.load_workbook(str(out))
    ws = wb["EVOLVEpro"]
    data = list(ws.values)
    assert data[0] == ("Variant", "activity")
    assert data[1][0] == "89W"
    assert abs(float(data[1][1]) - 1.78) < 1e-6


def test_export_evolvepro_xlsx_falls_back_to_fold_change(tmp_path: Path) -> None:
    """When relative_activity is None, fold_change is used as activity value."""
    import openpyxl

    rows = [_row(relative_activity=None, fold_change=2.5)]
    out = tmp_path / "evolvepro_fb.xlsx"
    n_written, excluded = export_evolvepro_xlsx(rows, out)
    assert n_written == 1
    assert excluded == []

    wb = openpyxl.load_workbook(str(out))
    data = list(wb["EVOLVEpro"].values)
    assert abs(float(data[1][1]) - 2.5) < 1e-6


def test_export_evolvepro_xlsx_skips_non_canonical(tmp_path: Path) -> None:
    """Multi-substitution or malformed variant strings are excluded."""
    rows = [
        _row(),  # canonical F89W → kept
        _row(well_id="C03", mutation="F89W/L70V"),  # multi-sub → excluded
    ]
    out = tmp_path / "evolvepro_nc.xlsx"
    n_written, excluded = export_evolvepro_xlsx(rows, out)
    assert n_written == 1
    assert any(reason == "non_canonical_variant" for _label, reason in excluded)
