from pathlib import Path
import csv
from typing import Any
from kuma_core.mame.activity.export_evolvepro import export_evolvepro_csv
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
