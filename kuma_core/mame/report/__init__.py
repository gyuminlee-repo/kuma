"""Run report generation for mame (A14 milestone).

Exposes ``build_run_report_data`` and ``render_html``.
PDF export via ``export_pdf`` is gated on weasyprint availability.
"""

from kuma_core.mame.report.builder import RunReportData, build_run_report_data
from kuma_core.mame.report.html_renderer import render_html
from kuma_core.mame.report.pdf_export import export_pdf

__all__ = ["RunReportData", "build_run_report_data", "render_html", "export_pdf"]
