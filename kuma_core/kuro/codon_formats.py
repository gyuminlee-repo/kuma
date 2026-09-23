"""Convert the table formats a lab actually has into a kuma codon document.

WHAT THIS MODULE IS AND IS NOT.
It converts bytes into the shape ``codon_import.validate_codon_table_data``
reads, and back out again. It judges nothing. Every scientific rule -- the
codon set, the genetic code, the frequency sums, the counts cross-check --
belongs to ``codon_import`` and stays there, so a table imported as CSV is
held to exactly the rules a table imported as JSON is held to. The only
failures raised here are the ones the validator structurally cannot reach: a
file whose columns cannot be located at all produces no ``codons`` block for
the validator to judge, and "the amino acid column is missing" is not
expressible as any of V1-V35.

That single failure class is V36. One code rather than three (one per format)
because the user-visible sentence is the same sentence in all three cases --
this line of this file did not parse as this format -- and because each code
costs ten locales.

ORDER IS LOAD-BEARING.
``codon_import.canonical_digest`` hashes the codon list of each amino acid in
list order, and ``_check_codons`` builds that list in input order. So the
writers below emit codons in document order and the parsers keep file order,
which is what makes the export -> import round trip return the digest it
started with. Sorting on either side would be invisible until a workspace
opened on another machine reported a table it could not reproduce.

EXPORT FORMATS ARE THREE, NOT FOUR.
JSON, CSV and cusp are written; Kazusa is read only. Kazusa is a page a user
pastes from a 2007 database, not a file anyone should be handed by kuma, and
writing it would mint a fourth spelling of a table whose canonical form is
already decided (design note section 3.3: one storage canon).
"""

from __future__ import annotations

import csv
import io
import re
from typing import Any

# Codon/AA pairs are carried as plain lists so the result drops straight into
# ``validate_codon_table_data`` without a conversion step.
Document = dict[str, Any]

FORMATS: tuple[str, ...] = ("json", "csv", "cusp", "kazusa")
EXPORT_FORMATS: tuple[str, ...] = ("json", "csv", "cusp")

# Extensions the import RPC accepts. ``.txt`` is here only because a Kazusa
# paste saved from a browser lands as one; the format is chosen by the caller,
# never inferred from the suffix.
IMPORT_EXTENSIONS: frozenset[str] = frozenset({".json", ".csv", ".cusp", ".cut", ".txt"})
EXPORT_EXTENSIONS: dict[str, str] = {"json": ".json", "csv": ".csv", "cusp": ".cusp"}

CSV_HEADER = ("amino_acid", "codon", "relative_frequency")

# Header spellings seen in the wild. python-codon-tables writes the first of
# each group; the others cost nothing to accept and save a user an edit.
_CSV_AA_NAMES = {"amino_acid", "aminoacid", "aa", "amino acid"}
_CSV_CODON_NAMES = {"codon", "triplet"}
_CSV_FREQ_NAMES = {
    "relative_frequency", "relative frequency", "frequency",
    "fraction", "freq", "rel_freq",
}

# EMBOSS cusp data line: codon, AA, fraction, per-thousand, count.
# The count is optional because kuma's own cusp export omits it for a table
# that has no counts (writing 0 there would make N4 recompute every fraction
# to zero and V24 would then reject a table that was never wrong).
_CUSP_LINE = re.compile(
    r"^\s*([A-Za-z]{3})\s+([A-Za-z*])\s+"
    r"([0-9]*\.?[0-9]+)\s+([0-9]*\.?[0-9]+)(?:\s+([0-9]+))?\s*$"
)

# Kazusa CUTG block: "UUU F 0.58 22.4 ( 10345)", several per line.
_KAZUSA_BLOCK = re.compile(
    r"([ACGUTacgut]{3})\s+([A-Za-z*])\s+"
    r"([0-9]*\.?[0-9]+)\s+([0-9]*\.?[0-9]+)\s*\(\s*([0-9]+)\s*\)"
)
# A triplet followed by a number but no amino acid: the exact shape of a
# Kazusa paste taken from the table that omits the AA column. It has to be
# told apart from ordinary prose, or "no blocks found" would be the message
# for a page that is in fact the right page missing one column.
_KAZUSA_NO_AA = re.compile(
    r"([ACGUacgu]{3})\s+([0-9]*\.?[0-9]+)\s+([0-9]*\.?[0-9]+)\s*\(\s*([0-9]+)\s*\)"
)


class CodonFormatError(ValueError):
    """A file that could not be read as the format it was declared to be.

    Carries the machine code and the ``{{placeholder}}`` values the UI needs,
    the same contract ``codon_import.Finding`` uses, so the dialog renders a
    parse failure and a rule failure through one code path.
    """

    def __init__(self, fmt: str, detail: str, line: int = 0) -> None:
        self.code = "V36"
        self.line = line
        # The line number is folded into ``detail`` rather than carried as a
        # third placeholder. scripts/i18n-parity.mjs compares the placeholder
        # set of a t() call against the sentence in both directions, so a
        # {{line}} in the sentence would have to be filled on every failure --
        # including the whole-file ones (an empty CSV, a Kazusa paste with no
        # blocks) that have no line to name. "line 0" in ten languages is
        # worse than a sentence that names a line only when there is one.
        self.params = {
            "format": fmt,
            "detail": f"line {line}: {detail}" if line else detail,
        }
        self.detail = f"This file could not be read as {fmt}: {self.params['detail']}."
        super().__init__(self.detail)


def _fraction(text: str, fmt: str, line: int) -> float:
    try:
        return float(text)
    except ValueError:  # pragma: no cover - the regexes already shaped this
        raise CodonFormatError(fmt, f"'{text}' is not a number", line) from None


def _append(codons: dict, counts: dict, aa: str, codon: str,
            freq: float, count: int | None) -> None:
    """Record one row, keeping first-seen order for both the AA and the codon.

    Nothing is deduplicated or reordered. A file that lists a codon twice
    keeps both rows so V18 reports the duplicate, which is the rule that owns
    that complaint.
    """
    codons.setdefault(aa, []).append([codon, freq])
    if count is not None:
        counts.setdefault(aa, []).append([codon, count])


# --- readers ---------------------------------------------------------------


def parse_csv(text: str) -> Document:
    """Read a three-column amino acid / codon / frequency table."""
    try:
        rows = list(csv.reader(io.StringIO(text)))
    except csv.Error as exc:
        raise CodonFormatError("csv", str(exc)) from None
    rows = [r for r in rows if any(c.strip() for c in r)]
    if not rows:
        raise CodonFormatError("csv", "the file is empty")

    header = [c.strip().lower().lstrip("﻿") for c in rows[0]]
    try:
        i_aa = next(i for i, h in enumerate(header) if h in _CSV_AA_NAMES)
        i_codon = next(i for i, h in enumerate(header) if h in _CSV_CODON_NAMES)
        i_freq = next(i for i, h in enumerate(header) if h in _CSV_FREQ_NAMES)
    except StopIteration:
        raise CodonFormatError(
            "csv",
            "the header needs an amino acid column, a codon column and a "
            f"frequency column; it has {header}",
            1,
        ) from None

    codons: dict[str, list] = {}
    counts: dict[str, list] = {}
    width = max(i_aa, i_codon, i_freq) + 1
    for n, row in enumerate(rows[1:], start=2):
        if len(row) < width:
            raise CodonFormatError(
                "csv", f"this row has {len(row)} column(s), not {width}", n
            )
        aa = row[i_aa].strip()
        codon = row[i_codon].strip()
        if not aa or not codon:
            raise CodonFormatError("csv", "the amino acid or codon cell is empty", n)
        _append(codons, counts, aa, codon, _fraction(row[i_freq].strip(), "csv", n), None)
    if not codons:
        raise CodonFormatError("csv", "the file has a header but no rows")
    return {"codons": codons}


def parse_cusp(text: str) -> Document:
    """Read EMBOSS ``cusp`` output.

    Comment lines start with ``#``, which is where cusp puts ``CdsCount`` and
    the GC figures. Neither a species name nor a taxid is in the file at all
    (design note section 3.3), so the caller supplies both.
    """
    codons: dict[str, list] = {}
    counts: dict[str, list] = {}
    saw_comment = False
    for n, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            saw_comment = True
            continue
        m = _CUSP_LINE.match(line)
        if not m:
            raise CodonFormatError(
                "cusp",
                "a cusp row is 'Codon AA Fraction Frequency Number'; this row "
                f"is {len(line.split())} field(s)",
                n,
            )
        codon, aa, frac, _per_thousand, count = m.groups()
        _append(
            codons, counts, aa, codon,
            _fraction(frac, "cusp", n),
            int(count) if count is not None else None,
        )
    if not codons:
        raise CodonFormatError(
            "cusp",
            "no codon rows were found"
            + (" below the header" if saw_comment else ""),
        )
    document: Document = {"codons": codons}
    if counts:
        document["counts"] = counts
    return document


def parse_kazusa(text: str) -> Document:
    """Read a Kazusa CUTG page pasted as text.

    The alphabet is RNA. It is deliberately left that way: N1 converts U to T
    inside the validator and reports how many codons it touched, so the user
    is told what changed rather than having it done silently here.
    """
    codons: dict[str, list] = {}
    counts: dict[str, list] = {}
    for m in _KAZUSA_BLOCK.finditer(text):
        codon, aa, frac, _per_thousand, count = m.groups()
        _append(codons, counts, aa.upper(), codon.upper(),
                _fraction(frac, "kazusa", 0), int(count))
    if not codons:
        if _KAZUSA_NO_AA.search(text):
            raise CodonFormatError(
                "kazusa",
                "the pasted text has codons and numbers but no amino acid "
                "letter; copy the table that shows the amino acid column",
            )
        raise CodonFormatError(
            "kazusa",
            "no 'codon amino-acid fraction per-thousand (count)' blocks were found",
        )
    return {"codons": codons, "counts": counts}


_READERS = {"csv": parse_csv, "cusp": parse_cusp, "kazusa": parse_kazusa}


def parse_table_text(text: str, fmt: str) -> Document:
    """Convert *text* in *fmt* into the body of a kuma codon document.

    ``json`` is not handled here: a kuma JSON file goes straight to
    ``codon_import.validate_codon_table_file``, which owns V3's line and
    column reporting. Routing it through this module would replace a precise
    JSON syntax error with a generic V36.
    """
    reader = _READERS.get(fmt)
    if reader is None:
        raise CodonFormatError(fmt, "unknown table format")
    return reader(text)


# --- writers ---------------------------------------------------------------


def _pairs(document: Document) -> list[tuple[str, str, float]]:
    out = []
    for aa, entries in (document.get("codons") or {}).items():
        for codon, freq in entries:
            out.append((aa, codon, float(freq)))
    return out


def _count_index(document: Document) -> dict[tuple[str, str], int]:
    index: dict[tuple[str, str], int] = {}
    for aa, entries in (document.get("counts") or {}).items():
        for codon, value in entries:
            index[(aa, codon)] = int(value)
    return index


def format_csv(document: Document) -> str:
    """Write the three-column CSV python-codon-tables reads."""
    buf = io.StringIO(newline="")
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(CSV_HEADER)
    for aa, codon, freq in _pairs(document):
        # repr, not a fixed number of decimals: a rounded fraction changes the
        # canonical digest, and the round-trip test exists to catch exactly
        # that. repr(float) is the shortest string that reads back identical.
        writer.writerow([aa, codon, repr(freq)])
    return buf.getvalue()


def format_cusp(document: Document) -> str:
    """Write EMBOSS-shaped cusp output.

    The Number column is written only when the document carries counts. An
    exported table with no counts must not claim zero counts: N4 would then
    recompute every fraction from those zeros and V24 would reject the file
    kuma itself had just written.
    """
    counts = _count_index(document)
    rows = _pairs(document)
    total = sum(counts.values()) or 0
    header = [
        f"#Codon usage table for {document.get('name', document.get('key', ''))}",
        "#",
        "#Coding GC 0.00%",
        "#",
        "#Codon AA Fraction Frequency Number" if counts
        else "#Codon AA Fraction Frequency",
    ]
    lines = list(header)
    for aa, codon, freq in rows:
        count = counts.get((aa, codon))
        # Frequency is the per-thousand figure cusp reports. With no counts
        # there is no total to divide by, so it is written as 0.000 rather
        # than invented; the importer ignores the column either way.
        per_thousand = (count / total * 1000.0) if (count is not None and total) else 0.0
        cells = [codon, aa, repr(freq), f"{per_thousand:.3f}"]
        if counts:
            cells.append(str(count if count is not None else 0))
        lines.append(" ".join(cells))
    return "\n".join(lines) + "\n"


_WRITERS = {"csv": format_csv, "cusp": format_cusp}


def format_table(document: Document, fmt: str) -> str:
    """Serialise *document* as *fmt*. ``json`` is written by the caller."""
    writer = _WRITERS.get(fmt)
    if writer is None:
        raise CodonFormatError(fmt, "unknown export format")
    return writer(document)
