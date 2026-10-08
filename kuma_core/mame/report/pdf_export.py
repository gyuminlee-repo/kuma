"""PDF export via weasyprint (optional, A14 milestone).

``export_pdf`` checks for weasyprint availability at call time using
``shutil.which``. If not installed, it writes the HTML fallback to *output*
(renaming .pdf → .html) and returns a status dict indicating the fallback.

Never raises — all errors are returned in the status dict.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from kuma_core.mame.report.builder import RunReportData
from kuma_core.mame.report.html_renderer import render_html


def _html_fallback_path(output: Path) -> Path:
    """Return the HTML fallback path for a .pdf output path."""
    return output.with_suffix(".html")


def export_pdf(data: RunReportData, output: Path) -> dict:
    """Export *data* to *output* as PDF (or HTML fallback).

    Parameters
    ----------
    data:
        Populated ``RunReportData`` instance.
    output:
        Destination file path. Should end in ``.pdf`` or ``.html``.

    Returns
    -------
    dict with keys:
      - ``output_path`` (str) — actual file written
      - ``format`` ("pdf" | "html") — format that was actually produced
      - ``weasyprint_available`` (bool)
      - ``error`` (str | None) — non-None when an error occurred
    """
    html_content = render_html(data)

    # ── weasyprint availability check ──────────────────────────────────────
    weasyprint_bin = shutil.which("weasyprint")
    if weasyprint_bin is None:
        # Try Python module import as fallback (installed but not on PATH)
        try:
            import importlib.util as _ilu
            spec = _ilu.find_spec("weasyprint")
            weasyprint_available = spec is not None
        except Exception:
            weasyprint_available = False
    else:
        weasyprint_available = True

    if not weasyprint_available:
        # Write HTML fallback
        fallback = _html_fallback_path(output) if output.suffix.lower() == ".pdf" else output.with_suffix(".html")
        try:
            fallback.write_text(html_content, encoding="utf-8")
        except OSError as exc:
            return {
                "output_path": str(fallback),
                "format": "html",
                "weasyprint_available": False,
                "error": f"Failed to write HTML fallback: {exc}",
            }
        return {
            "output_path": str(fallback),
            "format": "html",
            "weasyprint_available": False,
            "error": None,
        }

    # ── weasyprint available — write HTML temp then convert ────────────────
    import tempfile

    tmp_html: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            suffix=".html", delete=False, mode="w", encoding="utf-8"
        ) as fh:
            fh.write(html_content)
            tmp_html = Path(fh.name)

        output.parent.mkdir(parents=True, exist_ok=True)

        if weasyprint_bin:
            # Use CLI (avoids import overhead inside the sidecar process)
            result = subprocess.run(
                [weasyprint_bin, str(tmp_html), str(output)],
                shell=False,
                capture_output=True,
                timeout=60,
            )
            if result.returncode != 0:
                stderr = result.stderr.decode("utf-8", errors="replace")[:500]
                return {
                    "output_path": str(output),
                    "format": "pdf",
                    "weasyprint_available": True,
                    "error": f"weasyprint exited {result.returncode}: {stderr}",
                }
        else:
            # Module import path
            import weasyprint  # type: ignore[import-untyped]

            weasyprint.HTML(filename=str(tmp_html)).write_pdf(str(output))

    except subprocess.TimeoutExpired:
        return {
            "output_path": str(output),
            "format": "pdf",
            "weasyprint_available": True,
            "error": "weasyprint timed out after 60 s",
        }
    except Exception as exc:
        return {
            "output_path": str(output),
            "format": "pdf",
            "weasyprint_available": True,
            "error": str(exc),
        }
    finally:
        if tmp_html is not None:
            try:
                tmp_html.unlink(missing_ok=True)
            except OSError:
                pass

    return {
        "output_path": str(output),
        "format": "pdf",
        "weasyprint_available": True,
        "error": None,
    }


__all__ = ["export_pdf"]
