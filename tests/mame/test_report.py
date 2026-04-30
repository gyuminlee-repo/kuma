"""Tests for kuma_core.mame.report (A14 — run report generation)."""

from __future__ import annotations

import shutil
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from kuma_core.mame.report.builder import RunReportData, build_run_report_data
from kuma_core.mame.report.html_renderer import render_html
from kuma_core.mame.report.pdf_export import export_pdf


# ── Fixtures ─────────────────────────────────────────────────────────────────


def _make_barcode(native: str, custom: str, size_kb: float) -> MagicMock:
    b = MagicMock()
    b.native_barcode = native
    b.custom_barcode = custom
    b.file_size_kb = size_kb
    return b


def _make_verdict(native: str, custom: str, size_kb: float, verdict_val: str) -> MagicMock:
    barcode = _make_barcode(native, custom, size_kb)
    translated = MagicMock()
    translated.barcode = barcode
    vr = MagicMock()
    vr.translated = translated
    vr.verdict = MagicMock()
    vr.verdict.value = verdict_val
    vr.expected_mutations = ["V5F"]
    vr.verdict_notes = ""
    return vr


def _make_replicate(mutant_id: str, selected_plate: str | None, is_fallback: bool = False) -> MagicMock:
    rr = MagicMock()
    rr.mutant_id = mutant_id
    rr.selected_plate = selected_plate
    rr.failed = selected_plate is None
    rr.is_fallback = is_fallback
    rr.fallback_reason = "low depth" if is_fallback else None
    rr.plate_verdicts = {}
    return rr


def _make_run_meta() -> MagicMock:
    meta = MagicMock()
    meta.instrument = "MinION"
    meta.position = "MN00001"
    meta.flow_cell_id = "FAX12345"
    meta.sample_id = "test_sample"
    meta.kit = "SQK-LSK109"
    meta.started = "2024-01-01T10:00:00Z"
    meta.basecalling_enabled = True
    meta.raw_run_dir = "/mnt/data/runs/run_xyz"
    return meta


def _make_sample_verdicts() -> list:
    """12 verdicts spread across NB01/NB02: 4 PASS, 3 AMBIGUOUS, 5 FAIL."""
    return [
        _make_verdict("NB01", "1_1", 250.0, "PASS"),
        _make_verdict("NB01", "1_2", 230.0, "PASS"),
        _make_verdict("NB01", "1_3", 180.0, "AMBIGUOUS"),
        _make_verdict("NB01", "1_4", 40.0, "LOWDEPTH"),
        _make_verdict("NB01", "2_1", 35.0, "LOWDEPTH"),
        _make_verdict("NB01", "2_2", 200.0, "PASS"),
        _make_verdict("NB02", "1_1", 260.0, "PASS"),
        _make_verdict("NB02", "1_2", 190.0, "AMBIGUOUS"),
        _make_verdict("NB02", "1_3", 150.0, "AMBIGUOUS"),
        _make_verdict("NB02", "1_4", 30.0, "FRAMESHIFT"),
        _make_verdict("NB02", "2_1", 25.0, "MANY"),
        _make_verdict("NB02", "2_2", 20.0, "WRONG_AA"),
    ]


def _make_sample_replicates() -> list:
    return [
        _make_replicate("V5F", "NB01"),
        _make_replicate("K53N", "NB02", is_fallback=True),
        _make_replicate("G12V", None),
    ]


# ── build_run_report_data tests ───────────────────────────────────────────────


class TestBuildRunReportData:
    def test_total_counts_correct(self) -> None:
        verdicts = _make_sample_verdicts()
        replicates = _make_sample_replicates()
        data = build_run_report_data(
            verdicts, replicates, project_name="TestProject"
        )
        assert data.total_wells == 12
        assert data.pass_count == 4
        assert data.ambiguous_count == 3
        assert data.fail_count == 5

    def test_per_plate_breakdown(self) -> None:
        verdicts = _make_sample_verdicts()
        replicates = _make_sample_replicates()
        data = build_run_report_data(verdicts, replicates)
        assert "NB01" in data.per_plate
        assert "NB02" in data.per_plate
        nb01 = data.per_plate["NB01"]
        assert nb01.total == 6
        assert nb01.pass_count == 3
        assert nb01.ambiguous_count == 1
        assert nb01.fail_count == 2

    def test_fallback_count(self) -> None:
        verdicts = _make_sample_verdicts()
        replicates = _make_sample_replicates()
        data = build_run_report_data(verdicts, replicates)
        # K53N is_fallback=True, selected_plate=NB02
        assert data.fallback_count == 1

    def test_final_96_filled(self) -> None:
        verdicts = _make_sample_verdicts()
        replicates = _make_sample_replicates()
        data = build_run_report_data(verdicts, replicates)
        # V5F and K53N have selected_plate; G12V failed
        assert data.final_96_filled == 2

    def test_run_meta_propagated(self) -> None:
        meta = _make_run_meta()
        verdicts = _make_sample_verdicts()
        replicates = _make_sample_replicates()
        data = build_run_report_data(verdicts, replicates, run_meta=meta)
        assert data.run_meta is meta

    def test_project_name_set(self) -> None:
        verdicts = _make_sample_verdicts()
        replicates = _make_sample_replicates()
        data = build_run_report_data(
            verdicts, replicates, project_name="MyProject"
        )
        assert data.project_name == "MyProject"

    def test_distribution_stats_computed(self) -> None:
        verdicts = _make_sample_verdicts()
        replicates = _make_sample_replicates()
        data = build_run_report_data(verdicts, replicates)
        assert "min" in data.file_size_distribution
        assert "median" in data.file_size_distribution
        assert data.suggested_cutoff_kb >= 50.0

    def test_kuma_version_stored(self) -> None:
        verdicts = _make_sample_verdicts()
        replicates = _make_sample_replicates()
        data = build_run_report_data(
            verdicts, replicates, kuma_version="1.2.3"
        )
        assert data.kuma_version == "1.2.3"

    def test_empty_verdicts_safe(self) -> None:
        data = build_run_report_data([], [])
        assert data.total_wells == 0
        assert data.pass_count == 0
        assert data.final_96_filled == 0


# ── render_html tests ─────────────────────────────────────────────────────────


class TestRenderHtml:
    def _build_data(self) -> RunReportData:
        verdicts = _make_sample_verdicts()
        replicates = _make_sample_replicates()
        data = build_run_report_data(
            verdicts,
            replicates,
            run_meta=_make_run_meta(),
            project_name="TestProject",
            kuma_version="0.1.0",
        )
        data._raw_verdicts = verdicts  # type: ignore[attr-defined]
        return data

    def test_returns_string(self) -> None:
        html = render_html(self._build_data())
        assert isinstance(html, str)
        assert len(html) > 100

    def test_is_valid_html5(self) -> None:
        html = render_html(self._build_data())
        assert "<!DOCTYPE html>" in html
        assert "<html" in html
        assert "</html>" in html

    def test_project_name_present(self) -> None:
        html = render_html(self._build_data())
        assert "TestProject" in html

    def test_pass_count_present(self) -> None:
        html = render_html(self._build_data())
        # "4" is the PASS count; check it appears in card context
        assert ">4<" in html or ">4 " in html or "4</div>" in html

    def test_nb01_present(self) -> None:
        html = render_html(self._build_data())
        assert "NB01" in html

    def test_nb02_present(self) -> None:
        html = render_html(self._build_data())
        assert "NB02" in html

    def test_flow_cell_id_present(self) -> None:
        html = render_html(self._build_data())
        assert "FAX12345" in html

    def test_kuma_version_in_footer(self) -> None:
        html = render_html(self._build_data())
        assert "0.1.0" in html

    def test_no_raw_user_content_unescaped(self) -> None:
        """Project names with HTML special chars must be escaped."""
        verdicts = _make_sample_verdicts()
        replicates = _make_sample_replicates()
        data = build_run_report_data(
            verdicts, replicates, project_name="<script>alert(1)</script>"
        )
        html = render_html(data)
        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    def test_svg_plate_map_present(self) -> None:
        html = render_html(self._build_data())
        assert "<svg" in html
        assert "<circle" in html

    def test_inline_css_no_external_links(self) -> None:
        html = render_html(self._build_data())
        assert "rel=\"stylesheet\"" not in html
        assert "<link" not in html.lower().split("<style")[0]


# ── pdf_export graceful fallback tests ───────────────────────────────────────


class TestPdfExport:
    def _build_data(self) -> RunReportData:
        verdicts = _make_sample_verdicts()
        replicates = _make_sample_replicates()
        data = build_run_report_data(verdicts, replicates, project_name="PDFTest")
        data._raw_verdicts = verdicts  # type: ignore[attr-defined]
        return data

    def test_html_format_written(self, tmp_path: Path) -> None:
        output = tmp_path / "report.html"
        result = export_pdf(self._build_data(), output)
        assert result["error"] is None
        # weasyprint not expected in test env; either html or pdf
        written = Path(result["output_path"])
        assert written.exists()
        content = written.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content

    def test_no_weasyprint_graceful(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """When weasyprint is absent, export_pdf writes HTML fallback."""
        monkeypatch.setattr(shutil, "which", lambda _name: None)

        # Patch importlib to report weasyprint absent
        import importlib.util as _ilu
        original_find_spec = _ilu.find_spec

        def _fake_find_spec(name: str, *args, **kwargs):
            if name == "weasyprint":
                return None
            return original_find_spec(name, *args, **kwargs)

        monkeypatch.setattr(_ilu, "find_spec", _fake_find_spec)

        output = tmp_path / "report.pdf"
        result = export_pdf(self._build_data(), output)

        assert result["weasyprint_available"] is False
        assert result["format"] == "html"
        fallback = Path(result["output_path"])
        assert fallback.exists()
        assert fallback.suffix == ".html"
        assert "<!DOCTYPE html>" in fallback.read_text(encoding="utf-8")

    def test_result_has_required_keys(self, tmp_path: Path) -> None:
        output = tmp_path / "report.html"
        result = export_pdf(self._build_data(), output)
        for key in ("output_path", "format", "weasyprint_available", "error"):
            assert key in result
