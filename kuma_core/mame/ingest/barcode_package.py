"""barcode_package -- Generate MAME input package from barcode seeds and a CDS FASTA.

This module produces two output files and a context JSON:
- ``barcodes_sequence.xlsx``    : 20-row combinatorial barcode table (12 fwd + 8 rev)
- ``{sanitized_gene_name}_amplicon.fa`` : single-entry FASTA for the target gene region
- ``mame_context.json``         : machine-readable pointer file (schema 2)

It used to write a third file, ``sample_map_template.xlsx``, a (sample, well)
sheet the operator confirmed by hand. That file stated the plate a second time,
so a campaign carried two answers to one question and analyze had to pick one.
The computed draft says the same thing from the variant list alone, so the
template is gone and schema 2 no longer points at one.

Typical call site::

    result = generate_mame_package(
        fasta_path=Path("seq/target.fa"),
        gene_start=400,
        gene_end=700,
        barcode_seeds_path=Path("design/barcode_seeds.xlsx"),
        output_dir=Path("project/design"),
        project_root=Path("project"),
        gene_name="target_gene",
        polymerase="Q5",
    )
"""

from __future__ import annotations

import datetime
import json
import warnings
from dataclasses import dataclass, field
from pathlib import Path

import primer3

from kuma_core.mame.ingest.polymerase import PolymeraseProfile, get_profile

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_N_FWD = 12
_N_REV = 8
_MIN_SEED_LEN = 5
_MAX_SEED_LEN = 30
_VALID_BASES = frozenset("ATGC")

# Prefix convention for barcode_seeds.xlsx rows
_FWD_PREFIX = "fwd_"
_REV_PREFIX = "rev_"

# Suffix convention for the output barcodes_sequence.xlsx (MAME side).
# Row names are derived as ``{sanitized_gene_name}{_FWD_SUFFIX}{i}`` /
# ``{sanitized_gene_name}{_REV_SUFFIX}{i}``. The matching reader in
# ``sort_barcode.parse_combinatorial_barcodes`` is gene-agnostic — it parses
# any prefix that ends with ``_f_<int>`` / ``_r_<int>``.
_FWD_SUFFIX = "_f_"
_REV_SUFFIX = "_r_"


def _sanitize_gene_prefix(gene_name: str) -> str:
    """Return a filesystem- and excel-safe prefix derived from ``gene_name``.

    - Lower-cases.
    - Replaces any run of non-alphanumeric chars with a single ``_``.
    - Strips leading/trailing ``_``.
    - Strips embedded ``_f_`` / ``_r_`` substrings so the suffix on row names
      stays unambiguous for the reader's regex parser.

    Raises
    ------
    ValueError
        If the sanitized result is empty (pathological input such as ``""``
        or all-punctuation).
    """
    import re as _re
    s = _re.sub(r"[^a-z0-9]+", "_", gene_name.lower()).strip("_")
    # Strip any embedded _f_ / _r_ runs so the suffix on row names remains
    # the only such marker in the final string.
    s = s.replace("_f_", "_").replace("_r_", "_").strip("_")
    if not s:
        raise ValueError(
            f"gene_name {gene_name!r} sanitizes to an empty prefix; "
            "provide a gene name containing at least one alphanumeric character."
        )
    return s


# ---------------------------------------------------------------------------
# Reverse complement (local to avoid cross-layer coupling with kuro.overlap)
# ---------------------------------------------------------------------------

def _reverse_complement(seq: str) -> str:
    """Return the reverse complement of a DNA sequence (case-preserving)."""
    table = str.maketrans("ACGTacgt", "TGCAtgca")
    return seq.translate(table)[::-1]


# ---------------------------------------------------------------------------
# Tm calculation
# ---------------------------------------------------------------------------

def _calc_tm(seq: str, profile: PolymeraseProfile) -> float:
    """Calculate Tm using the given polymerase salt profile.

    Uses primer3.calc_tm with SantaLucia 1998 nearest-neighbour parameters.
    ``seq`` is converted to uppercase before passing to primer3.
    """
    return primer3.calc_tm(
        seq.upper(),
        mv_conc=profile.mv_conc,
        dv_conc=profile.dv_conc,
        dntp_conc=profile.dntp_conc,
        dna_conc=profile.dna_conc,
        tm_method=profile.tm_method,
        salt_corrections_method=profile.salt_corrections_method,
    )


# ---------------------------------------------------------------------------
# Sequence parser (FASTA / GenBank / SnapGene)
# ---------------------------------------------------------------------------

_GENBANK_SUFFIXES = {".gb", ".gbk", ".gbff"}
_SNAPGENE_SUFFIXES = {".dna"}
_FASTA_SUFFIXES = {".fa", ".fasta", ".fna"}


def _parse_first_cds_sequence(seq_path: Path) -> tuple[str, str]:
    """Return (sequence, topology) for the first record in a FASTA, GenBank, or
    SnapGene file.

    GenBank/SnapGene are routed to Biopython via kuro's ``load_sequence`` for the
    sequence, and via kuro's ``detect_topology`` for the topology annotation
    ("circular" or "linear"). FASTA uses a lightweight inline parser to keep
    the dependency surface small and has no topology annotation, so it is
    always reported as "linear".

    Raises
    ------
    FileNotFoundError
        If ``seq_path`` does not exist.
    ValueError
        If no record is found or the resulting sequence is empty.
    """
    if not seq_path.exists():
        raise FileNotFoundError(f"Sequence file not found: {seq_path}")

    suffix = seq_path.suffix.lower()

    if suffix in _GENBANK_SUFFIXES or suffix in _SNAPGENE_SUFFIXES:
        from kuma_core.kuro.sdm_engine import detect_topology, load_sequence

        _header, sequence, _genes = load_sequence(seq_path)
        if not sequence:
            raise ValueError(f"Empty sequence in: {seq_path}")
        topology = detect_topology(seq_path)
        return sequence.upper(), topology

    if suffix not in _FASTA_SUFFIXES:
        raise ValueError(
            f"Unsupported sequence file extension {suffix!r}; "
            "use .fa/.fasta/.fna, .gb/.gbk/.gbff, or .dna."
        )

    return _parse_first_fasta_sequence(seq_path), "linear"


def _parse_first_fasta_sequence(fasta_path: Path) -> str:
    """Return the sequence of the first record in a FASTA file.

    Issues a UserWarning when more than one record is present (first is used).

    Raises
    ------
    FileNotFoundError
        If ``fasta_path`` does not exist.
    ValueError
        If the file contains no valid FASTA record or the sequence is empty.
    """
    if not fasta_path.exists():
        raise FileNotFoundError(f"FASTA file not found: {fasta_path}")

    seq_parts: list[str] = []
    header_count = 0
    with fasta_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\r\n")
            if line.startswith(">"):
                header_count += 1
                if header_count > 1:
                    break   # stop reading after second header
            elif header_count == 1 and line:
                seq_parts.append(line.strip())

    if header_count == 0:
        raise ValueError(f"No FASTA record found in: {fasta_path}")
    if header_count > 1:
        warnings.warn(
            f"{fasta_path} contains {header_count} sequences; using the first one.",
            UserWarning,
            stacklevel=3,
        )

    seq = "".join(seq_parts)
    if not seq:
        raise ValueError(f"FASTA record in {fasta_path} has an empty sequence.")
    return seq


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def parse_barcode_seeds(path: Path) -> dict[str, str]:
    """Parse fwd/rev seed sequences from an xlsx file.

    File format (Sheet1):
        Column A: name  (``fwd_1`` .. ``fwd_12``, ``rev_1`` .. ``rev_8``)
        Column B: sequence (A/T/G/C, case-insensitive, 5-30 bp)

    Returns
    -------
    dict mapping ``"fwd_1"`` .. ``"fwd_12"`` and ``"rev_1"`` .. ``"rev_8"``
    to their uppercase seed sequences.

    Raises
    ------
    FileNotFoundError
        If ``path`` does not exist.
    ValueError
        If fwd count != 12, rev count != 8, any sequence contains non-ATGC
        characters, any sequence is outside the 5-30 bp range, or duplicate
        sequences are found among all 20 seeds.
    """
    if not path.exists():
        raise FileNotFoundError(f"barcode_seeds file not found: {path}")

    import openpyxl  # local import: keeps cold-start fast

    wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
    try:
        ws = wb.worksheets[0]
        fwd_map: dict[int, str] = {}
        rev_map: dict[int, str] = {}

        for row in ws.iter_rows(values_only=True):
            if not row or row[0] is None:
                continue
            name_raw = str(row[0]).strip().lower()
            seq_raw = str(row[1]).strip().upper() if len(row) > 1 and row[1] is not None else ""
            if not seq_raw:
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
            # rows that match neither prefix (header, comment) are silently skipped
    finally:
        wb.close()

    # Completeness check
    missing_fwd = [i for i in range(1, _N_FWD + 1) if i not in fwd_map]
    if missing_fwd:
        raise ValueError(
            f"Missing forward barcode seeds (expected fwd_1 .. fwd_{_N_FWD}): "
            f"indices {missing_fwd}"
        )
    missing_rev = [i for i in range(1, _N_REV + 1) if i not in rev_map]
    if missing_rev:
        raise ValueError(
            f"Missing reverse barcode seeds (expected rev_1 .. rev_{_N_REV}): "
            f"indices {missing_rev}"
        )

    # Per-seed validation (bases and length)
    all_seeds: dict[str, str] = {}
    for i in range(1, _N_FWD + 1):
        key = f"fwd_{i}"
        seq = fwd_map[i]
        _validate_seed_sequence(key, seq)
        all_seeds[key] = seq
    for i in range(1, _N_REV + 1):
        key = f"rev_{i}"
        seq = rev_map[i]
        _validate_seed_sequence(key, seq)
        all_seeds[key] = seq

    # Duplicate check across all 20 seeds
    seen_seqs: dict[str, str] = {}  # seq -> first key
    for key, seq in all_seeds.items():
        if seq in seen_seqs:
            raise ValueError(
                f"Duplicate seed sequence detected: {key!r} and "
                f"{seen_seqs[seq]!r} share the same sequence ({seq!r}). "
                "All 20 barcode seeds must be unique."
            )
        seen_seqs[seq] = key

    return all_seeds


def _validate_seed_sequence(key: str, seq: str) -> None:
    """Raise ValueError if seq contains non-ATGC chars or is out of length range."""
    if not (_MIN_SEED_LEN <= len(seq) <= _MAX_SEED_LEN):
        raise ValueError(
            f"Barcode seed {key!r} has length {len(seq)}, "
            f"expected {_MIN_SEED_LEN}-{_MAX_SEED_LEN} bp."
        )
    invalid = set(seq) - _VALID_BASES
    if invalid:
        raise ValueError(
            f"Barcode seed {key!r} contains non-ATGC characters: "
            f"{sorted(invalid)!r} (only A, T, G, C allowed)."
        )


def _circular_slice(seq: str, start: int, length: int, seq_len: int) -> str:
    """Return a length-character substring of seq starting at start, wrapping
    around the origin (position 0) if start is negative or start + length
    exceeds seq_len.

    Intended only for circular topology, where a primer binding site may
    physically span the origin of the template. start may be any integer
    (negative offsets count backwards from the end via Python's modulo).
    """
    return "".join(seq[(start + i) % seq_len] for i in range(length))


def design_flanking_primers(
    cds_sequence: str,
    gene_start: int,
    gene_end: int,
    profile: PolymeraseProfile,
    overhang_min: int = 20,
    overhang_max: int = 60,
    binding_min_len: int = 18,
    binding_max_len: int = 35,
    tm_min: float = 55.0,
    tm_max: float = 68.0,
    require_gc_clamp: bool = True,
    topology: str = "linear",
) -> tuple[str, str, list[str]]:
    """Design Tm-guided flanking primers flanking a gene region.

    What the window measures
    ------------------------
    The single configured axis is the **overhang**: how far the outer end of
    the amplicon reaches past the CDS boundary. For the forward primer the
    binding site is ``[pos, pos + length)`` and the overhang is
    ``gene_start - pos``. For the reverse primer the binding site is
    ``[start, end)`` and the overhang is ``end - gene_end``. Both must satisfy
    ``overhang_min <= overhang <= overhang_max``. This is the same quantity the
    downstream steps already measure, so ``trim_flank_bp`` and the terminal
    variant advisories speak of the same distance.

    The gap between primer and gene is **not** a parameter. It is fixed at
    ``>= 0``: a base a primer covers is read from the primer rather than from
    the template, so a primer reaching into the CDS would hide the very
    mutations this assay scores. The forward primer therefore ends no later
    than ``gene_start`` and the reverse binding site starts no earlier than
    ``gene_end``. Because ``overhang = gap + binding_length``, an
    ``overhang_min`` below ``binding_min_len`` describes a sub-range no primer
    can occupy; that is reported as a warning rather than refused, since larger
    overhangs in the same range remain reachable.

    Search order
    ------------
    Inner loop: binding length ascending from ``binding_min_len`` to
    ``binding_max_len``. First candidate satisfying both the Tm window and the
    GC-clamp (if requested) is returned immediately. If no candidate meets the
    criteria, the candidate whose Tm is closest to ``(tm_min + tm_max) / 2`` is
    returned instead and a warning is appended.

    The outer loop walks **outside-in on both strands**, from the largest
    reachable overhang towards ``overhang_min``. Forward iterates ``pos``
    ascending from ``gene_start - overhang_max``; reverse iterates ``end``
    descending from ``gene_end + overhang_max``, which is the same direction
    expressed in that strand's coordinates. The first accepted candidate
    therefore lands at the reachable cap on either side.

    That direction is the point of the default of 60, so do not turn either
    loop towards the gene without re-measuring. Landing at the cap leaves
    roughly ``60`` minus one binding length of template between the primer and
    the CDS on **both** sides, which keeps the 30 bp
    ``variants_near_reference_edge`` margin clear at both termini. Walking
    reverse inwards instead seated it near ``max(overhang_min,
    binding_min_len)``, about 22 bp at the defaults, which pulled the last few
    codons of the CDS inside that margin while the forward side was unaffected.
    Both directions are pinned by
    ``tests/mame/test_overhang_window.py::test_both_strands_search_outward``
    and its clamped counterpart.

    Parameters
    ----------
    cds_sequence:
        Full CDS nucleotide string (any case).
    gene_start:
        0-based inclusive start position of the gene within ``cds_sequence``.
    gene_end:
        0-based exclusive end position of the gene within ``cds_sequence``.
    profile:
        PolymeraseProfile supplying salt concentrations for Tm calculation.
    overhang_min:
        Minimum overhang (bp): how far past the gene boundary the outer end of
        the binding site must reach. Values below ``binding_min_len`` are
        unreachable and produce a warning.
    overhang_max:
        Maximum overhang (bp) that is searched.
    binding_min_len:
        Minimum primer binding length to try.
    binding_max_len:
        Maximum primer binding length to try.
    tm_min:
        Lower bound of the acceptable Tm window (deg C).
    tm_max:
        Upper bound of the acceptable Tm window (deg C).
    require_gc_clamp:
        If True, the 3' terminal base of every candidate must be G or C.
    topology:
        Either "linear" (default) or "circular". When "linear", an overhang
        that would reach outside ``cds_sequence`` is clamped to the sequence,
        and ValueError is raised only when the clamped reach is below
        ``max(overhang_min, binding_min_len)``. When "circular", the forward and
        reverse search windows are allowed to wrap around the sequence
        origin, since the corresponding template region physically exists on
        a circular molecule.

    Returns
    -------
    (fwd_flanking, rev_flanking, warnings) where both sequences are lowercase
    strings and warnings is a (possibly empty) list of human-readable messages.

    Raises
    ------
    ValueError
        If topology is not "linear" or "circular", if the clamped overhang
        reach under linear topology is below
        ``max(overhang_min, binding_min_len)``, if
        wrapping under circular topology would require reading past a full
        revolution of the sequence, or if ``gene_start >= gene_end``, or if
        parameter ranges are invalid.
    """
    seq_len = len(cds_sequence)

    if topology not in ("linear", "circular"):
        raise ValueError(
            f"topology must be \"linear\" or \"circular\", got {topology!r}."
        )

    if gene_start < 0:
        raise ValueError(f"gene_start must be >= 0, got {gene_start}.")
    if gene_end > seq_len:
        raise ValueError(
            f"gene_end ({gene_end}) exceeds sequence length ({seq_len})."
        )
    if gene_start >= gene_end:
        raise ValueError(
            f"gene_start ({gene_start}) must be < gene_end ({gene_end})."
        )
    if overhang_min < 0 or overhang_max < overhang_min:
        raise ValueError(
            f"overhang_min ({overhang_min}) must be >= 0 and "
            f"<= overhang_max ({overhang_max})."
        )
    if binding_min_len < 1 or binding_max_len < binding_min_len:
        raise ValueError(
            f"binding_min_len ({binding_min_len}) must be >= 1 and "
            f"<= binding_max_len ({binding_max_len})."
        )

    if topology == "circular" and (
        overhang_max > seq_len or binding_max_len > seq_len
    ):
        raise ValueError(
            f"Circular wrap overhang (overhang_max = {overhang_max}) or "
            f"binding_max_len ({binding_max_len}) exceeds the sequence length "
            f"(seq_len={seq_len}); wrapping would read the same base more than "
            "once. Reduce overhang_max/binding_max_len or use a longer template."
        )

    collected_warnings: list[str] = []

    # overhang = gap + binding_length and gap >= 0, so no primer can occupy an
    # overhang below binding_min_len. The sub-range is inert rather than fatal.
    if overhang_min < binding_min_len:
        collected_warnings.append(
            f"overhang_min ({overhang_min}) is below binding_min_len "
            f"({binding_min_len}); overhangs under {binding_min_len} bp cannot "
            f"hold a binding site, so the effective minimum is {binding_min_len}."
        )

    # The gap between primer and gene is a fixed invariant, not a parameter:
    # the forward primer ends no later than gene_start and the reverse binding
    # site starts no earlier than gene_end, so no scored base is read from a
    # primer. Only the overhang is configurable.
    overhang_floor = max(overhang_min, binding_min_len)
    fwd_overhang_cap = overhang_max
    rev_overhang_cap = overhang_max

    if topology == "linear":
        # A linear template has no bases before position 0 or after the last
        # one. Clamp the reach to what exists instead of refusing: what a
        # primer physically needs is one binding site, not the full
        # overhang_max.
        fwd_overhang_cap = min(overhang_max, gene_start)
        rev_overhang_cap = min(overhang_max, seq_len - gene_end)

    # Two different causes land here and the remedy differs, so name the one
    # that actually applies rather than always blaming the template.
    if fwd_overhang_cap < overhang_floor:
        cause = (
            "sequence is too short upstream of the gene"
            if fwd_overhang_cap < overhang_max
            else "raise overhang_max or lower binding_min_len"
        )
        raise ValueError(
            f"Forward primer overhang reaches at most {fwd_overhang_cap} bp, "
            f"which leaves {fwd_overhang_cap} bp, but "
            f"binding_min_len ({binding_min_len}) and overhang_min "
            f"({overhang_min}) require {overhang_floor} bp "
            f"(gene_start={gene_start}, overhang_max={overhang_max}); "
            f"{cause}."
        )
    if rev_overhang_cap < overhang_floor:
        cause = (
            "sequence is too short downstream of the gene"
            if rev_overhang_cap < overhang_max
            else "raise overhang_max or lower binding_min_len"
        )
        raise ValueError(
            f"Reverse primer overhang reaches at most {rev_overhang_cap} bp, "
            f"which leaves {rev_overhang_cap} bp, but "
            f"binding_min_len ({binding_min_len}) and overhang_min "
            f"({overhang_min}) require {overhang_floor} bp "
            f"(gene_end={gene_end}, seq_len={seq_len}, "
            f"overhang_max={overhang_max}); "
            f"{cause}."
        )

    # Both strands are walked outside-in: the first position tried is the one
    # with the largest reachable overhang and the last is the one at
    # overhang_min. `_first` and `_last` therefore name iteration order, not
    # coordinate order, and the reverse loop counts down because on that strand
    # the outermost coordinate is the largest one.
    #
    # Forward: the primer ends at gene_start at the latest, which caps its
    # length at the overhang itself.
    fwd_pos_first = gene_start - fwd_overhang_cap
    fwd_pos_last = gene_start - overhang_min  # inclusive

    # Reverse: the binding site starts at gene_end at the earliest, which
    # likewise caps its length at the overhang.
    rev_end_first = gene_end + rev_overhang_cap
    rev_end_last = gene_end + overhang_min  # inclusive

    tm_target = (tm_min + tm_max) / 2.0

    # --- Forward primer -------------------------------------------------------
    fwd_candidates: list[tuple[float, str]] = []  # (abs(Tm - target), seq)
    fwd_chosen: str | None = None

    for pos in range(fwd_pos_first, fwd_pos_last + 1):
        for length in range(binding_min_len, min(binding_max_len, gene_start - pos) + 1):
            if topology == "circular":
                candidate = _circular_slice(cds_sequence, pos, length, seq_len)
            else:
                candidate = cds_sequence[pos: pos + length]
                if len(candidate) < length:
                    break  # hit end of sequence
            tm = _calc_tm(candidate, profile)
            gc_ok = (not require_gc_clamp) or (candidate[-1].upper() in "GC")
            fwd_candidates.append((abs(tm - tm_target), candidate))
            if tm_min <= tm <= tm_max and gc_ok:
                fwd_chosen = candidate
                break
        if fwd_chosen is not None:
            break

    if fwd_chosen is None:
        fallback_candidates = (
            [item for item in fwd_candidates if item[1][-1].upper() in "GC"]
            if require_gc_clamp
            else fwd_candidates
        )
        if fallback_candidates:
            fallback_candidates.sort(key=lambda x: x[0])
            fwd_chosen = fallback_candidates[0][1]
            best_tm = _calc_tm(fwd_chosen, profile)
            collected_warnings.append(
                f"No forward primer candidate met Tm [{tm_min}, {tm_max}] "
                f"(require_gc_clamp={require_gc_clamp}). "
                f"Using closest candidate (Tm={best_tm:.1f} C): {fwd_chosen.upper()}"
            )
        elif require_gc_clamp:
            raise ValueError(
                "Forward primer search produced no candidate satisfying the required "
                "GC clamp. Relax require_gc_clamp or widen the search window."
            )
        else:
            raise ValueError(
                "Forward primer search produced no candidates. "
                f"Check overhang_min={overhang_min}, overhang_max={overhang_max}, "
                f"binding_min_len={binding_min_len}, binding_max_len={binding_max_len}."
            )

    # --- Reverse primer -------------------------------------------------------
    rev_candidates: list[tuple[float, str]] = []
    rev_chosen: str | None = None

    for end in range(rev_end_first, rev_end_last - 1, -1):
        for length in range(binding_min_len, min(binding_max_len, end - gene_end) + 1):
            start = end - length
            if topology == "circular":
                candidate_raw = _circular_slice(cds_sequence, start, length, seq_len)
            else:
                if start < 0:
                    break
                candidate_raw = cds_sequence[start:end]
                if len(candidate_raw) < length:
                    break
            candidate = _reverse_complement(candidate_raw)
            tm = _calc_tm(candidate, profile)
            gc_ok = (not require_gc_clamp) or (candidate[-1].upper() in "GC")
            rev_candidates.append((abs(tm - tm_target), candidate))
            if tm_min <= tm <= tm_max and gc_ok:
                rev_chosen = candidate
                break
        if rev_chosen is not None:
            break

    if rev_chosen is None:
        fallback_candidates = (
            [item for item in rev_candidates if item[1][-1].upper() in "GC"]
            if require_gc_clamp
            else rev_candidates
        )
        if fallback_candidates:
            fallback_candidates.sort(key=lambda x: x[0])
            rev_chosen = fallback_candidates[0][1]
            best_tm = _calc_tm(rev_chosen, profile)
            collected_warnings.append(
                f"No reverse primer candidate met Tm [{tm_min}, {tm_max}] "
                f"(require_gc_clamp={require_gc_clamp}). "
                f"Using closest candidate (Tm={best_tm:.1f} C): {rev_chosen.upper()}"
            )
        elif require_gc_clamp:
            raise ValueError(
                "Reverse primer search produced no candidate satisfying the required "
                "GC clamp. Relax require_gc_clamp or widen the search window."
            )
        else:
            raise ValueError(
                "Reverse primer search produced no candidates. "
                f"Check overhang_min={overhang_min}, overhang_max={overhang_max}, "
                f"binding_min_len={binding_min_len}, binding_max_len={binding_max_len}."
            )

    return fwd_chosen.lower(), rev_chosen.lower(), collected_warnings


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class MamePackageResult:
    """Paths produced by :func:`generate_mame_package`."""
    barcodes_xlsx: Path
    amplicon_fa: Path
    context_json: Path
    warnings: list[str] = field(default_factory=list)
    amplicon_length: int | None = None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def generate_mame_package(
    fasta_path: Path,
    gene_start: int,
    gene_end: int,
    barcode_seeds_path: Path,
    output_dir: Path,
    project_root: Path,
    gene_name: str,
    polymerase: str = "Q5",
    overhang_min: int = 20,
    overhang_max: int = 60,
    binding_min_len: int = 18,
    binding_max_len: int = 35,
    tm_min: float = 55.0,
    tm_max: float = 68.0,
    require_gc_clamp: bool = True,
    topology: str | None = None,
) -> MamePackageResult:
    """Generate the complete MAME input package for a sequencing run.

    Steps
    -----
    1. Read the first sequence from ``fasta_path`` (warn if multi-record).
    2. Call :func:`design_flanking_primers` to obtain fwd/rev flanking sequences.
    3. Call :func:`parse_barcode_seeds` to obtain 12 fwd + 8 rev seed sequences.
    4. Write ``barcodes_sequence.xlsx`` (20 data rows, 1 header row).
       Row format: name ``{sanitized_gene}_f_N`` / ``{sanitized_gene}_r_N``,
       sequence = SEED + flanking (all upper). The ``sanitized_gene`` prefix
       is derived from the ``gene_name`` parameter via
       :func:`_sanitize_gene_prefix`.
    5. Write ``{sanitized_gene_name}_amplicon.fa`` containing the target gene region.
    6. Write ``mame_context.json`` at ``project_root`` with schema 2.

    Parameters
    ----------
    fasta_path:
        Path to a FASTA file containing the full CDS sequence.
    gene_start:
        0-based inclusive start of the gene region within the CDS.
    gene_end:
        0-based exclusive end of the gene region within the CDS.
    barcode_seeds_path:
        Path to the barcode seeds xlsx (fwd_1..12, rev_1..8).
    output_dir:
        Destination for barcodes_sequence.xlsx, amplicon .fa, and template.
        Created automatically (``parents=True``) if it does not exist.
    project_root:
        Root of the KUMA project. ``mame_context.json`` is written here.
        All paths in the JSON are relative to this directory.
    gene_name:
        Required gene label derived from input annotation or explicit user entry.
        It is sanitized for barcode row names and the amplicon filename.
    polymerase:
        Name of the polymerase profile to use for Tm calculation.
        Must be one of the keys in ``POLYMERASE_PROFILES`` (default "Q5").
    overhang_min:
        Minimum overhang (bp): how far past the gene boundary the outer end of
        the primer binding site must reach.
    overhang_max:
        Maximum overhang (bp) searched.
    binding_min_len:
        Minimum primer binding length to try.
    binding_max_len:
        Maximum primer binding length to try.
    tm_min:
        Lower bound of the acceptable Tm window (deg C).
    tm_max:
        Upper bound of the acceptable Tm window (deg C).
    require_gc_clamp:
        If True, the 3' terminal base of every primer must be G or C.
    topology:
        Either "linear", "circular", or None (default). None means
        auto-detect from the sequence file: GenBank/SnapGene records carry an
        explicit topology annotation (falls back to "linear" if absent or
        unrecognised); plain FASTA has no topology annotation and is always
        treated as "linear". Pass "linear" or "circular" explicitly to
        override auto-detection.
    Returns
    -------
    :class:`MamePackageResult` with absolute paths of all three output files
    and a (possibly empty) ``warnings`` list.

    Raises
    ------
    FileNotFoundError
        If ``fasta_path`` or ``barcode_seeds_path`` does not exist.
    ValueError
        If FASTA parsing fails, gene range is invalid, barcode seeds fail
        validation, or the flank search window falls outside the CDS.
    """
    # Ensure output_dir exists
    output_dir = Path(output_dir)
    project_root = Path(project_root)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Resolve polymerase profile
    profile = get_profile(polymerase)

    # Step 1: parse CDS
    cds_seq, detected_topology = _parse_first_cds_sequence(Path(fasta_path))
    effective_topology = topology if topology is not None else detected_topology

    # Step 2: flanking primers (Tm-guided)
    fwd_flanking, rev_flanking, pkg_warnings = design_flanking_primers(
        cds_seq,
        gene_start=gene_start,
        gene_end=gene_end,
        profile=profile,
        overhang_min=overhang_min,
        overhang_max=overhang_max,
        binding_min_len=binding_min_len,
        binding_max_len=binding_max_len,
        tm_min=tm_min,
        tm_max=tm_max,
        require_gc_clamp=require_gc_clamp,
        topology=effective_topology,
    )

    # Step 3: barcode seeds
    seeds = parse_barcode_seeds(Path(barcode_seeds_path))

    # Step 4: barcodes_sequence.xlsx
    # Derive sanitized prefix from gene_name (raises ValueError on empty).
    gene_prefix = _sanitize_gene_prefix(gene_name)
    barcodes_xlsx_path = output_dir / "barcodes_sequence.xlsx"
    _write_barcodes_xlsx(
        path=barcodes_xlsx_path,
        seeds=seeds,
        fwd_flanking=fwd_flanking,
        rev_flanking=rev_flanking,
        gene_prefix=gene_prefix,
    )

    # Step 5: amplicon FASTA (gene region only)
    amplicon_fa_path = output_dir / f"{gene_prefix}_amplicon.fa"
    _write_amplicon_fasta(
        path=amplicon_fa_path,
        cds_seq=cds_seq,
        gene_start=gene_start,
        gene_end=gene_end,
        gene_name=gene_prefix,
    )

    # Step 6: mame_context.json
    context_json_path = project_root / "mame_context.json"
    _write_mame_context_json(
        path=context_json_path,
        project_root=project_root,
        barcodes_xlsx=barcodes_xlsx_path,
        amplicon_fa=amplicon_fa_path,
    )

    amplicon_length = _compute_amplicon_length(
        cds_seq=cds_seq,
        fwd_flanking=fwd_flanking,
        rev_flanking=rev_flanking,
    )

    return MamePackageResult(
        barcodes_xlsx=barcodes_xlsx_path,
        amplicon_fa=amplicon_fa_path,
        context_json=context_json_path,
        warnings=pkg_warnings,
        amplicon_length=amplicon_length,
    )


def _compute_amplicon_length(
    cds_seq: str,
    fwd_flanking: str,
    rev_flanking: str,
) -> int | None:
    """Locate primer binding sites on the template and return PCR amplicon length.

    Returns None if either primer is not found on the template (defensive — this
    should not happen since design_flanking_primers picks the sequences directly
    from cds_seq, but search may fail if rev primer is reverse-complemented).
    """
    seq_upper = cds_seq.upper()
    fwd_upper = fwd_flanking.upper()
    fwd_pos = seq_upper.find(fwd_upper)
    if fwd_pos < 0:
        return None

    complement = str.maketrans("ACGTNacgtn", "TGCANtgcan")
    rev_binding = rev_flanking.translate(complement)[::-1].upper()
    rev_pos = seq_upper.rfind(rev_binding)
    if rev_pos < 0:
        return None

    return (rev_pos + len(rev_binding)) - fwd_pos


# ---------------------------------------------------------------------------
# Private write helpers
# ---------------------------------------------------------------------------

def _write_barcodes_xlsx(
    path: Path,
    seeds: dict[str, str],
    fwd_flanking: str,
    rev_flanking: str,
    gene_prefix: str,
) -> None:
    """Write the 20-row barcodes_sequence.xlsx consumed by MAME.

    Output sequence = SEED (uppercase) + flanking (lowercase), concatenated.
    The MAME sort_barcode module trims the flanking part during matching, so
    including it here satisfies the full-primer column B requirement.

    Row names are ``{gene_prefix}{_FWD_SUFFIX}{i}`` /
    ``{gene_prefix}{_REV_SUFFIX}{i}``. The reader (``parse_combinatorial_barcodes``)
    is gene-agnostic and matches any prefix that ends with ``_f_<int>`` /
    ``_r_<int>``.
    """
    import openpyxl  # local import

    wb = openpyxl.Workbook()
    ws = wb.active
    if ws is None:
        ws = wb.create_sheet()
    ws.title = "Barcodes"
    ws.append(["name", "sequence"])

    for i in range(1, _N_FWD + 1):
        name = f"{gene_prefix}{_FWD_SUFFIX}{i}"
        seq = seeds[f"fwd_{i}"].upper() + fwd_flanking
        ws.append([name, seq])

    for i in range(1, _N_REV + 1):
        name = f"{gene_prefix}{_REV_SUFFIX}{i}"
        seq = seeds[f"rev_{i}"].upper() + rev_flanking
        ws.append([name, seq])

    wb.save(str(path))


def _write_amplicon_fasta(
    path: Path,
    cds_seq: str,
    gene_start: int,
    gene_end: int,
    gene_name: str,
) -> None:
    """Write a single-record FASTA of the gene region."""
    amplicon = cds_seq[gene_start:gene_end].upper()
    with path.open("w", encoding="utf-8") as fh:
        fh.write(f">{gene_name}_amplicon start={gene_start} end={gene_end}\n")
        # 60-character line wrap (standard FASTA)
        for i in range(0, len(amplicon), 60):
            fh.write(amplicon[i:i + 60] + "\n")


def _ctx_path(p: Path, root: Path) -> str:
    """Return relative posix path if inside root, else absolute posix path."""
    rp = p.resolve()
    try:
        return rp.relative_to(root).as_posix()
    except ValueError:
        return rp.as_posix()


def _write_mame_context_json(
    path: Path,
    project_root: Path,
    barcodes_xlsx: Path,
    amplicon_fa: Path,
) -> None:
    """Write mame_context.json with relative paths for files inside project_root,
    or absolute paths for files outside it.

    Schema 2 dropped ``sample_map_template_path``. The number is bumped rather
    than the key quietly omitted because a reader has to be able to tell "this
    project has no sample map" from "this file was written before the pointer
    existed", and only the schema number says which.
    """
    root = project_root.resolve()
    context = {
        "schema": 2,
        "published_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "custom_barcodes_path": _ctx_path(barcodes_xlsx, root),
        "reference_path": _ctx_path(amplicon_fa, root),
    }
    path.write_text(
        json.dumps(context, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
