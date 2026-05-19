"""``export_run_report`` JSON-RPC handler (A14 milestone).

Requires a prior successful ``analyze`` call. Reads cached VerdictRecord /
ReplicateResult / NgsRunMeta from SidecarState, derives distribution stats by
recomputing from file_size_kb (avoids R6 ownership conflict with analyze.py),
then renders an HTML or PDF run report.
"""

from __future__ import annotations

from typing import cast

from kuma_core.mame.ingest.run_meta import NgsRunMeta
from sidecar_mame.core import _validate_output_path, get_state

_ALLOWED_REPORT_EXTENSIONS = {".html", ".pdf"}


def handle_export_run_report(params: dict) -> dict:
    """Render and save a 1-page run report.

    Parameters (JSON-RPC params)
    ----------------------------
    output : str
        Destination file path. Must end in ``.html`` or ``.pdf``.
    format : "html" | "pdf"  (default "html")
        Requested output format.  PDF requires weasyprint; falls back to HTML
        gracefully when unavailable.
    project_name : str | None
        Display name inserted into the report header.

    Returns
    -------
    dict with keys:
      - ``output_path`` (str) — actual file written
      - ``format`` ("html" | "pdf") — format produced
      - ``weasyprint_available`` (bool)
      - ``fallback_to_html`` (bool) — True when PDF was requested but unavailable

    Raises
    ------
    RuntimeError
        When no prior ``analyze`` result is cached.
    ValueError
        When ``format`` is invalid or the output extension is unsupported.
    """
    from kuma_core.mame.report.builder import build_run_report_data
    from kuma_core.mame.report.html_renderer import render_html
    from kuma_core.mame.report.pdf_export import export_pdf
    from kuma_core.shared.version import KUMA_VERSION

    state = get_state()
    if state.last_verdicts is None or state.last_replicates is None:
        raise RuntimeError(
            "No prior analyze result. Run 'analyze' before 'export_run_report'."
        )

    requested_format = str(params.get("format", "html")).lower()
    if requested_format not in ("html", "pdf"):
        raise ValueError(
            f"Invalid format '{requested_format}'. Expected 'html' or 'pdf'."
        )

    output = _validate_output_path(
        params["output"], allowed_extensions=_ALLOWED_REPORT_EXTENSIONS
    )

    project_name: str | None = params.get("project_name") or None

    # Build unified report data (distribution recomputed internally)
    report_data = build_run_report_data(
        verdicts=state.last_verdicts,
        replicates=state.last_replicates,
        run_meta=cast(NgsRunMeta | None, state.last_run_meta),
        project_name=project_name,
        kuma_version=KUMA_VERSION,
    )
    # Attach raw verdicts for the plate map renderer
    report_data._raw_verdicts = state.last_verdicts  # type: ignore[attr-defined]

    if requested_format == "html":
        html_content = render_html(report_data)
        try:
            output.write_text(html_content, encoding="utf-8")
        except OSError as exc:
            raise RuntimeError(f"Failed to write HTML report: {exc}") from exc
        return {
            "output_path": str(output),
            "format": "html",
            "weasyprint_available": True,
            "fallback_to_html": False,
        }

    # PDF requested
    result = export_pdf(report_data, output)
    fallback = result.get("format") == "html" and requested_format == "pdf"
    if result.get("error"):
        raise RuntimeError(result["error"])
    return {
        "output_path": result["output_path"],
        "format": result["format"],
        "weasyprint_available": result.get("weasyprint_available", False),
        "fallback_to_html": fallback,
    }


__all__ = ["handle_export_run_report"]
