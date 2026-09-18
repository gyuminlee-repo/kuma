"""CLI routing, failure reporting, and output completion contracts."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from kuma_core.kuro import cli, plate_mapper, sdm_engine
from kuma_core.kuro.codon_table import CodonTableRegistry


def _args(tmp_path, *extra):
    return cli.build_parser().parse_args([
        "design", "--fasta", "template.gb", "--target-start", "0",
        "--mutations", "mutations.csv", "--output", str(tmp_path / "out"), *extra,
    ])


def _stub_design(monkeypatch, failures=None, *, empty=False, export_error=False):
    calls = {}
    result = SimpleNamespace(tm_condition_met=True, mutation=SimpleNamespace(raw="A10G"))
    def design(**kwargs):
        calls.update(kwargs)
        return ([] if empty else [result]), {}, dict(failures or {})
    def write_tsv(_results, path, **_kwargs):
        if export_error:
            raise OSError("simulated disk error")
        path.write_text("primers", encoding="utf-8")
    def write_excel(_maps, path, **_kwargs):
        path.write_bytes(b"test workbook")
    monkeypatch.setattr(sdm_engine, "design_sdm_primers", design)
    monkeypatch.setattr(sdm_engine, "export_results_tsv", write_tsv)
    monkeypatch.setattr(plate_mapper, "deduplicate_reverse", lambda _results: [])
    monkeypatch.setattr(plate_mapper, "generate_plate_map", lambda *_a, **_kw: ([], []))
    monkeypatch.setattr(plate_mapper, "export_plate_excel", write_excel)
    return calls


@pytest.mark.parametrize("organism", CodonTableRegistry().list_organisms())
def test_selected_host_reaches_design_engine_and_report(tmp_path, monkeypatch, organism):
    calls = _stub_design(monkeypatch)
    args = _args(tmp_path, "--organism", organism)
    cli.cmd_design(args)
    assert calls["organism"] == organism
    report = json.loads((Path(args.output) / "design_summary.json").read_text(encoding="utf-8"))
    assert report["organism"] == organism
    assert report["status"] == "complete"
    assert report["designed_count"] == 1
    assert report["failed_count"] == 0
    assert report["successful_mutations"] == ["A10G"]
    assert report["requested_parameters"]["tm_fwd_target"] is None
    assert set(report["artifacts"]) == {"primers", "plate_map"}


def test_default_host_remains_ecoli(tmp_path, monkeypatch):
    calls = _stub_design(monkeypatch)
    cli.cmd_design(_args(tmp_path))
    assert calls["organism"] == "ecoli"


def test_supported_alias_is_resolved(tmp_path, monkeypatch):
    calls = _stub_design(monkeypatch)
    cli.cmd_design(_args(tmp_path, "--host-organism", "Methylorubrum extorquens AM1"))
    assert calls["organism"] == "mextorquens"


@pytest.mark.parametrize("host", ["not-a-host", "../ecoli", "/tmp/table", ""])
def test_unknown_host_is_rejected_before_writing_output(tmp_path, host):
    with pytest.raises(SystemExit) as exc:
        _args(tmp_path, "--organism", host)
    assert exc.value.code == 2
    assert not (tmp_path / "out").exists()


def test_partial_success_is_preserved_and_failed_reasons_are_visible(tmp_path, monkeypatch, capsys):
    _stub_design(monkeypatch, {"A20G": "no valid primer pair"})
    args = _args(tmp_path)
    cli.cmd_design(args)
    report = json.loads((Path(args.output) / "design_summary.json").read_text(encoding="utf-8"))
    assert report["status"] == "partial"
    assert report["failed_reasons"] == {"A20G": "no valid primer pair"}
    assert report["designed_count"] == report["failed_count"] == 1
    assert (Path(args.output) / "sdm_primers.tsv").is_file()
    assert "A20G" in capsys.readouterr().out


def test_strict_partial_exit_happens_after_usable_artifacts_are_written(tmp_path, monkeypatch):
    _stub_design(monkeypatch, {"A20G": "no valid primer pair"})
    args = _args(tmp_path, "--fail-on-partial")
    with pytest.raises(SystemExit) as exc:
        cli.cmd_design(args)
    assert exc.value.code == 2
    assert (Path(args.output) / "plate_mapping.xlsx").is_file()
    assert json.loads((Path(args.output) / "design_summary.json").read_text())["status"] == "partial"


def test_no_designs_still_writes_failure_report(tmp_path, monkeypatch):
    _stub_design(monkeypatch, {"A0G": "position must be positive"}, empty=True)
    args = _args(tmp_path)
    with pytest.raises(SystemExit) as exc:
        cli.cmd_design(args)
    assert exc.value.code == 1
    report = json.loads((Path(args.output) / "design_summary.json").read_text(encoding="utf-8"))
    assert report["status"] == "failed"
    assert report["failed_reasons"]["A0G"] == "position must be positive"
    assert report["artifacts"] == {}


def test_failed_export_never_leaves_a_complete_summary(tmp_path, monkeypatch):
    _stub_design(monkeypatch, export_error=True)
    args = _args(tmp_path)
    with pytest.raises(OSError, match="simulated disk error"):
        cli.cmd_design(args)
    report = json.loads((Path(args.output) / "design_summary.json").read_text(encoding="utf-8"))
    assert report["status"] == "error"
    assert report["artifacts"] == {}
