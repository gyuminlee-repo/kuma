"""Handlers: compute a codon table from a genome, import one, export one out.

WHY THERE IS STILL NO DELETE RPC.
The design note's Phase 3 listed a delete RPC alongside import and export. It
is not here, and Phase 4b adding a third RPC does not change that.
Replacing a table is what a user actually does, and V10 plus ``overwrite``
already covers that end to end; deleting is removing a file from a folder the
app already offers an "Open folder" button for. A third RPC would add a
destructive path, its confirmation dialog and ten locales for both, to do
what the file manager does. Recorded as a deliberate narrowing of the note.

WHY COMPUTE SHARES IMPORT'S JUDGE-AND-INSTALL TAIL RATHER THAN COPYING IT.
``_judge_and_install`` is the one place a document is measured against the
disk (``import_context``), validated, rebuilt from the validator's normalised
form and written. Three entrants now reach it -- import, its ``dry_run``
preview and compute -- and the reason it is one function is the reason the
preview exists at all: a preview that runs different code from the install
reports findings the install would not. A computed table is held to exactly
the rules a JSON file dropped in the folder is held to, and there is no
second assembly of the context for V9/V10 to pass vacuously against.

WHY COMPUTE DOES NOT RUN ON A BACKGROUND THREAD.
It is not in ``dispatcher._ASYNC_METHODS``. Measured on this branch, 6,000
coding sequences take 0.5 s on a Linux filesystem and 4.2 s over a Windows
drvfs mount, and ``_SYNC_DISPATCH`` turns threaded dispatch off on frozen
Windows anyway, which is the shipping platform. Running on the main thread
means ``_progress`` writes reach stdout as the tally advances rather than
after it, so the notification arrives while the scan is still going. A
background thread would buy nothing here and would put the registry refresh
and the install write on a second thread.

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

from kuma_core.kuro import codon_compute as _compute
from kuma_core.kuro import codon_formats as _formats
from kuma_core.kuro.codon_import import validate_codon_table_data
from kuma_core.kuro.codon_table import _document_from_report

import sidecar_kuro.core as _core
from sidecar_kuro.core import (
    _ALLOWED_GENOME_EXTENSIONS,
    _progress,
    _validate_filepath,
    _validate_output_path,
)
from sidecar_kuro.handlers.misc import ensure_user_codon_dir
from sidecar_kuro.models import (
    ComputeCodonTableParams,
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

    # The genetic code of a kuma JSON file belongs to the file, never to the
    # dialog. It is an input to canonical_digest, so overwriting a colleague's
    # declared code with the dialog's default gives their table a different
    # digest here than the one their machine recorded -- the section 8.1 hole
    # this whole feature exists to close, reopened by the import path. V16
    # cannot catch it: NCBI tables 1 and 11 have identical forward tables and
    # identical stop codons (measured, Bio 1.85; they differ only in start
    # codons), so a table declared as 1 and read as 11 passes every codon-to-
    # amino-acid check there is. Left absent, the validator applies V14 and
    # _document_from_report writes report.genetic_code into the stored file,
    # which is what V14's sentence promises the user.
    #
    # The converted formats are the opposite case: CSV, cusp and a Kazusa
    # paste carry no genetic code at all, so the dialog's value is the only
    # one there is.
    if p.format != "json":
        document["genetic_code"] = p.genetic_code or 11

    if p.aliases:
        document["aliases"] = list(p.aliases)
    document.setdefault("aliases", [])
    if p.source:
        document["source"] = p.source
    document.setdefault("source", "")
    if p.format != "json":
        document.setdefault("provenance", _provenance(p, "counts" in document))
    return document


def _judge_and_install(
    registry,
    document: dict[str, Any],
    *,
    key: str,
    overwrite: bool,
    dry_run: bool,
) -> dict[str, Any]:
    """Validate *document* against the installed tables and, unless *dry_run*, write it.

    The one tail three entrants share: import, its preview and compute. See the
    module docstring for why it is one function rather than three copies.

    The context is built by the registry, from the same scan the dropdown is
    built from, so V9/V10/V29/V30 are judged against what is actually installed
    rather than against a second hand-assembled picture of it.
    """
    context = registry.import_context(key, overwrite=overwrite)
    report = validate_codon_table_data(document, stem=key, context=context)

    result: dict[str, Any] = {
        "ok": report.ok,
        "installed": False,
        "key": key,
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
    stored = _document_from_report(key, report, document)
    result["document"] = stored

    if dry_run:
        return result

    directory = ensure_user_codon_dir()
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{key}.json"
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


def handle_import_codon_table(params: dict) -> dict:
    """Validate a table and, if it passes, install it as ``<key>.json``.

    ``dry_run`` runs everything except the write, which is what the dialog's
    preview calls. Preview and import therefore report the same findings from
    the same code path rather than from two implementations that can drift.
    """
    p = ImportCodonTableParams(**params)
    registry = _core.get_registry()
    # Re-read the folder before judging. scan() is cached, and the cache is
    # exactly as old as the last listing: a user who opened the folder, dropped
    # a table in and then imported the same key would have V10 answered from a
    # picture of the disk taken before their file existed, and os.replace would
    # overwrite it without a word. A path that writes has to judge against the
    # disk rather than against a cache of it.
    registry.refresh()

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

    return _judge_and_install(
        registry, document, key=p.key, overwrite=p.overwrite, dry_run=p.dry_run
    )


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

# How many codons the preview names as diverging from the reference table. Ten
# rows is what fits beside the 21-row most-frequent block without the dialog
# scrolling; it is a display choice and nothing downstream reads it.
_DIVERGENT_ROWS = 10

# The bundled table a computed one is shown against. E. coli because it is the
# organism a user already has a feel for, which is what makes "your genome uses
# GCC where E. coli uses GCG" a sentence they can check against what they know.
# The comparison is presentational: nothing is rejected or adjusted by it.
_REFERENCE_KEY = "ecoli"


def _reference_fractions(registry) -> dict[str, float]:
    """codon -> fraction within its amino acid group, for the bundled reference.

    Read through the registry rather than from the resource file, so the
    preview compares against the same document ``list_organisms`` reports and
    the design engine looks codons up in. An absent or document-less reference
    yields an empty mapping and the preview simply omits the comparison, which
    is why the return is a plain dict and not an exception.
    """
    entry = next(
        (o for o in registry.scan()["organisms"] if o["key"] == _REFERENCE_KEY),
        None,
    )
    document = (entry or {}).get("document") or {}
    out: dict[str, float] = {}
    for pairs in (document.get("codons") or {}).values():
        for codon, fraction in pairs:
            out[str(codon)] = float(fraction)
    return out


def _preview(result: "_compute.ComputeResult", registry) -> dict[str, Any]:
    """The numbers the dialog shows before anything is written.

    Built here rather than in the frontend for one reason: every value below is
    derived from the tally, so deriving it in TypeScript would put a second
    implementation of the same arithmetic where no pytest can reach it. The
    frontend renders rows.

    Amino acid letters and codon strings are not translated. They are the
    IUPAC symbols, identical in every locale.
    """
    codons = result.document["codons"]
    counts = result.document["counts"]
    count_of = {
        codon: value
        for pairs in counts.values()
        for codon, value in pairs
    }

    top: list[dict[str, Any]] = []
    for aa in _compute.AMINO_ACID_ORDER:
        pairs = codons.get(aa) or []
        if not pairs:
            continue
        codon, fraction = pairs[0]
        top.append({
            "aa": aa,
            "codon": codon,
            "fraction": fraction,
            "count": count_of.get(codon, 0),
        })

    reference = _reference_fractions(registry)
    divergent: list[dict[str, Any]] = []
    if reference:
        rows = []
        for aa, pairs in codons.items():
            for codon, fraction in pairs:
                if codon not in reference:
                    continue
                rows.append({
                    "aa": aa,
                    "codon": codon,
                    "fraction": fraction,
                    "reference_fraction": reference[codon],
                    "delta": fraction - reference[codon],
                })
        rows.sort(key=lambda r: (-abs(r["delta"]), r["codon"]))
        divergent = rows[:_DIVERGENT_ROWS]

    return {
        "source_format": result.document["provenance"]["source_format"],
        "cds_total": result.cds_total,
        "cds_counted": result.cds_counted,
        "cds_excluded": dict(result.cds_excluded),
        "excluded_examples": {k: list(v) for k, v in result.excluded_examples.items()},
        "codon_count": result.codon_count,
        "top_codons": top,
        "reference_key": _REFERENCE_KEY if reference else None,
        "divergent_codons": divergent,
    }


def _empty_preview() -> dict[str, Any]:
    """The preview block of a rejection, so the field is never absent.

    A frontend that has to test for the presence of ``preview`` as well as for
    its contents grows two code paths where one would do, and the zeros here
    say the same thing the rejection says: nothing was counted.
    """
    return {
        "source_format": "",
        "cds_total": 0,
        "cds_counted": 0,
        "cds_excluded": {},
        "excluded_examples": {},
        "codon_count": 0,
        "top_codons": [],
        "reference_key": None,
        "divergent_codons": [],
    }


def _refused(code: str, params: dict, detail: str, key: str) -> dict[str, Any]:
    """A compute rejection, carrying the empty preview the reply always has.

    Compute replies with a ``preview`` block whatever happens, so the dialog
    reads one shape rather than testing for the field and then for its
    contents. ``_rejected`` stays without it: an import rejection has no tally
    to report and a field that is always empty is a field that lies.
    """
    rejection = _rejected([_finding(code, params, detail)], key)
    rejection["preview"] = _empty_preview()
    return rejection


def handle_compute_codon_table(params: dict) -> dict:
    """Count the codons of a genome file and install the table it yields.

    ``dry_run`` is the dialog's preview and runs everything except the write,
    so the findings shown before installing are the findings the install
    produces. The scan itself runs either way: there is no cheaper way to know
    how many coding sequences a file holds than to read them.

    THE CALLER'S GENETIC CODE IS WRITTEN OUT UNCHANGED. No ``or 11`` and no
    correction. ``compute_codon_table`` refuses a code it cannot count under
    rather than substituting one, and that refusal arrives here as G2.
    """
    p = ComputeCodonTableParams(**params)
    registry = _core.get_registry()
    # Re-read the folder before judging, for the reason the import path does:
    # scan() is cached, and a table dropped in after the last listing would
    # otherwise be overwritten by os.replace without V10 ever firing.
    registry.refresh()

    try:
        resolved = _validate_filepath(
            p.filepath, allowed_extensions=_ALLOWED_GENOME_EXTENSIONS
        )
    except ValueError as exc:
        # A suffix kuma does not read. Reported as a finding rather than
        # raised, so it lands in the dialog's localized list beside the
        # validator's own rejections instead of as a transport error in
        # English.
        return _refused("G1", {"detail": str(exc)}, str(exc), p.key)
    if not resolved.exists():
        raise FileNotFoundError(f"File does not exist: {p.filepath}")

    def on_progress(done: int, total: int | None) -> None:
        # ``value`` is the 0-100 the shared progress bar reads. A GenBank scan
        # has no denominator -- ``codon_compute`` passes total=None because it
        # will not parse the file twice to get one -- so the bar stays at 0 and
        # the count rides in the message. Deriving a percentage from ``done``
        # alone would draw a bar that fills at a rate no one can interpret.
        # Not capped below 100. tally_codons calls back once more at the end
        # with done == total, so a FASTA scan finishes at 100 the way the
        # design path's "Design complete" does. Nothing renders this number
        # outside a running job (JobQueuePanel uses it only for a running
        # job's ETA), so a value left behind is inert either way; ending at
        # the number that means finished is simply the honest one.
        pct = int(done * 100 / total) if total else 0
        _progress(pct, f"Counting codons: {done} coding sequences read")

    try:
        computed = _compute.compute_codon_table(
            resolved,
            key=p.key,
            name=p.name or p.key,
            genetic_code=p.genetic_code,
            genome_format=p.genome_format,
            taxid=p.taxid,
            aliases=tuple(p.aliases),
            source=p.source,
            on_progress=on_progress,
        )
    except _compute.UnsupportedGeneticCodeError as exc:
        return _refused(
            "G2", {"code": exc.code, "detail": str(exc)}, str(exc), p.key
        )
    except _compute.GenomeParseError as exc:
        return _refused("G1", {"detail": str(exc)}, str(exc), p.key)

    if computed.cds_counted == 0:
        # Every amino acid group is zero, so the validator would reject this
        # under V24 -- twenty-one times, once per group, none of which names
        # the actual problem. Two quite different files land here: one that is
        # not the genome the suffix claims (Biopython's GenBank parser yields
        # no records rather than raising on a malformed header, measured on
        # this branch), and one whose coding sequences were all filtered out.
        # G3 states which of the two it is by carrying the counts, and it is
        # one sentence the user can act on instead of twenty-one they cannot.
        detail = (
            f"No coding sequences were counted in {resolved.name}. "
            f"{computed.cds_total} were read and "
            f"{sum(computed.cds_excluded.values())} were excluded."
        )
        rejection = _refused(
            "G3", {"file": resolved.name, "total": computed.cds_total},
            detail, p.key,
        )
        rejection["preview"] = _preview(computed, registry)
        return rejection

    result = _judge_and_install(
        registry,
        computed.document,
        key=p.key,
        overwrite=p.overwrite,
        dry_run=p.dry_run,
    )
    result["preview"] = _preview(computed, registry)
    return result
