"""sort_barcode — Combinatorial barcode sorter for 96-well plates.

Takes a MinKNOW run directory (containing native-barcode subdirs under
``fastq_pass/``) and a combinatorial barcode xlsx (12 forward × 8 reverse
= 96 well identities) and writes per-well FASTA files under a
``sort_barcode{NN}/`` directory for each native-barcode subdir.

Matching strategy
-----------------
1. Read 5' prefix → best match among 12 fwd barcodes (Hamming distance).
2. Read 3' suffix window (last ~80 bp) → best match among 8 rev barcode
   RC sequences (Hamming distance).
3. Both matches must pass ``ceil(len * error_tolerance)`` threshold; ties
   in either axis → unassigned.
4. Well assignment: well_id = ``ROW_LETTER[rev_idx-1] + f"{fwd_idx:02d}"``
   where fwd_idx ∈ 1..12 (column) and rev_idx ∈ 1..8 (row).

Rev barcode RC note
-------------------
The read is on the forward strand: 5'-[fwd][insert][rc(rev)]-3'.
Therefore rev sequences are RC'd before matching the 3' read end.
Sequences are used in full (not split into unique segments) — only the
overall Hamming distance determines a match.

cutadapt note
-------------
``use_cutadapt=True`` is accepted for API compatibility but the
combinatorial two-axis matching is always performed in pure Python.
cutadapt does not natively support paired (fwd, rev) demux for 96-well
combinatorial layouts. Parameter is reserved for future extension.

Output
------
``{output_dir}/sort_barcode{NN}/{well_id}.fasta``
e.g. ``{output_dir}/sort_barcode06/A01.fasta``
FASTA header: ``>{read_id}``  (original ONT UUID preserved per spec).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Re-use private helpers from demux.py (cross-layer dependency documented in
# CLAUDE.md cross-layer table).
# ---------------------------------------------------------------------------
from kuma_core.mame.ingest.demux import (
    _hamming_prefix,
    _iter_fastq_records,
    _rc,
    detect_native_barcode_dirs,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ROW_LETTERS = list("ABCDEFGH")   # rows 1–8 → A–H
_N_COLS = 12
_N_ROWS = 8

_NB_DIR_PATTERN = re.compile(r"^(?:barcode|NB)(\d{1,3})$", re.IGNORECASE)

_FWD_PREFIX = "isps_f_"
_REV_PREFIX = "isps_r_"

# Suffix search window: last N bases of the read (Nanopore 3' end is noisy).
_REV_SEARCH_TAIL_BP = 80

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class SortBarcodeResult:
    output_dir: Path
    nb_dirs_processed: list[str]
    n_total_reads: int
    n_total_assigned: int
    n_total_unassigned: int
    per_nb_per_well_counts: dict[str, dict[str, int]] = field(default_factory=dict)
    skipped_nb_dirs: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# NB dir → sort_barcode name
# ---------------------------------------------------------------------------


def _nb_to_sort_barcode_name(nb_basename: str) -> str:
    """Map a native-barcode dir name to a sort_barcode output dir name.

    Examples
    --------
    ``barcode06``  →  ``sort_barcode06``
    ``NB06``       →  ``sort_barcode06``
    ``barcode100`` →  ``sort_barcode100``

    Raises
    ------
    ValueError
        If ``nb_basename`` does not match the expected pattern.
    """
    m = _NB_DIR_PATTERN.match(nb_basename)
    if m is None:
        raise ValueError(
            f"Cannot convert {nb_basename!r} to sort_barcode name: "
            "expected 'barcodeN' or 'NBN' (1–3 digit suffix)"
        )
    n = int(m.group(1))
    # 2-digit zero-pad for n < 100; 3-digit (no pad needed) for n >= 100.
    padded = f"{n:02d}" if n < 100 else str(n)
    return f"sort_barcode{padded}"


# ---------------------------------------------------------------------------
# Barcode xlsx parser
# ---------------------------------------------------------------------------


def parse_combinatorial_barcodes(path: Path) -> dict[str, tuple[str, str]]:
    """Parse ``isps_f_*`` / ``isps_r_*`` barcodes from xlsx and expand to 96 wells.

    File format (Sheet1)
    --------------------
    Column A: barcode name  (e.g. ``isps_f_1``, ``isps_r_3``)
    Column B: sequence (ACGT, any length ≥ 5)

    Expansion rule
    --------------
    - ``isps_f_N`` (N=1..12): forward barcode, used for column index.
    - ``isps_r_N`` (N=1..8):  reverse barcode, used for row index.
    - ``well_id = f"{ROW_LETTER[r-1]}{c:02d}"`` where r = rev index, c = fwd index.
    - Example: fwd=1, rev=1 → A01; fwd=12, rev=8 → H12.

    Returns
    -------
    ``dict[str, tuple[str, str]]``: {well_id: (fwd_seq, rev_seq)} for all 96 wells.

    Raises
    ------
    FileNotFoundError
        If ``path`` does not exist.
    ValueError
        If not all 12 fwd or not all 8 rev barcodes are present, or if any
        barcode name prefix is unrecognised.
    """
    if not path.exists():
        raise FileNotFoundError(f"custom_barcode_xlsx not found: {path}")

    import openpyxl  # local import: keeps cold-start fast

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        ws = wb.worksheets[0]
        fwd_map: dict[int, str] = {}   # {N: sequence}
        rev_map: dict[int, str] = {}   # {N: sequence}

        for row in ws.iter_rows(values_only=True):
            if not row or row[0] is None:
                continue
            name_raw = str(row[0]).strip()
            seq_raw = str(row[1]).strip().upper() if len(row) > 1 and row[1] is not None else ""
            if not seq_raw or len(seq_raw) < 5:
                continue

            if name_raw.startswith(_FWD_PREFIX):
                try:
                    n = int(name_raw[len(_FWD_PREFIX):])
                except ValueError:
                    raise ValueError(
                        f"Cannot parse fwd barcode index from {name_raw!r}. "
                        f"Expected format: {_FWD_PREFIX}<integer>"
                    )
                fwd_map[n] = seq_raw

            elif name_raw.startswith(_REV_PREFIX):
                try:
                    n = int(name_raw[len(_REV_PREFIX):])
                except ValueError:
                    raise ValueError(
                        f"Cannot parse rev barcode index from {name_raw!r}. "
                        f"Expected format: {_REV_PREFIX}<integer>"
                    )
                rev_map[n] = seq_raw

            else:
                # Rows that do not match either prefix are silently skipped
                # (header rows, comments, blank names).
                continue
    finally:
        wb.close()

    # Validate completeness.
    missing_fwd = [i for i in range(1, _N_COLS + 1) if i not in fwd_map]
    if missing_fwd:
        raise ValueError(
            f"Missing forward barcodes (expected {_FWD_PREFIX}1 … {_FWD_PREFIX}{_N_COLS}): "
            f"indices {missing_fwd}"
        )
    missing_rev = [i for i in range(1, _N_ROWS + 1) if i not in rev_map]
    if missing_rev:
        raise ValueError(
            f"Missing reverse barcodes (expected {_REV_PREFIX}1 … {_REV_PREFIX}{_N_ROWS}): "
            f"indices {missing_rev}"
        )

    # Build 96-well map.
    well_map: dict[str, tuple[str, str]] = {}
    for r in range(1, _N_ROWS + 1):       # rev idx → row letter
        for c in range(1, _N_COLS + 1):   # fwd idx → column number
            well_id = f"{_ROW_LETTERS[r - 1]}{c:02d}"
            well_map[well_id] = (fwd_map[c], rev_map[r])

    return well_map


# ---------------------------------------------------------------------------
# Hamming suffix window helper
# ---------------------------------------------------------------------------


def _hamming_suffix_window(
    read_seq: str,
    barcode: str,
    tail_bp: int = _REV_SEARCH_TAIL_BP,
) -> tuple[int, int]:
    """Find the best Hamming match for ``barcode`` in the last ``tail_bp`` bases.

    Scans right-to-left (prefers the 3'-most occurrence) to minimise false
    positives caused by partial homology in the amplicon body.

    Returns
    -------
    ``(best_distance, match_start)``
        ``best_distance`` = ``len(barcode) + 1`` if no window fits.
        ``match_start`` = position in ``read_seq`` where the best hit begins.
    """
    bc_len = len(barcode)
    if len(read_seq) < bc_len:
        return bc_len + 1, -1

    tail_start = max(0, len(read_seq) - tail_bp)
    tail = read_seq[tail_start:]

    best_dist = bc_len + 1
    best_abs_pos = -1

    for i in range(len(tail) - bc_len, -1, -1):
        mismatches = 0
        for a, b in zip(barcode, tail[i: i + bc_len]):
            if a != b:
                mismatches += 1
            if mismatches >= best_dist:
                break
        if mismatches < best_dist:
            best_dist = mismatches
            best_abs_pos = tail_start + i

    return best_dist, best_abs_pos


# ---------------------------------------------------------------------------
# Single-NB sort
# ---------------------------------------------------------------------------


def _sort_one_nb(
    nb_dir: Path,
    output_nb_dir: Path,
    error_tolerance: float,
    fwd_seqs: list[tuple[int, str]],       # [(c_idx, fwd_seq)]  c_idx 1-based
    rev_rc_seqs: list[tuple[int, str]],    # [(r_idx, rev_rc)]   r_idx 1-based
) -> tuple[dict[str, int], int]:
    """Demux a single NB directory into per-well FASTA files.

    Parameters
    ----------
    fwd_seqs:
        Pre-built list of (column_index, fwd_sequence) pairs.
    rev_rc_seqs:
        Pre-built list of (row_index, RC_of_rev_sequence) pairs.

    Returns
    -------
    ``(per_well_counts, n_total_reads)``:
        per_well_counts — dict mapping well_id to assigned read count.
        n_total_reads   — total reads seen (assigned + unassigned).
    """
    output_nb_dir.mkdir(parents=True, exist_ok=True)

    # Precompute max-mismatches per barcode.
    fwd_max_mm: dict[int, int] = {
        c: math.ceil(len(seq) * error_tolerance) for c, seq in fwd_seqs
    }
    rev_max_mm: dict[int, int] = {
        r: math.ceil(len(seq) * error_tolerance) for r, seq in rev_rc_seqs
    }

    # Collect FASTQ files.
    fastq_files: list[Path] = sorted(
        list(nb_dir.rglob("*.fastq")) + list(nb_dir.rglob("*.fastq.gz"))
    )
    if not fastq_files:
        raise FileNotFoundError(
            f"No FASTQ files found in {nb_dir}. Expected *.fastq or *.fastq.gz."
        )

    per_well_counts: dict[str, int] = {}
    n_nb_reads = 0
    writers: dict[str, object] = {}  # lazy-open file handles

    try:
        for fastq_path in fastq_files:
            for read_id, seq in _iter_fastq_records(fastq_path):
                n_nb_reads += 1
                # ── Forward barcode match (5' prefix) ────────────────────
                best_c: int | None = None
                best_fwd_dist = 999

                for c, fwd_seq in fwd_seqs:
                    dist = _hamming_prefix(seq, fwd_seq)
                    if dist < best_fwd_dist:
                        best_fwd_dist = dist
                        best_c = c
                    elif dist == best_fwd_dist:
                        best_c = None  # tie → ambiguous

                if best_c is None or best_fwd_dist > fwd_max_mm[best_c]:
                    continue  # unassigned

                # ── Reverse barcode RC match (3' suffix window) ──────────
                best_r: int | None = None
                best_rev_dist = 999

                for r, rev_rc in rev_rc_seqs:
                    dist, _ = _hamming_suffix_window(seq, rev_rc)
                    if dist < best_rev_dist:
                        best_rev_dist = dist
                        best_r = r
                    elif dist == best_rev_dist:
                        best_r = None  # tie → ambiguous

                if best_r is None or best_rev_dist > rev_max_mm[best_r]:
                    continue  # unassigned

                # ── Well assignment ──────────────────────────────────────
                well_id = f"{_ROW_LETTERS[best_r - 1]}{best_c:02d}"

                # Lazy-open writer.
                if well_id not in writers:
                    fasta_path = output_nb_dir / f"{well_id}.fasta"
                    writers[well_id] = open(  # noqa: WPS515
                        fasta_path, "w", encoding="utf-8"
                    )

                fh = writers[well_id]
                fh.write(f">{read_id}\n{seq}\n")  # type: ignore[union-attr]

                per_well_counts[well_id] = per_well_counts.get(well_id, 0) + 1

    finally:
        for fh in writers.values():
            fh.close()  # type: ignore[union-attr]

    return per_well_counts, n_nb_reads


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def sort_barcode_run(
    minknow_run_dir: Path,
    custom_barcode_xlsx: Path,
    output_dir: Path,
    *,
    nb_override: list[str] | None = None,
    error_tolerance: float = 0.1,
    use_cutadapt: bool = True,  # reserved; pure-Python only for combinatorial
) -> SortBarcodeResult:
    """Sort reads from a MinKNOW run into per-well FASTA files.

    Parameters
    ----------
    minknow_run_dir:
        Root of a MinKNOW run (must contain ``fastq_pass/`` with native-barcode
        subdirs, e.g. ``barcode06/`` or ``NB06/``).
    custom_barcode_xlsx:
        Path to a ``barcodes sequence.xlsx`` with Sheet1 col A = name, col B =
        sequence.  Expects 12 ``isps_f_*`` and 8 ``isps_r_*`` rows.
    output_dir:
        Destination root; per-NB subdirs (``sort_barcode{NN}/``) are created
        automatically.
    nb_override:
        If provided, process only these native-barcode dir basenames (e.g.
        ``["barcode06", "barcode07"]``).  Each must exist under
        ``fastq_pass/`` or as an absolute path that is a subdirectory of
        ``fastq_pass/``.
    error_tolerance:
        Per-base mismatch rate for Hamming matching [0.0, 0.5].
    use_cutadapt:
        Reserved for API compatibility; combinatorial matching is always
        performed in pure Python.  Reserved for future cutadapt extension.

    Returns
    -------
    SortBarcodeResult

    Raises
    ------
    FileNotFoundError
        minknow_run_dir / fastq_pass / custom_barcode_xlsx missing, or any
        nb_override entry not found.
    ValueError
        No NB dirs detected, error_tolerance out of range, xlsx incomplete,
        path traversal detected.
    """
    _ = use_cutadapt  # reserved; combinatorial matching is always pure-Python
    # ── Input validation ──────────────────────────────────────────────────
    # Check for ".." BEFORE resolve() — resolve() normalises ".." away,
    # making the check a dead-code no-op if done afterwards.
    if ".." in minknow_run_dir.parts:
        raise ValueError(f"Path traversal not allowed in minknow_run_dir: {minknow_run_dir}")
    minknow_run_dir = minknow_run_dir.resolve()
    if not minknow_run_dir.exists():
        raise FileNotFoundError(f"minknow_run_dir not found: {minknow_run_dir}")

    fastq_pass = minknow_run_dir / "fastq_pass"
    if not fastq_pass.exists():
        raise FileNotFoundError(f"fastq_pass/ not found: {fastq_pass}")

    if ".." in custom_barcode_xlsx.parts:
        raise ValueError(
            f"Path traversal not allowed in custom_barcode_xlsx: {custom_barcode_xlsx}"
        )
    custom_barcode_xlsx = custom_barcode_xlsx.resolve()
    if not custom_barcode_xlsx.exists():
        raise FileNotFoundError(f"custom_barcode_xlsx not found: {custom_barcode_xlsx}")

    if not (0.0 <= error_tolerance <= 0.5):
        raise ValueError(
            f"error_tolerance must be in [0.0, 0.5], got {error_tolerance!r}"
        )

    if ".." in output_dir.parts:
        raise ValueError(f"Path traversal not allowed in output_dir: {output_dir}")
    output_dir = output_dir.resolve()

    # ── Resolve NB directories ────────────────────────────────────────────
    if nb_override is not None:
        nb_dirs: list[Path] = []
        for name in nb_override:
            # WARNING fix: validate entry is a plain basename (no path separators,
            # no "..", no null bytes) before constructing a path from it.
            if (
                not name
                or "/" in name
                or "\\" in name
                or "\x00" in name
                or name in (".", "..")
            ):
                raise ValueError(
                    f"nb_override entry must be a plain directory name: {name!r}"
                )
            candidate = (fastq_pass / name).resolve()
            # Boundary check: candidate must remain inside fastq_pass.
            fastq_pass_resolved = fastq_pass.resolve()
            try:
                candidate.relative_to(fastq_pass_resolved)
            except ValueError:
                raise ValueError(
                    f"nb_override entry escapes fastq_pass boundary: {name!r}"
                )
            if not candidate.is_dir():
                raise FileNotFoundError(
                    f"nb_override entry not found: {candidate}"
                )
            nb_dirs.append(candidate)
    else:
        nb_dirs = detect_native_barcode_dirs(fastq_pass)

    if not nb_dirs:
        raise ValueError(
            "No native barcode dirs detected in "
            f"{fastq_pass}. Expected subdirectories matching barcode*/NB*."
        )

    # ── Parse barcode xlsx ────────────────────────────────────────────────
    well_map = parse_combinatorial_barcodes(custom_barcode_xlsx)

    # Pre-build fwd / rev lists once (shared across all NB dirs).
    fwd_seqs: list[tuple[int, str]] = []
    rev_rc_seqs: list[tuple[int, str]] = []

    # Collect unique fwd/rev sequences from the well map.
    _seen_c: dict[int, str] = {}
    _seen_r: dict[int, str] = {}

    for r in range(1, _N_ROWS + 1):
        for c in range(1, _N_COLS + 1):
            well_id = f"{_ROW_LETTERS[r - 1]}{c:02d}"
            fwd_seq, rev_seq = well_map[well_id]
            if c not in _seen_c:
                _seen_c[c] = fwd_seq
            if r not in _seen_r:
                _seen_r[r] = rev_seq

    for c in range(1, _N_COLS + 1):
        fwd_seqs.append((c, _seen_c[c]))
    for r in range(1, _N_ROWS + 1):
        # RC the rev seq: reads are on the forward strand (5'-[fwd][ins][rc(rev)]-3').
        rev_rc_seqs.append((r, _rc(_seen_r[r])))

    # ── Process each NB directory ─────────────────────────────────────────
    nb_dirs_processed: list[str] = []
    skipped_nb_dirs: list[str] = []
    n_total_reads = 0
    n_total_assigned = 0
    per_nb_per_well: dict[str, dict[str, int]] = {}

    for nb_dir in nb_dirs:
        sb_name = _nb_to_sort_barcode_name(nb_dir.name)
        sb_out = output_dir / sb_name

        try:
            per_well, n_nb_reads = _sort_one_nb(
                nb_dir=nb_dir,
                output_nb_dir=sb_out,
                error_tolerance=error_tolerance,
                fwd_seqs=fwd_seqs,
                rev_rc_seqs=rev_rc_seqs,
            )
        except FileNotFoundError:
            # NB dir exists but has no FASTQ files — skip gracefully.
            skipped_nb_dirs.append(nb_dir.name)
            continue

        # n_nb_reads comes from the single demux pass — no second rglob needed.
        nb_assigned = sum(per_well.values())
        n_total_reads += n_nb_reads
        n_total_assigned += nb_assigned
        per_nb_per_well[nb_dir.name] = per_well
        nb_dirs_processed.append(nb_dir.name)

    n_total_unassigned = n_total_reads - n_total_assigned

    return SortBarcodeResult(
        output_dir=output_dir,
        nb_dirs_processed=nb_dirs_processed,
        n_total_reads=n_total_reads,
        n_total_assigned=n_total_assigned,
        n_total_unassigned=n_total_unassigned,
        per_nb_per_well_counts=per_nb_per_well,
        skipped_nb_dirs=skipped_nb_dirs,
    )


__all__ = [
    "SortBarcodeResult",
    "sort_barcode_run",
    "parse_combinatorial_barcodes",
    "_nb_to_sort_barcode_name",
    "_hamming_suffix_window",
]
