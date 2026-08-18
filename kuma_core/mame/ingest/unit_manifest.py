"""Run-level membership manifest for a MAME demux output root.

The per-unit :mod:`kuma_core.mame.ingest.stage_marker` answers "is THIS unit
complete", by comparing a unit directory against its own recorded inventory.
Nothing answered the other question: "which units belong to the run that this
directory holds".  A demux output root is stable across re-runs and nothing
removes what an earlier run left in it, so a second run exporting into a folder
that already holds ``sort_barcode15/`` from the day before ends up with six unit
directories where three were selected, each one internally consistent and each
one carrying a valid stage marker.  Every unit passes its own check and the
directory as a whole is still wrong.

On 2026-08-10 that happened on a real run: three native barcodes were selected,
the export folder already held three units of 14, 15 and 9 wells from the
previous day, and the verdict table came back with six plates.  Four verdict
workbooks were produced from it before anyone noticed.

This module records MEMBERSHIP at the output root, so a reader can tell a unit
of the current run from a leftover by looking at the directory rather than by
remembering to pass a parameter.  The producer
(:func:`kuma_core.mame.ingest.run_pipeline.ingest_run_folder`) writes the
manifest when it finishes; the consumer
(:func:`kuma_core.mame.ingest.fasta_parser.load_barcode_directory`) reads it and
narrows itself to the units named there.

A directory with NO manifest keeps its old behaviour and every subdirectory is
read.  That is the externally-sorted directory a user points MAME at directly,
which this pipeline did not produce and has no membership statement about.
Absence of a manifest therefore means "no claim", never "no units".

Manifest filename: ``.mame_run_units.json``.  The leading dot plus the ``.json``
suffix keep it out of every ``*.fasta`` / ``*.fa`` / ``*.fas`` glob, and the top
level of the output root is walked for directories only, so the file is inert
for every existing reader.  This is the same naming rule
:mod:`kuma_core.mame.ingest.stage_marker` follows.

Schema (version 1)::

    {
      "schema_version": 1,
      "kind": "mame_run_units",
      "run_dir": "<absolute path of the ingested run directory>",
      "native_barcodes": ["barcode07", ...],   # as selected, [] when pooled
      "units": ["sort_barcode07", ...],        # subdir names this run produced
      "written_at": "2026-08-13T04:05:06Z"
    }

``units`` is the load-bearing field and the only one a reader acts on.  The
other three are there so an operator (or a support session) can tell from the
file alone which run owns the directory, which is what the disk state failed to
say when this defect was found.

A manifest that cannot be parsed as the expected JSON object, or that names no
units, is treated as ABSENT rather than fatal, exactly as a corrupt stage marker
is.  Degrading to "read everything" restores the pre-manifest behaviour, which
is wrong in the narrow way this module exists to fix but is never worse than the
state the pipeline shipped in for the last four runs; raising instead would turn
a truncated write into an unopenable results folder.

The two stamped fields are read back, and the three answers are not the same
answer.  ``kind`` says whether MAME wrote this file at all: anything else at
this name is not a membership statement MAME made, so it is ABSENT for the same
reason unparseable bytes are, and honouring its ``units`` (which is what
happened before) let a file nobody wrote decide which plates a run scores.
``schema_version`` says whether this build can read the statement: a version
this build does not know comes from a NEWER kuma, and both other answers are
wrong there.  Trusting it reads a field that may no longer mean what it meant in
version 1, and folding it to "no claim" reads every leftover in the folder,
which is exactly the defect this module exists to prevent and which the newer
build was recording membership to avoid.  So an unknown schema REFUSES the run
and says which version wrote the folder.  There is no truncation risk in that
choice: a half-written manifest is not valid JSON and never reaches the version
check, and the write is atomic besides.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any

from kuma_core.shared.atomic_write import atomic_write_text

MANIFEST_FILENAME = ".mame_run_units.json"
MANIFEST_SCHEMA_VERSION = 1
MANIFEST_KIND = "mame_run_units"

__all__ = [
    "MANIFEST_FILENAME",
    "MANIFEST_KIND",
    "MANIFEST_SCHEMA_VERSION",
    "UnreadableManifestError",
    "manifest_path",
    "read_run_manifest",
    "read_manifest_units",
    "units_of",
    "write_run_manifest",
]


def manifest_path(output_root: Path) -> Path:
    """Return the manifest path for *output_root* (does not check existence)."""
    return Path(output_root) / MANIFEST_FILENAME


def write_run_manifest(
    output_root: Path,
    *,
    run_dir: Path,
    native_barcodes: list[str] | None,
    units: list[str],
) -> Path:
    """Atomically write the run membership manifest into *output_root*.

    Callers write this LAST, after every unit directory of the run is on disk,
    for the same reason a stage marker is written last: the manifest is the
    statement that this set of units is what the run produced, and a manifest
    naming a unit that is not there yet would narrow a later read down to an
    incomplete set.

    Args:
        output_root: The demux output directory (``demux_output_dir``).
        run_dir: The run directory that was ingested, recorded so the folder
            says which run owns it.
        native_barcodes: The native barcodes selected for this run, or ``None``
            in single-pool mode where none were selected.  Recorded as ``[]``
            when absent, since "pooled" is a real answer and not a missing one.
        units: The top-level subdirectory names this run produced.  This is the
            field the reader acts on.

    Returns:
        The resolved absolute path of the written manifest.
    """
    payload: dict[str, Any] = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "kind": MANIFEST_KIND,
        "run_dir": str(Path(run_dir)),
        "native_barcodes": [str(nb) for nb in (native_barcodes or [])],
        "units": [str(u) for u in units],
        "written_at": datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
    }
    content = json.dumps(payload, ensure_ascii=False, indent=2)
    return atomic_write_text(manifest_path(output_root), content)


class UnreadableManifestError(RuntimeError):
    """A membership claim this build recognises but cannot interpret.

    Raised only for a manifest whose ``kind`` is this module's and whose
    ``schema_version`` is newer than :data:`MANIFEST_SCHEMA_VERSION`.  Every
    other unusable file is reported as absent instead; see the module docstring
    for why this one case is different.
    """


def read_run_manifest(output_root: Path) -> dict[str, Any] | None:
    """Return the parsed manifest for *output_root*, or ``None`` when absent.

    A file that is missing, unreadable, not JSON, not a JSON object, or not
    stamped with this module's ``kind`` is reported as ``None``.  Every caller
    answers ``None`` by treating the directory as one that carries no membership
    claim, which is the behaviour that predates this module.

    The check lives here rather than at the call site because this is the
    function whose return value is trusted.  A caller that validated the stamp
    itself would protect only itself, and the next reader of the same file would
    trust whatever is in it, which is the shape of the defect this module was
    written to remove.

    Raises:
        UnreadableManifestError: the file is this module's manifest and states a
            ``schema_version`` newer than this build knows.  A newer kuma wrote
            the folder, so neither trusting the claim nor discarding it is safe;
            see the module docstring.
    """
    path = manifest_path(output_root)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    if data.get("kind") != MANIFEST_KIND:
        return None
    version = data.get("schema_version")
    if not isinstance(version, int) or isinstance(version, bool):
        raise UnreadableManifestError(
            f"{path} is a MAME run manifest with no readable schema version "
            f"({version!r}). It states which plates the run in this folder "
            "produced, and a run cannot be scored against a claim that cannot "
            "be read. Re-run the demux into this folder, or point the analysis "
            "at a folder this build filled."
        )
    if version > MANIFEST_SCHEMA_VERSION:
        raise UnreadableManifestError(
            f"{path} was written by a newer version of kuma (manifest schema "
            f"{version}; this build reads {MANIFEST_SCHEMA_VERSION}). It states "
            "which plates the run in this folder produced, and ignoring it "
            "would score the leftovers of earlier runs alongside them. Update "
            "kuma, or re-run the demux into an empty folder with this build."
        )
    return data


def units_of(manifest: dict[str, Any] | None) -> set[str] | None:
    """Return the unit names *manifest* claims, or ``None`` for no claim.

    ``None`` means no membership statement: no manifest at all, or one whose
    ``units`` is missing, not a list, or empty once non-string entries are
    dropped.  An empty claim is folded into ``None`` deliberately.  A manifest
    naming zero units is indistinguishable from a truncated one, and honouring
    it would render an empty results table for a directory that plainly holds
    data, which is a worse failure than the over-reading this module fixes.

    Takes the parsed manifest rather than a path so a caller that also wants
    the recorded run identity reads the file once.
    """
    if manifest is None:
        return None
    raw = manifest.get("units")
    if not isinstance(raw, list):
        return None
    units = {u for u in raw if isinstance(u, str) and u}
    return units or None


def read_manifest_units(output_root: Path) -> set[str] | None:
    """Return the unit names *output_root* claims, or ``None`` for no claim.

    Convenience wrapper over :func:`read_run_manifest` plus :func:`units_of`
    for callers that need nothing but the membership set, and it raises what
    that reader raises (:class:`UnreadableManifestError`).
    """
    return units_of(read_run_manifest(output_root))
