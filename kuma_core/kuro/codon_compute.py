"""Count codons in a genome and build a kuma codon table from the tally.

This is path A of the codon-table design note (section 3.4): the user has a
genome, not a table. Two inputs are accepted and they are alternatives, never
combined -- a GenBank ``.gbff``, whose CDS features carry the coordinates this
module slices, or a CDS FASTA (``cds_from_genomic.fna``), whose records are
already sliced.

WHAT THIS MODULE IS AND IS NOT.
It counts and it filters. It judges nothing else. The output is the shape
``codon_import.validate_codon_table_data`` reads, and every scientific rule --
the 64-codon set, the genetic code assignment, the frequency sums, the
counts/fraction cross-check -- stays in ``codon_import``, so a table computed
here is held to exactly the rules a table imported as JSON is held to.
``tests/test_codon_compute.py`` asserts that round trip rather than assuming
it.

THE GENETIC CODE COMES FROM THE CALLER AND IS NEVER INFERRED.
Neither input file states which NCBI ``transl_table`` its coding sequences
use in a form worth trusting -- a CDS FASTA has no such field at all, and a
``.gbff`` states it per feature where a single mis-annotated gene would flip
the choice for the whole genome. So the caller passes it, the default is 11,
and the value is echoed into the output verbatim. Rewriting a caller's 1 to 11
"because they assign codons identically" is the defect this module refuses to
repeat: codes 1 and 11 share ``forward_table`` and ``stop_codons`` and differ
only in start codons, so no codon-level check can tell them apart, yet the
declared number lands in the canonical digest and two colleagues would then
hold tables that disagree on paper about the same science.

NON-STANDARD CODES ARE REFUSED, NOT SILENTLY MISCOUNTED. A Mycoplasma genome
(code 4, TGA = Trp) counted under code 11 would report thousands of internal
stops and exclude nearly every CDS. ``UnsupportedGeneticCodeError`` names the
code instead. ``codon_import.SUPPORTED_GENETIC_CODES`` is the single list.

PROGRESS IS A PARAMETER, NOT A PRINT. ``on_progress(done, total)`` is called
as the tally advances so a caller can drive a progress bar.
``dispatcher.py`` turns asynchronous dispatch off entirely on frozen Windows
(``_SYNC_DISPATCH = sys.platform == "win32" and getattr(sys, "frozen", False)``),
which is the shipping platform, so a caller that cannot report progress has
nothing to show during the scan. Wiring that callback to an RPC notification
is not this module's job.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

from Bio import SeqIO
from Bio.Seq import UndefinedSequenceError
from Bio.SeqIO.FastaIO import SimpleFastaParser

from .codon_formats import Document
from .codon_import import (
    DEFAULT_GENETIC_CODE,
    LOW_CDS_WARN_THRESHOLD,
    LOW_CODON_COUNT_WARN_THRESHOLD,
    SUPPORTED_GENETIC_CODES,
    SUPPORTED_SCHEMA_VERSION,
    _code_table,
)

__all__ = [
    "AMINO_ACID_ORDER",
    "CdsRecord",
    "ComputeResult",
    "EXCLUSION_REASONS",
    "GenomeParseError",
    "LOW_CDS_WARN_THRESHOLD",
    "LOW_CODON_COUNT_WARN_THRESHOLD",
    "UnsupportedGeneticCodeError",
    "compute_codon_table",
    "iter_cds_fasta",
    "iter_cds_genbank",
    "tally_codons",
]

# --- tunable constants -----------------------------------------------------

# LOW_CDS_WARN_THRESHOLD and LOW_CODON_COUNT_WARN_THRESHOLD are imported, not
# redeclared. They are the same operating choice this pipeline already made in
# ``codon_import`` (V31), and that module says plainly what they are worth:
# THEY ARE OPERATING CHOICES, NOT LITERATURE CONSTANTS. No published threshold
# separates a representative codon table from an unrepresentative one, and the
# values 50 / 10,000 have no source. Declaring a second copy here would let a
# computed table and the same table re-imported disagree about whether its
# sample is small, which is a contradiction the user would have to resolve.

# The order amino acid keys are written in. It does not reach the canonical
# digest (``canonical_digest`` serialises with ``sort_keys=True``), so this is
# a readability choice only: it is the order the design note's section 3.2
# example file uses, which keeps a diff against that file readable.
AMINO_ACID_ORDER = "ARNDCQEGHILKMFPSTWYV*"

# Why each coding sequence can be dropped, in the order the filters run. The
# first matching reason wins, so a pseudogene whose length is not a multiple
# of three is reported once, as ``pseudo``. The order is the one section 3.2
# writes its ``cds_excluded`` block in.
EXCLUSION_REASONS: tuple[str, ...] = (
    "pseudo",
    "not_multiple_of_3",
    "internal_stop",
    "no_terminal_stop",
    "ambiguous_base",
)

_UNAMBIGUOUS = re.compile(r"^[ACGT]*$")

# ``[pseudo=true]`` in a RefSeq CDS FASTA description. RefSeq writes the
# bracketed qualifier list itself, so this is the file's own field rather
# than a guess from the protein name.
_FASTA_PSEUDO = re.compile(r"\[pseudo=true\]", re.IGNORECASE)


class GenomeParseError(ValueError):
    """The input could not be read as the genome format it was declared to be."""


class UnsupportedGeneticCodeError(ValueError):
    """A genetic code kuma will not count under. See the module docstring."""

    def __init__(self, code: Any) -> None:
        self.code = code
        super().__init__(
            f"kuma counts codons under NCBI genetic code "
            f"{' or '.join(str(c) for c in SUPPORTED_GENETIC_CODES)} only, "
            f"not {code!r}. A non-standard code such as 4 (Mycoplasma, "
            f"TGA = Trp) reassigns codons rather than only changing codon "
            f"preference, so counting a genome under the wrong one would "
            f"exclude almost every coding sequence as having internal stops."
        )


def _require_supported_code(code: Any) -> int:
    """Return *code* if kuma counts under it, else raise.

    ``bool`` and ``float`` are rejected explicitly. ``True in (1, 11)`` and
    ``11.0 in (1, 11)`` are both true in Python, so a plain membership test
    would accept ``genetic_code=True`` and write it into the file, where
    ``codon_import`` V15 -- which does make the isinstance check -- would then
    reject kuma's own output.
    """
    if isinstance(code, bool) or not isinstance(code, int) \
            or code not in SUPPORTED_GENETIC_CODES:
        raise UnsupportedGeneticCodeError(code)
    return code


# --- reading coding sequences ----------------------------------------------


@dataclass(frozen=True)
class CdsRecord:
    """One coding sequence as read from either input format."""

    identifier: str
    sequence: str
    pseudo: bool = False


@dataclass
class ComputeResult:
    """The computed table plus the numbers the caller has to be able to show."""

    document: Document
    cds_total: int
    cds_counted: int
    cds_excluded: dict[str, int]
    codon_count: int
    # identifier -> reason, for the first few of each reason. A preview that
    # says "164 excluded" without naming one record cannot be checked by the
    # person who has the file open.
    excluded_examples: dict[str, list[str]] = field(default_factory=dict)
    # Codes this result would raise on import, computed here so a preview can
    # show them before anything is written. V31 is the low-sample warning.
    warning_codes: tuple[str, ...] = ()


def iter_cds_fasta(path: Path | str) -> Iterator[CdsRecord]:
    """Yield the records of a CDS FASTA (``cds_from_genomic.fna``).

    The sequences are already sliced, so nothing here is extracted or
    reverse-complemented; that work was done by whoever wrote the file.
    """
    path = Path(path)
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for title, seq in SimpleFastaParser(handle):
                yield CdsRecord(
                    identifier=title.split(None, 1)[0] if title else "",
                    sequence=seq.upper(),
                    pseudo=bool(_FASTA_PSEUDO.search(title)),
                )
    except OSError as exc:
        raise GenomeParseError(f"Could not read {path.name}: {exc}") from exc


def iter_cds_genbank(path: Path | str) -> Iterator[CdsRecord]:
    """Yield one record per CDS feature of a GenBank flat file.

    ``feature.extract`` is what applies the strand and joins the segments of a
    compound location, so a gene on the minus strand or one split across a
    ``join(...)`` arrives here in reading frame rather than as genomic
    coordinates this module would have to re-implement.

    ``/codon_start`` is honoured. A value other than 1 means the feature's
    first base is not the first base of a codon, which happens on a
    5'-truncated gene; slicing the offset off keeps the remaining codons in
    frame instead of discarding a real gene or, worse, counting it shifted.
    """
    path = Path(path)
    try:
        records = SeqIO.parse(str(path), "genbank")
        for record in records:
            for feature in record.features:
                if feature.type != "CDS":
                    continue
                quals = feature.qualifiers
                pseudo = "pseudo" in quals or "pseudogene" in quals
                name = (
                    (quals.get("locus_tag") or quals.get("protein_id")
                     or quals.get("gene") or [""])[0]
                )
                try:
                    seq = str(feature.extract(record.seq)).upper()
                except UndefinedSequenceError as exc:
                    raise GenomeParseError(
                        f"{path.name} carries annotations but no sequence "
                        f"(record {record.id}). Download the GenBank file "
                        f"with sequence data, not the CONTIG-only form."
                    ) from exc
                try:
                    start = int((quals.get("codon_start") or ["1"])[0])
                except (TypeError, ValueError):
                    start = 1
                if start > 1:
                    seq = seq[start - 1:]
                yield CdsRecord(identifier=name, sequence=seq, pseudo=pseudo)
    except GenomeParseError:
        raise
    except (OSError, ValueError) as exc:
        raise GenomeParseError(
            f"Could not read {path.name} as a GenBank file: {exc}"
        ) from exc


# --- the tally -------------------------------------------------------------


def _classify(record: CdsRecord, stop_codons: frozenset[str]) -> str | None:
    """Return the reason *record* is excluded, or None if it is counted."""
    if record.pseudo:
        return "pseudo"
    seq = record.sequence
    if not seq or len(seq) % 3 != 0:
        return "not_multiple_of_3"
    codons = [seq[i:i + 3] for i in range(0, len(seq), 3)]
    if any(c in stop_codons for c in codons[:-1]):
        # Selenoprotein genes land here on purpose: their in-frame TGA is a
        # stop codon under codes 1 and 11 and is only read as Sec through a
        # /transl_except annotation this module does not honour. Counting one
        # would attribute a Sec codon to the stop tally.
        return "internal_stop"
    if codons[-1] not in stop_codons:
        return "no_terminal_stop"
    if not _UNAMBIGUOUS.match(seq):
        return "ambiguous_base"
    return None


@dataclass
class _Tally:
    counts: dict[str, dict[str, int]]
    cds_total: int = 0
    cds_counted: int = 0
    codon_count: int = 0
    excluded: dict[str, int] = field(default_factory=dict)
    examples: dict[str, list[str]] = field(default_factory=dict)


def tally_codons(
    records: Iterator[CdsRecord],
    genetic_code: int = DEFAULT_GENETIC_CODE,
    on_progress: Callable[[int, int | None], None] | None = None,
    total: int | None = None,
    progress_every: int = 500,
) -> _Tally:
    """Count codons over *records*, filtering as section 3.4 requires.

    ``on_progress(done, total)`` is called every ``progress_every`` records and
    once at the end, so ``done`` finishes equal to ``cds_total``. ``total`` is
    passed through untouched: this function consumes an iterator and cannot
    know the length of one.
    """
    genetic_code = _require_supported_code(genetic_code)
    mapping = _code_table(genetic_code)
    stop_codons = frozenset(c for c, aa in mapping.items() if aa == "*")

    counts: dict[str, dict[str, int]] = {aa: {} for aa in AMINO_ACID_ORDER}
    for codon, aa in mapping.items():
        counts[aa][codon] = 0
    tally = _Tally(counts=counts)
    tally.excluded = {reason: 0 for reason in EXCLUSION_REASONS}

    for record in records:
        tally.cds_total += 1
        reason = _classify(record, stop_codons)
        if reason is not None:
            tally.excluded[reason] += 1
            bucket = tally.examples.setdefault(reason, [])
            if len(bucket) < 5 and record.identifier:
                bucket.append(record.identifier)
        else:
            seq = record.sequence
            tally.cds_counted += 1
            for i in range(0, len(seq), 3):
                codon = seq[i:i + 3]
                aa = mapping.get(codon)
                if aa is not None:
                    counts[aa][codon] += 1
                    tally.codon_count += 1
        if on_progress is not None and tally.cds_total % progress_every == 0:
            on_progress(tally.cds_total, total)

    if on_progress is not None:
        on_progress(tally.cds_total, total)
    return tally


# --- assembling the document -----------------------------------------------


def _count_fasta_records(path: Path) -> int:
    n = 0
    with path.open("rb") as handle:
        for line in handle:
            if line.startswith(b">"):
                n += 1
    return n


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _format(path: Path, declared: str | None) -> str:
    if declared is not None:
        if declared not in ("fasta", "genbank"):
            raise GenomeParseError(
                f"Unknown genome format '{declared}'. Use 'fasta' or 'genbank'."
            )
        return declared
    suffix = path.suffix.lower()
    if suffix in (".gbff", ".gb", ".gbk", ".genbank"):
        return "genbank"
    if suffix in (".fna", ".fa", ".fasta", ".ffn"):
        return "fasta"
    raise GenomeParseError(
        f"Cannot tell from the name '{path.name}' whether this is a GenBank "
        f"file or a CDS FASTA. Say which it is."
    )


def compute_codon_table(
    path: Path | str,
    *,
    key: str,
    name: str,
    genetic_code: int = DEFAULT_GENETIC_CODE,
    genome_format: str | None = None,
    taxid: int | None = None,
    aliases: tuple[str, ...] | list[str] = (),
    source: str = "",
    source_uri: str = "",
    source_file: str | None = None,
    on_progress: Callable[[int, int | None], None] | None = None,
    generated_at: str | None = None,
    include_sha256: bool = True,
) -> ComputeResult:
    """Count the coding sequences in *path* and return a kuma codon document.

    ``genetic_code`` is the caller's and is written out unchanged; see the
    module docstring for why it is never inferred or corrected.

    ``source_sha256`` hashes the file on disk, not the response that delivered
    it. An NCBI datasets download is a ZIP assembled per request, so hashing
    the response would make the same accession mismatch itself on a second
    download.
    """
    path = Path(path)
    genetic_code = _require_supported_code(genetic_code)
    fmt = _format(path, genome_format)
    if not path.is_file():
        raise GenomeParseError(f"No such file: {path}")

    if fmt == "fasta":
        total = _count_fasta_records(path)
        records = iter_cds_fasta(path)
    else:
        total = None
        records = iter_cds_genbank(path)

    tally = tally_codons(
        records, genetic_code=genetic_code, on_progress=on_progress, total=total
    )

    counts_block: dict[str, list[list[Any]]] = {}
    codons_block: dict[str, list[list[Any]]] = {}
    for aa in AMINO_ACID_ORDER:
        pairs = sorted(
            tally.counts[aa].items(), key=lambda kv: (-kv[1], kv[0])
        )
        group_total = sum(v for _, v in pairs)
        counts_block[aa] = [[codon, value] for codon, value in pairs]
        # Unrounded. A rounded fraction would sit further from the one its own
        # count implies than V27's tolerance allows in the tail of a large
        # genome, and N4 recomputes fractions from counts anyway, so rounding
        # here would only make the stored file disagree with the table kuma
        # loads from it.
        codons_block[aa] = [
            [codon, (value / group_total) if group_total else 0.0]
            for codon, value in pairs
        ]

    provenance: dict[str, Any] = {
        "method": "cds_count",
        "source_format": fmt,
        "source_file": source_file or path.name,
        "cds_total": tally.cds_total,
        "cds_counted": tally.cds_counted,
        "cds_excluded": {r: tally.excluded[r] for r in EXCLUSION_REASONS},
        "codon_count": tally.codon_count,
        "generated_by": "kuma kuro compute_codon_table",
        "generated_at": generated_at or datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
    }
    if source_uri:
        provenance["source_uri"] = source_uri
    if include_sha256:
        provenance["source_sha256"] = _file_sha256(path)

    document: Document = {
        "schema_version": SUPPORTED_SCHEMA_VERSION,
        "key": key,
        "name": name,
        "taxid": taxid,
        "genetic_code": genetic_code,
        "aliases": [str(a).strip().lower() for a in aliases if str(a).strip()],
        "source": source,
        "provenance": provenance,
        "counts": counts_block,
        "codons": codons_block,
    }

    warnings: list[str] = []
    if (tally.cds_counted < LOW_CDS_WARN_THRESHOLD
            or tally.codon_count < LOW_CODON_COUNT_WARN_THRESHOLD):
        warnings.append("V31")

    return ComputeResult(
        document=document,
        cds_total=tally.cds_total,
        cds_counted=tally.cds_counted,
        cds_excluded=dict(provenance["cds_excluded"]),
        codon_count=tally.codon_count,
        excluded_examples={k: list(v) for k, v in tally.examples.items()},
        warning_codes=tuple(warnings),
    )
