from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import openpyxl

from kuma_core.shared.atomic_write import atomic_write_text

_FORWARD_NAME = re.compile(r".+_f_\d+$", re.IGNORECASE)
_REVERSE_NAME = re.compile(r".+_r_\d+$", re.IGNORECASE)
_COMPLEMENT = str.maketrans("ACGTacgtNn", "TGCAtgcaNn")
_MIN_TAIL_LENGTH = 12
_STOP_CODONS = frozenset({"TAA", "TAG", "TGA"})


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


def _common_tail(sequences: list[str]) -> str | None:
    if len(sequences) < 2:
        return None
    reversed_sequences = [sequence[::-1] for sequence in sequences]
    length = 0
    for bases in zip(*reversed_sequences, strict=False):
        if len(set(bases)) != 1:
            break
        length += 1
    if length < _MIN_TAIL_LENGTH or any(len(sequence) <= length for sequence in sequences):
        return None
    return sequences[0][-length:]


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
    forward_tail = _common_tail(forward)
    reverse_tail = _common_tail(reverse)
    if forward_tail is None or reverse_tail is None:
        return AmpliconReferenceResolution(
            reference_fasta, False, None, len(sequence), 0, 0,
            "Amplicon extraction skipped because shared primer tails could not be derived.",
        )
    span = _unique_span(sequence, forward_tail, reverse_tail)
    if span is None:
        return AmpliconReferenceResolution(
            reference_fasta, False, None, len(sequence), 0, 0,
            "Amplicon extraction skipped because primer boundaries were not unique in the reference.",
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


__all__ = [
    "AmpliconReferenceError",
    "AmpliconReferenceResolution",
    "AmpliconSpan",
    "resolve_amplicon_reference",
]
