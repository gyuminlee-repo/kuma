"""Generate demo fixtures for MAME analysis pipeline.

Simulates a Native Barcoding Kit V14 run:
  - 3 native barcodes (NB01, NB02, NB03) × 96 custom barcodes = 288 wells
  - NB01/02/03 are replicates of the same 96 mutants
  - Custom barcodes are indexed by 8-row × 12-col plate layout:
    row 1-8, col 1-12 → labels 1_1 .. 8_12  (96 total)

Verdict class distribution across 288 wells (rows in 96-mutant × 3-replicate matrix):
  PASS      ~50%  → 144 wells
  AMBIGUOUS ~10%  → 29 wells   (closest to PASS, but extra adjacent AA change)
  FRAMESHIFT ~10% → 29 wells
  MANY       ~5%  → 14 wells
  LOWDEPTH  ~15%  → 43 wells
  WRONG_AA  ~10%  → 29 wells

Each mutant has a single intended AA substitution in the synthetic ~1700 bp CDS.
Positions are evenly spaced across the protein (spacing = 5 codons).

Usage
-----
    python fixtures/mame_demo/generate.py           # skip existing files
    python fixtures/mame_demo/generate.py --force   # overwrite everything

Reproducibility
---------------
    random.seed(42) is set at module top — identical output on every run.
"""

from __future__ import annotations

import argparse
import random
from pathlib import Path

import openpyxl

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DEMO_ROOT = Path(__file__).resolve().parent
CONSENSUS_ROOT = DEMO_ROOT / "consensus"
REFERENCE_PATH = DEMO_ROOT / "reference.fasta"
XLSX_PATH = DEMO_ROOT / "KURO_expected.xlsx"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
random.seed(42)

# Target pad size for non-LOWDEPTH files: 52 KB
_PAD_BYTES_ABOVE = 52 * 1024
# LOWDEPTH files are written without padding; this ceiling is used to verify
# that no LOWDEPTH file accidentally exceeds the depth threshold.
_LOWDEPTH_MAX_BYTES = 30 * 1024

# Plate layout: 8 rows × 12 cols = 96 wells
_ROWS = 8
_COLS = 12
_N_WELLS = _ROWS * _COLS  # 96

# 3 native barcodes
_NBS = ["NB01", "NB02", "NB03"]

# Verdict distribution across 288 wells (96 mutants × 3 replicates)
# Assignment strategy: per-mutant, each of the 3 replicates gets an
# independently chosen case type, but total counts obey the distribution.
_VERDICT_DISTRIBUTION: list[tuple[str, int]] = [
    ("PASS", 144),
    ("AMBIGUOUS", 29),
    ("FRAMESHIFT", 29),
    ("MANY", 14),
    ("LOWDEPTH", 43),
    ("WRONG_AA", 29),
]
# Total = 288

# Amino acid alphabet (single-letter, no stop)
_AAS = list("ACDEFGHIKLMNPQRSTVWY")

# E. coli-preferred codon table (table 11, most-used codon per AA)
_PREFERRED_CODON: dict[str, str] = {
    "A": "GCG", "C": "TGC", "D": "GAC", "E": "GAA",
    "F": "TTC", "G": "GGC", "H": "CAC", "I": "ATC",
    "K": "AAA", "L": "CTG", "M": "ATG", "N": "AAC",
    "P": "CCG", "Q": "CAG", "R": "CGC", "S": "AGC",
    "T": "ACC", "V": "GTG", "W": "TGG", "Y": "TAC",
}

# Alternative codons for each AA (distinct from preferred).
# Used in WRONG_AA fallback: when no entry exists in _WRONG_AA_SUBSTITUTION,
# the wrong codon is drawn from this table so it differs from _PREFERRED_CODON.
_ALT_CODON: dict[str, str] = {
    "A": "GCC", "C": "TGT", "D": "GAT", "E": "GAG",
    "F": "TTT", "G": "GGT", "H": "CAT", "I": "ATT",
    "K": "AAG", "L": "CTC", "M": "ATG", "N": "AAT",
    "P": "CCA", "Q": "CAA", "R": "CGT", "S": "TCG",
    "T": "ACA", "V": "GTC", "W": "TGG", "Y": "TAT",
}

# Second alternative (for WRONG_AA — different AA)
_WRONG_AA_SUBSTITUTION: dict[str, tuple[str, str]] = {
    # mt_aa → (wrong_aa, wrong_codon)
    "F": ("Y", "TAC"), "N": ("D", "GAC"), "D": ("E", "GAA"),
    "K": ("R", "CGC"), "V": ("A", "GCG"), "L": ("I", "ATC"),
    "S": ("T", "ACC"), "H": ("Q", "CAG"), "I": ("V", "GTG"),
    "R": ("K", "AAA"), "T": ("S", "AGC"), "E": ("Q", "CAG"),
    "G": ("A", "GCG"), "A": ("V", "GTG"), "Q": ("E", "GAA"),
    "C": ("S", "AGC"), "Y": ("F", "TTC"), "W": ("R", "CGC"),
    "P": ("L", "CTG"), "M": ("L", "CTG"),
}


# ---------------------------------------------------------------------------
# Synthetic reference CDS (~1701 bp)
# ---------------------------------------------------------------------------

def _build_reference_cds() -> str:
    """Build a deterministic synthetic CDS.

    Seed is fixed at module level (random.seed(42)).
    Starts with ATG, ends with TGA stop codon.
    No internal stop codons (verified by construction).
    Length = 567 codons × 3 = 1701 bp.
    """
    codons: list[str] = ["ATG"]  # mandatory start
    for _ in range(565):
        aa = random.choice(_AAS)
        codons.append(_PREFERRED_CODON[aa])
    codons.append("TGA")  # stop
    return "".join(codons)


# Build once at module load (seed already set)
_REFERENCE_CDS: str = _build_reference_cds()
# CDS_END: position AFTER last nt of stop codon (1-based exclusive = length)
CDS_END: int = len(_REFERENCE_CDS)  # 1701
# Protein length (excluding stop): 566 AAs (indices 0..565 in AA space, 1-based 1..566)
_PROTEIN_LEN: int = CDS_END // 3 - 1  # 566


# ---------------------------------------------------------------------------
# Mutant definitions
# ---------------------------------------------------------------------------

def _build_mutants() -> list[dict]:
    """Define 96 mutants with evenly spaced positions across the protein.

    Returns list of dicts:
        mutant_id, position (1-based AA), wt_aa, mt_aa,
        wt_codon, mt_codon, group_id, primer_set_ref,
        notation_type, status

    Position spacing: `spacing = 5` codons.
    Positions: 6, 11, 16, ..., 481  (6 + i * spacing for i in 0..95).
    All within the 1..566 protein range.
    """
    mutants: list[dict] = []
    spacing = 5  # step between mutant positions (in AA units)
    for i in range(_N_WELLS):
        pos = 6 + i * spacing  # 1-based AA position
        # Codon boundaries (0-based nt): (pos-1)*3 .. pos*3
        codon_start = (pos - 1) * 3
        wt_codon = _REFERENCE_CDS[codon_start: codon_start + 3]
        # Determine WT AA from codon
        wt_aa = _codon_to_aa(wt_codon)
        # Pick a MT AA that differs from WT
        mt_aa = _pick_mt_aa(wt_aa, seed_offset=i)
        mt_codon = _PREFERRED_CODON[mt_aa]
        mutant_id = f"M{i+1:03d}_{wt_aa}{pos}{mt_aa}"
        mutants.append({
            "mutant_id": mutant_id,
            "position": pos,
            "wt_aa": wt_aa,
            "mt_aa": mt_aa,
            "wt_codon": wt_codon,
            "mt_codon": mt_codon,
            "group_id": "",
            "primer_set_ref": mutant_id,
            "notation_type": "substitution",
            "status": "DESIGNED",
        })
    return mutants


_CODON_TO_AA_CACHE: dict[str, str] = {}


def _codon_to_aa(codon: str) -> str:
    """Translate a single codon using NCBI table 11 (bacterial/plant plastid)."""
    if codon not in _CODON_TO_AA_CACHE:
        from Bio.Seq import Seq  # local import; Biopython guaranteed present
        aa = str(Seq(codon).translate(table="11"))
        _CODON_TO_AA_CACHE[codon] = aa
    return _CODON_TO_AA_CACHE[codon]


def _pick_mt_aa(wt_aa: str, seed_offset: int) -> str:
    """Pick a mutant AA that differs from the WT."""
    candidates = [a for a in _AAS if a != wt_aa and a != "*"]
    # Use deterministic selection (seed already fixed globally)
    return candidates[seed_offset % len(candidates)]


# ---------------------------------------------------------------------------
# Case type assignment
# ---------------------------------------------------------------------------

def _assign_cases() -> list[list[str]]:
    """Assign case types for 96 mutants × 3 replicates.

    Returns a 96-element list; each element is a 3-element list of case names
    for [NB01, NB02, NB03].

    Total counts across all 288 assignments match _VERDICT_DISTRIBUTION.
    """
    # Build flat list of 288 case labels matching distribution
    flat: list[str] = []
    for case_name, count in _VERDICT_DISTRIBUTION:
        flat.extend([case_name] * count)
    assert len(flat) == 288, f"Expected 288 cases, got {len(flat)}"

    # Shuffle with fixed seed (already seeded at module level)
    random.shuffle(flat)

    # Reshape into 96 × 3
    matrix: list[list[str]] = []
    for i in range(96):
        matrix.append([flat[i * 3], flat[i * 3 + 1], flat[i * 3 + 2]])
    return matrix


# ---------------------------------------------------------------------------
# Sequence builders
# ---------------------------------------------------------------------------

def _mutate_cds(cds: str, mutant: dict, case: str) -> str:
    """Return a mutated CDS string for the given mutant and case type.

    PASS        : apply exactly the intended mt_codon
    AMBIGUOUS   : apply mt_codon + one adjacent AA substitution (±1 codon)
    FRAMESHIFT  : apply mt_codon + insert 2 extra bases nearby (two INDEL
                  markers within frameshift_window_bp=10)
    MANY        : apply mt_codon + 6 additional random AA substitutions
    LOWDEPTH    : apply mt_codon (sequence is fine; file stays small)
    WRONG_AA    : apply a different AA at the intended position
    """
    pos = mutant["position"]  # 1-based AA
    mt_codon = mutant["mt_codon"]
    codon_start = (pos - 1) * 3

    cds_list = list(cds)  # mutable copy

    if case == "PASS":
        # Exactly one intended substitution
        for k, base in enumerate(mt_codon):
            cds_list[codon_start + k] = base

    elif case == "AMBIGUOUS":
        # Intended mutation + adjacent AA change (within ±5 codons)
        for k, base in enumerate(mt_codon):
            cds_list[codon_start + k] = base
        # Pick adjacent position (pos+2, capped)
        adj_pos = min(pos + 2, _PROTEIN_LEN - 1)  # 1-based, keep safe
        adj_codon_start = (adj_pos - 1) * 3
        adj_wt = cds[adj_codon_start: adj_codon_start + 3]
        adj_wt_aa = _codon_to_aa(adj_wt)
        # Introduce a synonymous-looking but different AA via alt codon mismatch
        adj_mt_aa = _pick_mt_aa(adj_wt_aa, seed_offset=pos + 7)
        adj_mt_codon = _PREFERRED_CODON[adj_mt_aa]
        for k, base in enumerate(adj_mt_codon):
            cds_list[adj_codon_start + k] = base

    elif case == "FRAMESHIFT":
        # Intended mutation + two nucleotide substitutions within 10 bp
        # The FRAMESHIFT detector looks for 2+ NT INDEL markers within
        # frameshift_window_bp. We introduce them by making positions look
        # like INDELs: insert extra characters is not possible in a list-of-chars
        # model without alignment. Instead we delete 1 nt and insert 2 nt
        # to shift the reading frame.
        # Simpler approach: replace two adjacent nucleotides in a short window
        # so that after string-level diff with reference both appear as INDELs.
        # The extract_nt_changes function reports {pos}_INDEL when qry is longer
        # than ref. So we extend the CDS by inserting 2 extra bases.
        for k, base in enumerate(mt_codon):
            cds_list[codon_start + k] = base
        # Insert 2 extra bases after the mt_codon to create 2 INDEL markers
        insert_pos = codon_start + 3
        cds_list.insert(insert_pos, "A")
        cds_list.insert(insert_pos + 1, "A")  # two consecutive INDELs

    elif case == "MANY":
        # Intended mutation + 6 extra substitutions spread across the CDS
        for k, base in enumerate(mt_codon):
            cds_list[codon_start + k] = base
        # Add 6 more AA changes at well-separated positions
        extra_positions = [10, 50, 100, 200, 300, 450]
        for ep in extra_positions:
            if ep == pos:
                ep += 1
            ep_codon_start = (ep - 1) * 3
            if ep_codon_start + 3 > len(cds_list):
                continue
            ep_mt_aa = _pick_mt_aa(
                _codon_to_aa(cds[ep_codon_start: ep_codon_start + 3]),
                seed_offset=ep,
            )
            ep_mt_codon = _PREFERRED_CODON[ep_mt_aa]
            for k, base in enumerate(ep_mt_codon):
                cds_list[ep_codon_start + k] = base

    elif case == "LOWDEPTH":
        # Sequence has correct mutation; file size is kept small (no padding)
        for k, base in enumerate(mt_codon):
            cds_list[codon_start + k] = base

    elif case == "WRONG_AA":
        # Wrong AA at the intended position.
        # Priority: _WRONG_AA_SUBSTITUTION lookup → _ALT_CODON of a different AA.
        wrong_info = _WRONG_AA_SUBSTITUTION.get(mutant["mt_aa"])
        if wrong_info is not None:
            _, wrong_codon = wrong_info
        else:
            # Fallback: pick a different AA and use its alt codon so the
            # resulting codon is distinct from both wt_codon and mt_codon.
            wrong_aa = _pick_mt_aa(mutant["mt_aa"], seed_offset=pos + 3)
            wrong_codon = _ALT_CODON.get(wrong_aa, _PREFERRED_CODON[wrong_aa])
        for k, base in enumerate(wrong_codon):
            cds_list[codon_start + k] = base

    return "".join(cds_list)


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------

def _write_fasta(path: Path, header: str, sequence: str, pad: bool) -> None:
    """Write a FASTA file, optionally padding to ≥52 KB."""
    path.parent.mkdir(parents=True, exist_ok=True)
    wrapped = "\n".join(sequence[i: i + 60] for i in range(0, len(sequence), 60))
    text = f">{header}\n{wrapped}\n"
    if pad:
        encoded = text.encode("utf-8")
        blank_filler = ("\n" * 64).encode("utf-8")
        while len(encoded) < _PAD_BYTES_ABOVE:
            encoded += blank_filler
        path.write_bytes(encoded)
    else:
        path.write_text(text, encoding="utf-8")


def _write_reference(force: bool) -> None:
    if REFERENCE_PATH.exists() and not force:
        return
    REFERENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    wrapped = "\n".join(_REFERENCE_CDS[i: i + 60] for i in range(0, len(_REFERENCE_CDS), 60))
    REFERENCE_PATH.write_text(
        f">synthetic_isoprene_synthase length={CDS_END} CDS_END={CDS_END}\n{wrapped}\n",
        encoding="utf-8",
    )


def _write_xlsx(mutants: list[dict], force: bool) -> None:
    if XLSX_PATH.exists() and not force:
        return
    wb = openpyxl.Workbook()
    # --- Fwd List sheet (format from create_fixtures.py) ---
    ws_fwd = wb.active
    assert ws_fwd is not None
    ws_fwd.title = "Fwd List"
    ws_fwd.append([
        "Well", "Primer Name", "Sequence", "Length", "Tm", "Tm_Overlap",
        "WT_Codon", "MT_Codon", "Mutation",
    ])
    # One row per mutant (synthetic primer sequences)
    for idx, m in enumerate(mutants):
        row_letter = chr(ord("A") + (idx % 8))
        col_num = (idx // 8) + 1
        well = f"{row_letter}{col_num}"
        # Synthetic 20-mer primer (partial CDS region)
        pos = m["position"]
        codon_start = (pos - 1) * 3
        anchor_len = min(17, CDS_END - codon_start - 3)
        anchor = _REFERENCE_CDS[codon_start + 3: codon_start + 3 + anchor_len]
        primer_seq = m["mt_codon"] + anchor
        ws_fwd.append([
            well,
            f"{m['mutant_id']}_F",
            primer_seq,
            len(primer_seq),
            round(62.0 + (pos % 5) * 0.5, 1),
            round(42.0 + (pos % 3) * 0.3, 1),
            m["wt_codon"],
            m["mt_codon"],
            f"{m['wt_aa']}{pos}{m['mt_aa']}",
        ])

    # --- expected_mutations sheet ---
    ws_exp = wb.create_sheet("expected_mutations")
    ws_exp.append([
        "mutant_id", "position", "wt_aa", "mt_aa", "wt_codon", "mt_codon",
        "group_id", "primer_set_ref", "notation_type", "status",
    ])
    for m in mutants:
        ws_exp.append([
            m["mutant_id"], m["position"], m["wt_aa"], m["mt_aa"],
            m["wt_codon"], m["mt_codon"], m["group_id"], m["primer_set_ref"],
            m["notation_type"], m["status"],
        ])

    XLSX_PATH.parent.mkdir(parents=True, exist_ok=True)
    wb.save(XLSX_PATH)


# ---------------------------------------------------------------------------
# Well label helpers
# ---------------------------------------------------------------------------

def _well_labels() -> list[str]:
    """Return 96 well labels in row-major order: 1_1 .. 8_12."""
    labels: list[str] = []
    for row in range(1, _ROWS + 1):
        for col in range(1, _COLS + 1):
            labels.append(f"{row}_{col}")
    return labels


# ---------------------------------------------------------------------------
# Main generation
# ---------------------------------------------------------------------------

def generate(force: bool = False) -> None:
    """Generate all fixture files."""
    print(f"Demo root: {DEMO_ROOT}")
    print(f"Force overwrite: {force}")

    # 1) Reference
    _write_reference(force)
    print(f"  [OK] reference.fasta ({CDS_END} bp, CDS_END={CDS_END})")

    # 2) Mutant definitions
    mutants = _build_mutants()
    assert len(mutants) == 96, f"Expected 96 mutants, got {len(mutants)}"

    # 3) XLSX
    _write_xlsx(mutants, force)
    print(f"  [OK] KURO_expected.xlsx ({len(mutants)} mutants)")

    # 4) Case assignment matrix (96 × 3)
    case_matrix = _assign_cases()

    # 5) Well labels
    well_labels = _well_labels()
    assert len(well_labels) == 96

    # 6) Write FASTA files
    stats: dict[str, int] = {name: 0 for name, _ in _VERDICT_DISTRIBUTION}
    total_bytes = 0
    file_sizes_kb: list[float] = []
    files_written = 0
    files_skipped = 0

    for nb_idx, nb in enumerate(_NBS):
        nb_dir = CONSENSUS_ROOT / nb
        nb_dir.mkdir(parents=True, exist_ok=True)
        for well_idx, label in enumerate(well_labels):
            mutant = mutants[well_idx]
            case = case_matrix[well_idx][nb_idx]
            out_path = nb_dir / f"{label}.fasta"

            if out_path.exists() and not force:
                files_skipped += 1
                continue

            seq = _mutate_cds(_REFERENCE_CDS, mutant, case)
            pad = case != "LOWDEPTH"
            _write_fasta(out_path, header=label, sequence=seq, pad=pad)

            size = out_path.stat().st_size
            # Verify LOWDEPTH files do not accidentally exceed the depth threshold.
            assert case != "LOWDEPTH" or size <= _LOWDEPTH_MAX_BYTES, (
                f"LOWDEPTH file {out_path} is {size} bytes, "
                f"exceeds _LOWDEPTH_MAX_BYTES={_LOWDEPTH_MAX_BYTES}"
            )
            total_bytes += size
            file_sizes_kb.append(size / 1024)
            stats[case] += 1
            files_written += 1

    # Print summary
    print(f"\n  Files written: {files_written}, skipped (already exist): {files_skipped}")
    print(f"\n  Case distribution (written this run):")
    for case_name, count in stats.items():
        print(f"    {case_name:<12}: {count:>4}")

    if file_sizes_kb:
        mean_kb = sum(file_sizes_kb) / len(file_sizes_kb)
        print(f"\n  Total bytes: {total_bytes:,}")
        print(f"  Mean file size: {mean_kb:.1f} KB")
        above_50 = sum(1 for s in file_sizes_kb if s >= 50)
        below_30 = sum(1 for s in file_sizes_kb if s < 30)
        print(f"  Files >= 50 KB: {above_50}")
        print(f"  Files <  30 KB: {below_30}")

    print("\nDone.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate MAME demo fixtures")
    parser.add_argument(
        "--force", action="store_true",
        help="Overwrite existing files (default: skip)",
    )
    args = parser.parse_args()
    generate(force=args.force)
