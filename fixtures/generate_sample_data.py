"""Generate KURO SDM primer design tool fixture files.

Outputs:
  fixtures/sample_plasmid.gb       — GenBank circular plasmid (~5000 bp, 3 CDS)
  fixtures/sample_evolvepro.csv    — EVOLVEpro df_test.csv format (120 variants)

Note: SnapGene .dna write is not supported by Biopython 1.86; skipped per spec.
"""

from __future__ import annotations

import csv
import random
import sys
from datetime import date
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SEED = 42
random.seed(SEED)

# E. coli K-12 optimal codons (from codon_table.py)
ECOLI_BEST: dict[str, str] = {
    "A": "GCG", "R": "CGC", "N": "AAC", "D": "GAT", "C": "TGC",
    "Q": "CAG", "E": "GAA", "G": "GGC", "H": "CAC", "I": "ATT",
    "L": "CTG", "K": "AAA", "M": "ATG", "F": "TTT", "P": "CCG",
    "S": "AGC", "T": "ACC", "W": "TGG", "Y": "TAT", "V": "GTG",
    "*": "TAA",
}

CODON_TO_AA: dict[str, str] = {}
for _aa, _codon in ECOLI_BEST.items():
    CODON_TO_AA[_codon] = _aa

# Full standard genetic code (for translation)
GENETIC_CODE: dict[str, str] = {
    "TTT": "F", "TTC": "F", "TTA": "L", "TTG": "L",
    "CTT": "L", "CTC": "L", "CTA": "L", "CTG": "L",
    "ATT": "I", "ATC": "I", "ATA": "I", "ATG": "M",
    "GTT": "V", "GTC": "V", "GTA": "V", "GTG": "V",
    "TCT": "S", "TCC": "S", "TCA": "S", "TCG": "S",
    "CCT": "P", "CCC": "P", "CCA": "P", "CCG": "P",
    "ACT": "T", "ACC": "T", "ACA": "T", "ACG": "T",
    "GCT": "A", "GCC": "A", "GCA": "A", "GCG": "A",
    "TAT": "Y", "TAC": "Y", "TAA": "*", "TAG": "*",
    "CAT": "H", "CAC": "H", "CAA": "Q", "CAG": "Q",
    "AAT": "N", "AAC": "N", "AAA": "K", "AAG": "K",
    "GAT": "D", "GAC": "D", "GAA": "E", "GAG": "E",
    "TGT": "C", "TGC": "C", "TGA": "*", "TGG": "W",
    "CGT": "R", "CGC": "R", "CGA": "R", "CGG": "R",
    "AGT": "S", "AGC": "S", "AGA": "R", "AGG": "R",
    "GGT": "G", "GGC": "G", "GGA": "G", "GGG": "G",
}

AMINO_ACIDS = list("ACDEFGHIKLMNPQRSTVWY")
STOP_CODONS = {"TAA", "TAG", "TGA"}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def random_codon(aa: str) -> str:
    """Return E. coli best codon for given amino acid."""
    return ECOLI_BEST[aa]


def make_cds_dna(aa_sequence: str) -> str:
    """Encode an amino acid sequence as a DNA CDS using E. coli optimal codons.

    Appends TAA stop codon. Does not include ATG start in aa_sequence.
    """
    return "".join(ECOLI_BEST[aa] for aa in aa_sequence) + ECOLI_BEST["*"]


def random_aa_sequence(length: int) -> str:
    """Generate a random amino acid sequence (no stop codons, no Met except start)."""
    # Exclude M to keep ATG start codon unique-ish; exclude * (stop)
    pool = [aa for aa in AMINO_ACIDS if aa != "M"]
    return "".join(random.choice(pool) for _ in range(length - 1))  # -1 for Met start


def translate(dna: str) -> str:
    """Translate a DNA sequence starting with ATG."""
    aa_parts = []
    for i in range(0, len(dna) - 2, 3):
        codon = dna[i:i + 3]
        aa = GENETIC_CODE.get(codon, "?")
        if aa == "*":
            break
        aa_parts.append(aa)
    return "".join(aa_parts)


def make_random_linker(length: int) -> str:
    """Generate random non-coding DNA (GC ~50%)."""
    bases = "ACGT"
    return "".join(random.choice(bases) for _ in range(length))


# ---------------------------------------------------------------------------
# Build plasmid sequence
# ---------------------------------------------------------------------------

def build_plasmid() -> tuple[str, list[dict]]:
    """Build a ~5000 bp random circular plasmid with 3 CDS features.

    Returns:
        (full_sequence, list of CDS dicts with start/end/gene/product/aa_seq)
    """
    # CDS 1: small enzyme-like ~120 aa
    aa1 = "M" + random_aa_sequence(120)
    cds1_dna = make_cds_dna(aa1)  # includes stop codon

    # CDS 2: target protein (longest) ~380 aa → 300-500 aa requirement
    aa2 = "M" + random_aa_sequence(380)
    cds2_dna = make_cds_dna(aa2)

    # CDS 3: small regulator ~100 aa
    aa3 = "M" + random_aa_sequence(100)
    cds3_dna = make_cds_dna(aa3)

    # Intergenic linkers to reach ~5000 bp total
    # CDS lengths (bp): each aa*3 + 3 (stop)
    len1 = len(cds1_dna)   # 121*3 + 3 = 366
    len2 = len(cds2_dna)   # 381*3 + 3 = 1146
    len3 = len(cds3_dna)   # 101*3 + 3 = 306
    total_cds = len1 + len2 + len3   # 1818

    target_total = 5000
    remaining = target_total - total_cds  # ~3182 bp in linkers
    # Distribute: 4 linkers (before CDS1, between 1-2, between 2-3, after CDS3)
    l0 = remaining // 4
    l1 = remaining // 4
    l2 = remaining // 4
    l3 = remaining - l0 - l1 - l2

    linker0 = make_random_linker(l0)
    linker1 = make_random_linker(l1)
    linker2 = make_random_linker(l2)
    linker3 = make_random_linker(l3)

    # Assemble
    seq = linker0 + cds1_dna + linker1 + cds2_dna + linker2 + cds3_dna + linker3

    # Calculate feature coordinates (0-based GenBank start, 1-based end in GenBank)
    pos = 0
    pos += len(linker0)
    cds1_start = pos       # 0-based
    pos += len1
    cds1_end = pos         # exclusive (no stop in feature by convention)

    pos += len(linker1)
    cds2_start = pos
    pos += len2
    cds2_end = pos

    pos += len(linker2)
    cds3_start = pos
    pos += len3
    cds3_end = pos

    # Verify ATG at CDS starts
    assert seq[cds1_start:cds1_start + 3] == "ATG", f"CDS1 start fail: {seq[cds1_start:cds1_start+3]}"
    assert seq[cds2_start:cds2_start + 3] == "ATG", f"CDS2 start fail: {seq[cds2_start:cds2_start+3]}"
    assert seq[cds3_start:cds3_start + 3] == "ATG", f"CDS3 start fail: {seq[cds3_start:cds3_start+3]}"

    cds_list = [
        {
            "gene": "lacZ_alpha",
            "product": "beta-galactosidase alpha fragment",
            "start": cds1_start,   # 0-based inclusive
            "end": cds1_end,       # 0-based exclusive (Biopython convention)
            "aa_seq": aa1,
            "dna": cds1_dna,
        },
        {
            "gene": "synR",
            "product": "synthetic regulatory protein SynR",
            "start": cds2_start,
            "end": cds2_end,
            "aa_seq": aa2,
            "dna": cds2_dna,
        },
        {
            "gene": "ampR",
            "product": "beta-lactamase (ampicillin resistance)",
            "start": cds3_start,
            "end": cds3_end,
            "aa_seq": aa3,
            "dna": cds3_dna,
        },
    ]

    return seq, cds_list


# ---------------------------------------------------------------------------
# Write GenBank file
# ---------------------------------------------------------------------------

def write_genbank(filepath: Path, seq: str, cds_list: list[dict]) -> None:
    """Write a GenBank file without Biopython (manual format for reliability)."""
    total_len = len(seq)
    today = date.today().strftime("%d-%b-%Y").upper()

    lines: list[str] = []

    # LOCUS line
    lines.append(
        f"LOCUS       pSampleKURO             {total_len} bp    DNA     circular SYN {today}"
    )
    lines.append("DEFINITION  Synthetic plasmid for KURO SDM primer design tool testing.")
    lines.append("ACCESSION   pSampleKURO")
    lines.append("VERSION     pSampleKURO.1")
    lines.append("KEYWORDS    synthetic; SDM; test fixture.")
    lines.append("SOURCE      synthetic construct")
    lines.append("  ORGANISM  synthetic construct")
    lines.append("            other sequences; artificial sequences; vectors.")
    lines.append("FEATURES             Location/Qualifiers")
    lines.append('     source          1..{}'.format(total_len))
    lines.append('                     /organism="synthetic construct"')
    lines.append('                     /mol_type="other DNA"')

    # CDS features
    for cds in cds_list:
        # GenBank uses 1-based, inclusive coordinates
        gb_start = cds["start"] + 1
        gb_end = cds["end"]       # end is exclusive in Biopython, so gb_end = end (1-based inclusive)
        aa_seq = cds["aa_seq"]
        # translation excludes the stop codon, i.e. everything after ATG up to (not including) stop
        translation = aa_seq  # already starts with M, no stop char
        lines.append(f'     CDS             {gb_start}..{gb_end}')
        lines.append(f'                     /gene="{cds["gene"]}"')
        lines.append(f'                     /product="{cds["product"]}"')
        lines.append(f'                     /codon_start=1')
        lines.append(f'                     /transl_table=11')
        # Wrap translation at 59 chars per line
        trans_line = f'                     /translation="{translation[:45]}'
        if len(translation) > 45:
            remaining_trans = translation[45:]
            lines.append(trans_line)
            while remaining_trans:
                chunk = remaining_trans[:58]
                remaining_trans = remaining_trans[58:]
                if remaining_trans:
                    lines.append(f'                     {chunk}')
                else:
                    lines.append(f'                     {chunk}"')
        else:
            lines.append(trans_line + '"')

    # ORIGIN
    lines.append("ORIGIN")
    seq_upper = seq.upper()
    for i in range(0, total_len, 60):
        chunk = seq_upper[i:i + 60]
        # Split into groups of 10
        groups = [chunk[j:j + 10] for j in range(0, len(chunk), 10)]
        lines.append(f"{i + 1:>9} {' '.join(groups)}")

    lines.append("//")

    filepath.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Write EVOLVEpro CSV
# ---------------------------------------------------------------------------

def write_evolvepro_csv(
    filepath: Path,
    cds: dict,
    n_variants: int = 120,
) -> None:
    """Generate EVOLVEpro df_test.csv format from the longest CDS.

    Columns: variant, y_pred  (sorted by y_pred descending).
    variant format: {WT_AA}{1-based_position}{MT_AA}
    """
    aa_seq: str = cds["aa_seq"]   # starts with M
    aa_len = len(aa_seq)

    # Pool of target AAs (exclude same as WT and stop)
    all_aas = list(AMINO_ACIDS)  # 20 standard AAs

    variants: list[tuple[str, float]] = []
    used: set[str] = set()

    attempts = 0
    while len(variants) < n_variants and attempts < n_variants * 10:
        attempts += 1
        # Pick random position (1-based, skip position 1 = Met start to avoid ATG change)
        pos = random.randint(2, aa_len)
        wt_aa = aa_seq[pos - 1]

        # Pick random mutant AA (different from WT)
        candidates = [aa for aa in all_aas if aa != wt_aa]
        mt_aa = random.choice(candidates)

        notation = f"{wt_aa}{pos}{mt_aa}"
        if notation in used:
            continue
        used.add(notation)

        # y_pred in [0.5, 1.0]
        y_pred = round(random.uniform(0.5, 1.0), 4)
        variants.append((notation, y_pred))

    # Sort descending by y_pred
    variants.sort(key=lambda x: x[1], reverse=True)

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["variant", "y_pred"])
        for notation, y_pred in variants:
            writer.writerow([notation, y_pred])


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

def verify_genbank(gb_path: Path, cds_list: list[dict]) -> bool:
    """Verify GenBank file loads correctly via load_sequence."""
    import sys
    sys.path.insert(0, str(gb_path.parent.parent))

    try:
        from kuro.sdm_engine import load_sequence
        header, seq, genes = load_sequence(gb_path)
        print(f"[GB verify] header={repr(header[:60])}, len={len(seq)}, genes={len(genes)}")
        if len(seq) == 0:
            print("  FAIL: empty sequence")
            return False
        if len(genes) == 0:
            print("  FAIL: no genes detected")
            return False
        for g in genes:
            print(f"  gene={g.gene!r}, product={g.product!r}, "
                  f"cds={g.cds_start}-{g.cds_end}, aa_len={g.aa_length}")
            # Check ATG at cds_start
            codon = seq[g.cds_start:g.cds_start + 3]
            if codon != "ATG":
                print(f"  WARN: expected ATG at {g.cds_start}, got {codon!r}")
        return True
    except Exception as exc:
        print(f"  FAIL: {exc}")
        return False


def verify_csv(csv_path: Path) -> bool:
    """Verify EVOLVEpro CSV basic parsing."""
    import re
    mutation_re = re.compile(r"^([A-Z])(\d+)([A-Z])$")
    rows = []
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert "variant" in (reader.fieldnames or []), "Missing 'variant' column"
        assert "y_pred" in (reader.fieldnames or []), "Missing 'y_pred' column"
        for row in reader:
            v = row["variant"]
            y = float(row["y_pred"])
            assert mutation_re.match(v), f"Bad variant notation: {v!r}"
            assert 0.0 <= y <= 1.0, f"y_pred out of range: {y}"
            rows.append((v, y))

    # Check sorted descending
    for i in range(1, len(rows)):
        assert rows[i - 1][1] >= rows[i][1], f"Not sorted at row {i}"

    print(f"[CSV verify] {len(rows)} variants, y_pred range [{rows[-1][1]:.4f}, {rows[0][1]:.4f}]")
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    project_root = Path(__file__).resolve().parent.parent
    samples_dir = project_root / "samples"
    samples_dir.mkdir(exist_ok=True)

    print("Building plasmid sequence...")
    seq, cds_list = build_plasmid()
    print(f"  Total plasmid: {len(seq)} bp")
    for cds in cds_list:
        aa_len = len(cds["aa_seq"])
        bp_len = cds["end"] - cds["start"]
        print(f"  {cds['gene']}: {cds['start']}-{cds['end']} ({bp_len} bp, {aa_len} aa)")

    # Identify longest CDS
    longest_cds = max(cds_list, key=lambda c: len(c["aa_seq"]))
    print(f"  Longest CDS: {longest_cds['gene']} ({len(longest_cds['aa_seq'])} aa)")

    # 1. Write GenBank
    gb_path = samples_dir / "sample_plasmid.gb"
    print(f"\nWriting {gb_path}...")
    write_genbank(gb_path, seq, cds_list)
    gb_size = gb_path.stat().st_size
    print(f"  Size: {gb_size} bytes ({gb_size / 1024:.1f} KB)")

    # 2. SnapGene .dna: not supported by Biopython SeqIO writers (snapgene absent from _FormatToWriter)
    print("\nSnapGene .dna: Biopython 1.86 SeqIO.write does not support 'snapgene' format — skipped.")

    # 3. Write EVOLVEpro CSV
    csv_path = samples_dir / "sample_evolvepro.csv"
    print(f"\nWriting {csv_path}...")
    write_evolvepro_csv(csv_path, longest_cds, n_variants=120)
    csv_size = csv_path.stat().st_size
    print(f"  Size: {csv_size} bytes ({csv_size / 1024:.1f} KB)")

    # ---------------------------------------------------------------------------
    # Verification
    # ---------------------------------------------------------------------------
    print("\n--- Verification ---")
    ok_gb = verify_genbank(gb_path, cds_list)
    ok_csv = verify_csv(csv_path)

    # File size checks
    if gb_size > 100 * 1024:
        print(f"WARN: GenBank file exceeds 100 KB ({gb_size / 1024:.1f} KB)")
    if csv_size > 10 * 1024:
        print(f"WARN: CSV file exceeds 10 KB ({csv_size / 1024:.1f} KB)")

    if ok_gb and ok_csv:
        print("\nAll checks PASSED.")
        return 0
    else:
        print("\nSome checks FAILED.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
