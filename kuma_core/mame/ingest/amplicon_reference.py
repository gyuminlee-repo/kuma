from __future__ import annotations

import gzip
import math
import re
from dataclasses import dataclass
from pathlib import Path

import openpyxl

from kuma_core.mame.ingest.barcode_tail import common_tail
from kuma_core.shared.atomic_write import atomic_write_text

_FORWARD_NAME = re.compile(r".+_f_\d+$", re.IGNORECASE)
_REVERSE_NAME = re.compile(r".+_r_\d+$", re.IGNORECASE)
_COMPLEMENT = str.maketrans("ACGTacgtNn", "TGCAtgcaNn")
_STOP_CODONS = frozenset({"TAA", "TAG", "TGA"})

#: Human-readable form of the primer naming rule the barcode workbook must use
#: for the amplicon span to be derivable. Kept next to the regexes above so the
#: rule and the message that quotes it cannot drift apart.
PRIMER_NAME_RULE = "<target>_f_<n> / <target>_r_<n>"

#: How many reads to look at when deciding whether the coverage gate is
#: reachable at all. A sampling budget, not a scientific threshold: the decision
#: below compares the LONGEST sampled read against the gate, so the sample only
#: has to be large enough to contain a full-length read. Nanopore FASTQ are not
#: length-sorted, so a few thousand reads from the front of the run is ample.
_READ_LENGTH_SAMPLE_SIZE = 2000


@dataclass(frozen=True, slots=True)
class AmpliconSpan:
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class AmpliconReferenceResolution:
    reference_fasta: Path
    extracted: bool
    span: AmpliconSpan | None
    original_length: int
    cds_start: int
    cds_end: int
    note: str


class AmpliconReferenceError(ValueError):
    def __init__(self, path: Path, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(f"{reason}: {path}")


def _reverse_complement(sequence: str) -> str:
    return sequence.translate(_COMPLEMENT)[::-1]


def _read_fasta(path: Path) -> str:
    sequence = "".join(
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith(">")
    ).upper()
    if not sequence:
        raise AmpliconReferenceError(path, "Reference FASTA contains no sequence")
    return sequence


def _barcode_sequences(path: Path) -> tuple[list[str], list[str]]:
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        sheet = workbook.active
        if sheet is None:
            raise AmpliconReferenceError(path, "Barcode workbook has no active sheet")
        forward: list[str] = []
        reverse: list[str] = []
        for row in sheet.iter_rows(values_only=True):
            if len(row) < 2 or row[0] is None or row[1] is None:
                continue
            name = str(row[0]).strip()
            sequence = str(row[1]).strip().upper()
            if _FORWARD_NAME.fullmatch(name):
                forward.append(sequence)
            elif _REVERSE_NAME.fullmatch(name):
                reverse.append(sequence)
        return forward, reverse
    finally:
        workbook.close()


#: Why ``_unique_span`` returned ``None``. Distinct from "not unique" (found
#: more than once) because the two point an operator in opposite directions:
#: "not found" is normal and expected for a bare-CDS reference (the primer
#: tail sits in vector backbone outside the CDS, see ``_span_reason``'s
#: docstring), while "not unique" or "out of order" means the reference
#: itself is ambiguous or malformed. Collapsing all three into one message
#: previously sent operators hunting for duplicate primer sites when the
#: reference simply did not contain the tail at all (2026-08 incident).
class _SpanReason:
    NOT_FOUND = "not_found"
    NOT_UNIQUE = "not_unique"
    OUT_OF_ORDER = "out_of_order"


def _span_reason(sequence: str, forward_tail: str, reverse_tail: str) -> str | None:
    """Classify why a span could not be derived; ``None`` when it can be."""
    reverse_site = _reverse_complement(reverse_tail)
    forward_start = sequence.find(forward_tail)
    reverse_start = sequence.find(reverse_site)
    if forward_start < 0 or reverse_start < 0:
        return _SpanReason.NOT_FOUND
    if sequence.find(forward_tail, forward_start + 1) >= 0:
        return _SpanReason.NOT_UNIQUE
    if sequence.find(reverse_site, reverse_start + 1) >= 0:
        return _SpanReason.NOT_UNIQUE
    end = reverse_start + len(reverse_site)
    if forward_start >= end:
        return _SpanReason.OUT_OF_ORDER
    return None


def _unique_span(sequence: str, forward_tail: str, reverse_tail: str) -> AmpliconSpan | None:
    reverse_site = _reverse_complement(reverse_tail)
    forward_start = sequence.find(forward_tail)
    reverse_start = sequence.find(reverse_site)
    if forward_start < 0 or reverse_start < 0:
        return None
    if sequence.find(forward_tail, forward_start + 1) >= 0:
        return None
    if sequence.find(reverse_site, reverse_start + 1) >= 0:
        return None
    end = reverse_start + len(reverse_site)
    if forward_start >= end:
        return None
    return AmpliconSpan(start=forward_start, end=end)


def _longest_forward_orf(sequence: str) -> tuple[int, int] | None:
    candidates: list[tuple[int, int]] = []
    for start in range(len(sequence) - 2):
        if sequence[start:start + 3] != "ATG":
            continue
        for end in range(start + 3, len(sequence) - 2, 3):
            if sequence[end:end + 3] in _STOP_CODONS:
                candidates.append((start, end + 3))
                break
    if not candidates:
        return None
    return max(candidates, key=lambda bounds: (bounds[1] - bounds[0], -bounds[0]))


def _fasta_text(header: str, sequence: str) -> str:
    lines = [f">{header}"]
    lines.extend(sequence[index:index + 80] for index in range(0, len(sequence), 80))
    return "\n".join(lines) + "\n"


def resolve_amplicon_reference(
    reference_fasta: Path,
    barcodes_xlsx: Path,
    output_dir: Path,
) -> AmpliconReferenceResolution:
    reference_fasta = Path(reference_fasta)
    sequence = _read_fasta(reference_fasta)
    forward, reverse = _barcode_sequences(Path(barcodes_xlsx))
    # Same derivation the demux uses to find where a seed ends, so the span cut
    # here and the prefixes matched there cannot disagree about the file.
    forward_tail = common_tail(forward)
    reverse_tail = common_tail(reverse)
    if forward_tail is None or reverse_tail is None:
        return AmpliconReferenceResolution(
            reference_fasta, False, None, len(sequence), 0, 0,
            "Amplicon extraction skipped because shared primer tails could not be derived.",
        )
    span = _unique_span(sequence, forward_tail, reverse_tail)
    if span is None:
        reason = _span_reason(sequence, forward_tail, reverse_tail)
        if reason == _SpanReason.NOT_FOUND:
            note = (
                "Amplicon extraction skipped because the primer tail sequence was "
                "not found in the reference. This is expected when the reference is "
                "a bare CDS and the primer tail sits in vector backbone outside it; "
                "the whole reference is used unmodified in that case."
            )
        elif reason == _SpanReason.NOT_UNIQUE:
            note = (
                "Amplicon extraction skipped because a primer tail sequence "
                "matched more than one position in the reference."
            )
        else:
            note = (
                "Amplicon extraction skipped because the forward and reverse "
                "primer sites were found out of order in the reference."
            )
        return AmpliconReferenceResolution(
            reference_fasta, False, None, len(sequence), 0, 0, note,
        )
    amplicon = sequence[span.start:span.end]
    coding_bounds = _longest_forward_orf(amplicon)
    cds_start, cds_end = coding_bounds if coding_bounds is not None else (0, 0)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    extracted_path = output_dir / f"{reference_fasta.stem}.amplicon.fa"
    atomic_write_text(
        extracted_path,
        _fasta_text(
            f"{reference_fasta.stem}_amplicon_{span.start + 1}_{span.end}",
            amplicon,
        ),
    )
    return AmpliconReferenceResolution(
        extracted_path,
        True,
        span,
        len(sequence),
        cds_start,
        cds_end,
        f"Amplicon extracted from reference positions {span.start + 1}-{span.end} ({len(amplicon)} bp).",
    )


@dataclass(frozen=True, slots=True)
class CoverageReachability:
    """Whether ANY read in a run can clear the demux coverage gate.

    The demux keeps a read only when its alignment spans at least
    ``coverage_fraction`` of the reference (see ``align_reads_multi``).  An
    alignment cannot report a reference span longer than the read that produced
    it plus its deletions, so a run whose longest read is shorter than
    ``required_span`` cannot place a single read in a well.  That is the
    silent-failure shape this guards: a whole-plasmid reference (e.g. 6,494 bp)
    against amplicon reads (e.g. 1.7 kb) yields 0 assigned reads, 0 wells, and
    an empty consensus FASTA while the run still reports success.

    The test deliberately uses the LONGEST sampled read, so it only fires when
    the gate is unreachable for every read observed, never merely hard to reach.
    """

    reference_length: int
    coverage_fraction: float
    required_span: int
    sampled_reads: int
    longest_read_length: int

    @property
    def reachable(self) -> bool:
        # No reads sampled: nothing is known, so do not block the run.
        if self.sampled_reads == 0:
            return True
        return self.longest_read_length >= self.required_span


def _iter_run_fastq(run_dir: Path) -> list[Path]:
    fastq_pass = Path(run_dir) / "fastq_pass"
    root = fastq_pass if fastq_pass.is_dir() else Path(run_dir)
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and (path.name.endswith(".fastq") or path.name.endswith(".fastq.gz"))
    )


def _sample_read_lengths(run_dir: Path, sample_size: int) -> tuple[int, int]:
    """Return ``(n_sampled, longest_length)`` over the first reads of a run."""
    sampled = 0
    longest = 0
    for path in _iter_run_fastq(run_dir):
        opener = gzip.open if path.name.endswith(".gz") else open
        try:
            with opener(path, "rt") as handle:  # type: ignore[operator]
                while sampled < sample_size:
                    header = handle.readline()
                    if not header:
                        break
                    sequence = handle.readline().strip()
                    handle.readline()
                    handle.readline()
                    if not sequence:
                        continue
                    sampled += 1
                    longest = max(longest, len(sequence))
        except OSError:
            # An unreadable/truncated FASTQ is the pipeline's problem to report,
            # not this pre-flight check's; fall through with what was sampled.
            continue
        if sampled >= sample_size:
            break
    return sampled, longest


def check_coverage_reachable(
    reference_fasta: Path,
    run_dir: Path,
    coverage_fraction: float,
    sample_size: int = _READ_LENGTH_SAMPLE_SIZE,
) -> CoverageReachability:
    """Measure the run reads against the coverage gate the reference implies."""
    reference_length = len(_read_fasta(Path(reference_fasta)))
    required_span = math.ceil(coverage_fraction * reference_length)
    sampled, longest = _sample_read_lengths(Path(run_dir), sample_size)
    return CoverageReachability(
        reference_length=reference_length,
        coverage_fraction=coverage_fraction,
        required_span=required_span,
        sampled_reads=sampled,
        longest_read_length=longest,
    )


def unreachable_coverage_message(
    reachability: CoverageReachability,
    resolution: AmpliconReferenceResolution,
    barcodes_xlsx: Path,
    reference_fasta: Path,
) -> str:
    """Operator-facing explanation of an amplicon extraction that must not run."""
    return (
        "Amplicon reference could not be derived from the custom barcodes file, "
        "and the reference as given cannot pass the coverage filter.\n"
        f"  barcodes file: {Path(barcodes_xlsx)}\n"
        f"  reason: {resolution.note}\n"
        f"  expected primer names: {PRIMER_NAME_RULE} "
        "(e.g. ispS_f_1, ispS_r_1); rows whose names do not match are ignored, "
        "so a plate map without primer sequences yields no amplicon span.\n"
        f"  reference: {Path(reference_fasta)} "
        f"({reachability.reference_length} bp)\n"
        f"  coverage_fraction: {reachability.coverage_fraction} "
        f"-> every read must align over at least {reachability.required_span} bp\n"
        f"  longest of {reachability.sampled_reads} sampled reads: "
        f"{reachability.longest_read_length} bp\n"
        "Every read would be dropped at the coverage gate, producing 0 assigned "
        "reads, 0 wells and an empty consensus FASTA. Supply a barcodes workbook "
        "whose primer rows follow the naming rule above, or pass the amplicon "
        "reference itself instead of the whole construct."
    )


__all__ = [
    "PRIMER_NAME_RULE",
    "AmpliconReferenceError",
    "AmpliconReferenceResolution",
    "AmpliconSpan",
    "CoverageReachability",
    "check_coverage_reachable",
    "resolve_amplicon_reference",
    "unreachable_coverage_message",
]
