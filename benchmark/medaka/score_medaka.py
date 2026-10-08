"""
Score medaka consensus vs truth using edlib infix (HW) alignment.
Outputs TSV: tag, well, depth, medaka_ed, truth_len, consensus_len, len_match
"""
import os
import sys

import edlib

# Truth sequences (full, flank included)
TRUTHS = {
    "G1": "AATCCCACTACCACAGGAGGTTAAACCATGGTGTTCAAGAACTTCGATGCGCTGACCGGCAAAGACCTGAAAGAGTTCGCGAAATCGAAAAAAATGAACCTGAACAAGCTGAAAGCGTTCAACCAGTTCGCGAACATGAAAGCGTTCTTTTTTTACTTCAACAAGATCTTCAACAAGTTCGCGAACATGAACAAGTTCAACTGACTAGAGCGCAACGCATGTCATAGGG",
    "G2": "TATCTGACCTTCACAGGAGGTTAAACCATGGTGTTCAAGAACTTCGATGCGCTGACCGGCAAAGACCTGAAAGAGTTCGCGAAATCGAAAAAAATGAACCTGAACAAGCTGAAAGCGTTCAATCAGTTCGCGTACATGAAAGCGTTCTTTTTTTACTTCAACTAGATCTTCAACAAGTTCGCGAACATGAACAAGTTCAACTGACTAGAGCGCAACGCACTTGCCATTA",
    "G3": "GCGCGATTTTCACAGGAGGTTAAACCATGGTGTTCAAGAACTTCGATGCGCTGACCGGCAAAGACCTGAAAGAGTTCGCGAAATCGAAAAAAATGAACCTGAACAAGCTGAAAGCGTTCAACCAGTTCGCGAACATGAAAGCGTTGTTTTTTTACTTCAACAAGATCTTCAACAAGTTCGCGAACATGAACAAGTTCAACTGACTAGAGCGCAACGCATTCTACATAC",
    "G4": "GAACATACGGCACAGGAGGTTAAACCATGGTGTTCAAGAACTTCGATGCGCTGACCGGCAAAGACCTGAAAGAGTTCGCGAAATCGAAAAAAATGAACCTGAACAATGAAAGCGTTCAACCAGTTCGCGAACATGAAAGCGTTCTTTTTTTACTTCAACAAGATCTTCAACAAGTTCGCGAACATGAACAAGTTCAACTGACTAGAGCGCAACGCAGCCGCACTCT",
    "G5": "CGCTCATTAGCACAGGAGGTTAAACCATGGTGTTCAAGAACTTCGATGCGCTGACCGGCAAAGACCTGAAAGAGTTCGCGAAATCGAAAAATGAACCTGAACAAGCTGAAAGCGTTCAACCAGTTCGCGAACATGAAAGCGTTCTTTTTTTACTTCAACAAGATCTTCAACAAGTTCGCGAACATGAACAAGTTCAACTGACTAGAGCGCAACGCAGGTTGCGAGG",
}

# Truth amplicon lengths (indel truth)
TRUTH_ALEN = {"G1": 177, "G2": 177, "G3": 177, "G4": 175, "G5": 176}

# tag -> (well, depth_label)
TAGS = [
    ("g1",     "G1", "100x"),
    ("g2",     "G2", "100x"),
    ("g3",     "G3", "100x"),
    ("g4",     "G4", "100x"),
    ("g5",     "G5", "100x"),
    ("d30_g1", "G1", "30x"),
    ("d30_g2", "G2", "30x"),
    ("d30_g3", "G3", "30x"),
    ("d30_g4", "G4", "30x"),
    ("d30_g5", "G5", "30x"),
]

# Directory holding {tag}/consensus.fasta from the medaka runs. The original
# run directory was a local scratch folder that no longer exists.
BASE = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("MEDAKA_TEST_DIR", "medaka_test")

def read_fasta_seq(path):
    lines = []
    with open(path) as f:
        for line in f:
            if not line.startswith(">"):
                lines.append(line.strip())
    return "".join(lines)

print("tag\twell\tdepth\tmedaka_ed\ttruth_alen\tconsensus_len\tlen_match")
for tag, well, depth in TAGS:
    fasta = f"{BASE}/{tag}/consensus.fasta"
    try:
        seq = read_fasta_seq(fasta)
    except FileNotFoundError:
        print(f"{tag}\t{well}\t{depth}\tFAIL\t{TRUTH_ALEN[well]}\tNA\tNA")
        continue
    truth = TRUTHS[well]
    result = edlib.align(seq, truth, mode="HW", task="distance")
    ed = result["editDistance"]
    clen = len(seq)
    alen = TRUTH_ALEN[well]
    len_match = "Y" if clen == alen else "N"
    print(f"{tag}\t{well}\t{depth}\t{ed}\t{alen}\t{clen}\t{len_match}")
