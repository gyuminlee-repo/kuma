"""Handlers: import a codon table into the user folder, export one out of it.

WHY THESE TWO AND NOT THREE.
The design note's Phase 3 listed a delete RPC alongside these. It is not here.
Replacing a table is what a user actually does, and V10 plus ``overwrite``
already covers that end to end; deleting is removing a file from a folder the
app already offers an "Open folder" button for. A third RPC would add a
destructive path, its confirmation dialog and ten locales for both, to do
what the file manager does. Recorded as a deliberate narrowing of the note.

WHAT THE KEY PARAMETER IS FOR.
The key comes from the caller, not from the file name. That is the whole
reason V9 and V10 become reachable in this phase. V9's own sentence tells the
user to "import under a different key, for example {{key}}_lab", which is only
actionable if the key is a field in the dialog; and while the key was forced to
equal the file stem (V8), a second import of the same table could never reach
V10. The stem the validator is handed is therefore the requested key, so V8
compares the key against itself here and V9/V10 do the real work.

NOTHING IS WRITTEN UNTIL EVERYTHING PASSES.
Design note section 6, principle 2: a rejected import leaves the disk alone.
The validator runs over the assembled document in memory, and only a report
with no errors reaches the file system -- through a temporary file and
``os.replace``, so a crash mid-write cannot leave a half-written table that
the next scan would report as corrupt.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kuma_core.kuro import codon_formats as _formats
from kuma_core.kuro.codon_import import validate_codon_table_data
from kuma_core.kuro.codon_table import _document_from_report

import sidecar_kuro.core as _core
from sidecar_kuro.core import _validate_filepath, _validate_output_path
from sidecar_kuro.handlers.misc import ensure_user_codon_dir
from sidecar_kuro.models import (
    ExportCodonTableParams,
    ImportCodonTableParams,
)

# The import dialog reads whatever the user points it at; the format is a
# parameter, never inferred from the suffix. ``.txt`` is accepted because a
# Kazusa page saved from a browser lands as one.
_ALLOWED_IMPORT_EXTENSIONS = set(_formats.IMPORT_EXTENSIONS)


def _finding(code: str, params: dict, detail: str) -> dict:
    """One finding in the shape the frontend already renders.

    Identical to what ``list_organisms`` puts in ``warnings`` and
    ``failed[].findings``, so ``formatCodonTableMessage`` handles an import
    rejection and a drop-in rejection through one code path.
    """
    return {"code": code, "params": params, "detail": detail}


def _rejected(findings: list[dict], key: str) -> dict:
    return {
        "ok": False,
        "installed": False,
        "key": key,
        "table_sha256": None,
        "errors": findings,
        "warnings": [],
        "normalizations": [],
        # A rejection before the validator ran examined nothing, and saying so
        # is the point of the counter: "no defects" from zero checks and "no
        # defects" from 200 checks must not read the same.
        "checks_performed": 0,
        "codons_examined": 0,
        "document": None,
        "path": None,
    }


def _read_source(p: ImportCodonTableParams) -> str:
    """Return the text to parse, from the pasted body or the chosen file."""
    if p.text:
        return p.text
    if not p.filepath:
        raise ValueError("Either text or filepath is required")
    resolved = _validate_filepath(
        p.filepath, allowed_extensions=_ALLOWED_IMPORT_EXTENSIONS
    )
    if not resolved.exists():
        raise FileNotFoundError(f"File does not exist: {p.filepath}")
    return resolved.read_text(encoding="utf-8")


def _provenance(p: ImportCodonTableParams, has_counts: bool) -> dict:
    """What this import can honestly say about where the numbers came from.

    A converted file knows its format and its origin file name and nothing
    else, so ``method`` records which of the two it is. It is not padding to
    silence V32: V32 warns that a run made with this table cannot say where
    its numbers came from, and after this it can.
    """
    return {
        "method": "counts" if has_counts else "fraction_only",
        "source_format": p.format,
        "source_file": Path(p.filepath).name if p.filepath else "(pasted text)",
        "generated_by": "kuma kuro import_codon_table",
        "generated_at": datetime.now(tz=timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
    }


def _assemble(p: ImportCodonTableParams) -> dict[str, Any]:
    """Turn the caller's parameters and the source bytes into one document.

    JSON keeps whatever the file declares and lets the caller's fields
    override; the converted formats carry no identity at all (design note
    section 3.3: a cusp file has neither a species name nor a taxid), so for
    those the caller's fields are the only source.
    """
    text = _read_source(p)

    if p.format == "json":
        # Not routed through codon_formats: a kuma JSON file is the canonical
        # form and json.JSONDecodeError already reports a line and a column,
        # which V3 exists to carry. Converting that into a generic V36 would
        # lose the position.
        body = json.loads(text)
        if not isinstance(body, dict):
            return {"__not_an_object__": type(body).__name__}
        document = dict(body)
    else:
        document = _formats.parse_table_text(text, p.format)

    document["key"] = p.key
    if p.name:
        document["name"] = p.name
    document.setdefault("name", p.key)
    if p.taxid is not None or "taxid" not in document:
        document["taxid"] = p.taxid
    if p.genetic_code is not None:
        document["genetic_code"] = p.genetic_code
    document.setdefault("genetic_code", 11)
    if p.aliases:
        document["aliases"] = list(p.aliases)
    document.setdefault("aliases", [])
    if p.source:
        document["source"] = p.source
    document.setdefault("source", "")
    if p.format != "json":
        document.setdefault("provenance", _provenance(p, "counts" in document))
    return document


def handle_import_codon_table(params: dict) -> dict:
    """Validate a table and, if it passes, install it as ``<key>.json``.

    ``dry_run`` runs everything except the write, which is what the dialog's
    preview calls. Preview and import therefore report the same findings from
    the same code path rather than from two implementations that can drift.
    """
    p = ImportCodonTableParams(**params)
    registry = _core.get_registry()

    try:
        document = _assemble(p)
    except _formats.CodonFormatError as exc:
        return _rejected([_finding(exc.code, exc.params, exc.detail)], p.key)
    except json.JSONDecodeError as exc:
        return _rejected(
            [
                _finding(
                    "V3",
                    {"line": exc.lineno, "col": exc.colno, "detail": exc.msg},
                    f"This file is not valid JSON (line {exc.lineno}, column "
                    f"{exc.colno}): {exc.msg}.",
                )
            ],
            p.key,
        )
    if "__not_an_object__" in document:
        kind = document["__not_an_object__"]
        return _rejected(
            [_finding("V4", {"type": kind},
                      f"A codon table must be a JSON object, not a {kind}.")],
            p.key,
        )

    # The context is built by the registry, from the same scan the dropdown is
    # built from, so V9/V10/V29/V30 are judged against what is actually
    # installed rather than against a second hand-assembled picture of it.
    context = registry.import_context(p.key, overwrite=p.overwrite)
    report = validate_codon_table_data(document, stem=p.key, context=context)

    result = {
        "ok": report.ok,
        "installed": False,
        "key": p.key,
        "table_sha256": report.table_sha256,
        "errors": [
            {"code": f.code, "params": f.params, "detail": f.detail}
            for f in report.errors
        ],
        "warnings": [
            {"code": f.code, "params": f.params, "detail": f.detail}
            for f in report.warnings
        ],
        "normalizations": [
            {"code": f.code, "params": f.params, "detail": f.detail}
            for f in report.normalizations
        ],
        "checks_performed": report.checks_performed,
        "codons_examined": report.codons_examined,
        "document": None,
        "path": None,
    }
    if not report.ok:
        return result

    # Built from what the validator normalised, not from the bytes that came
    # in. That is what makes the stored file, the document list_organisms
    # reports and the workspace embed one object with one digest.
    stored = _document_from_report(p.key, report, document)
    result["document"] = stored

    if p.dry_run:
        return result

    directory = ensure_user_codon_dir()
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{p.key}.json"
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(stored, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(tmp, target)

    # Same send -> relist -> select order saveCustomPolymerase uses: the
    # caches go before anything reads the folder again, so the frontend's
    # loadOrganisms() after this call sees the new table.
    registry.refresh()
    result["installed"] = True
    result["path"] = str(target)
    return result


def handle_export_codon_table(params: dict) -> dict:
    """Write an installed table out as JSON, CSV or cusp.

    The document exported is the one the registry reports, which is the
    normalised document rather than the bytes on disk. Exporting a table and
    importing it back therefore returns the same canonical digest, and that
    round trip is the control the format tests assert.
    """
    p = ExportCodonTableParams(**params)
    registry = _core.get_registry()
    scan = registry.scan()
    entry = next((o for o in scan["organisms"] if o["key"] == p.key), None)
    if entry is None:
        raise ValueError(f"No codon table named '{p.key}' is installed")
    document = entry.get("document")
    if document is None:
        raise ValueError(f"The codon table '{p.key}' carries no document to export")

    suffix = _formats.EXPORT_EXTENSIONS.get(p.format)
    if suffix is None:
        raise ValueError(f"Cannot export a codon table as '{p.format}'")
    resolved = _validate_output_path(p.filepath, allowed_extensions={suffix})

    if p.format == "json":
        text = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
    else:
        text = _formats.format_table(document, p.format)
    resolved.write_text(text, encoding="utf-8")
    return {"path": str(resolved), "format": p.format, "bytes": len(text.encode())}
