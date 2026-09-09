#!/usr/bin/env python3
"""Build a KURO codon usage table from an NCBI RefSeq CDS FASTA.

Reads a ``*_cds_from_genomic.fna[.gz]`` file, counts codons per amino acid, and
writes the JSON shape that ``kuma_core/kuro/codon_table.py`` already loads:

    {"name": str, "taxid": int, "source": str, "codons": {"<AA>": [["CODON", fraction], ...]}}

Provenance fields ("assembly", "strain", "n_cds", "transl_table",
"source_release") are added alongside those four. The four original keys keep
their names and meanings, so every existing reader keeps working.

Counting rules
--------------
* Every codon of an accepted CDS is counted by its own identity through the
  genetic code forward table, including the initiator codon and the terminator.
  A GTG or TTG start therefore counts as Val or Leu, not as Met. This is the
  convention Kazusa and CoCoPUTs use, and it is why translation table 11 gives
  the same result as table 1 here: the two tables differ only in which codons
  are permitted as a START, never in amino acid assignment (verify with
  ``unambiguous_dna_by_id[1].forward_table == unambiguous_dna_by_id[11].forward_table``).
* A CDS record is dropped when its header carries ``[pseudo=true]`` or
  ``[partial=``, when its length is not a multiple of three, or when it contains
  any character outside ACGT (ambiguity codes included). Drop counts are printed
  per reason.
* All 64 codons are always emitted, taken from the genetic code rather than from
  the observed data, so a codon that never occurs appears with fraction 0.00 and
  the table stays complete for callers that build a codon-to-amino-acid map from
  it.

Rounding
--------
Fractions are rounded to 2 decimals, so an amino acid group need not sum to
exactly 1.00. The tables already shipped in this repository have the same
property: hsapiens.json Ser sums to 0.97 and ecoli.json Gly sums to 1.01.
Rounding is presentational and is applied after ordering, so a group whose two
leading codons round to the same value is still listed with the genuinely more
frequent one first.

Determinism
-----------
Amino acids are emitted in the fixed order used by the existing ecoli.json
(alphabetical by three letter code, stop last). Within an amino acid, codons are
sorted by descending fraction, then by codon string ascending. Two runs over the
same input produce byte identical output.

Usage
-----
    python3 scripts/build_codon_table.py <cds.fna.gz> \
        --name "Bacillus subtilis subsp. subtilis str. 168" \
        --taxid 224308 --strain 168 --assembly GCF_000009045.1_ASM904v1 \
        --transl-table 11 --source "NCBI RefSeq" --source-release 2021-02-12 \
        --out kuma_core/kuro/resources/codon_tables/bsubtilis.json

Depends only on the standard library and ``Bio.Data.CodonTable``.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Iterator

from Bio.Data.CodonTable import unambiguous_dna_by_id

# Amino acid order of the existing shipped tables: alphabetical by three letter
# code, with the stop group last.
AA_ORDER: list[str] = [
    "A", "R", "N", "D", "C", "Q", "E", "G", "H", "I",
    "L", "K", "M", "F", "P", "S", "T", "W", "Y", "V", "*",
]

_ACGT = frozenset("ACGT")


def _open_text(path: Path):
    """Open a FASTA that may be gzipped, decided by magic bytes not by suffix."""
    with open(path, "rb") as probe:
        magic = probe.read(2)
    if magic == b"\x1f\x8b":
        return gzip.open(path, "rt")
    return open(path, "rt")


def iter_fasta(path: Path) -> Iterator[tuple[str, str]]:
    """Yield (header, sequence) for each record. Header excludes the '>'."""
    header: str | None = None
    chunks: list[str] = []
    with _open_text(path) as handle:
        for line in handle:
            line = line.rstrip("\n").rstrip("\r")
            if line.startswith(">"):
                if header is not None:
                    yield header, "".join(chunks)
                header = line[1:]
                chunks = []
            elif line:
                chunks.append(line)
    if header is not None:
        yield header, "".join(chunks)


def codon_to_aa(transl_table: int) -> dict[str, str]:
    """Map all 64 codons to a one letter amino acid, stops as '*'."""
    table = unambiguous_dna_by_id[transl_table]
    mapping = dict(table.forward_table)
    for stop in table.stop_codons:
        mapping[stop] = "*"
    if len(mapping) != 64:
        raise SystemExit(
            f"translation table {transl_table} yielded {len(mapping)} codons, expected 64"
        )
    return mapping


def count_codons(path: Path, mapping: dict[str, str]) -> tuple[Counter, dict[str, int]]:
    """Count codons over accepted CDS records. Returns (counts, statistics)."""
    counts: Counter = Counter()
    stats = {
        "records": 0,
        "accepted": 0,
        "dropped_pseudo": 0,
        "dropped_partial": 0,
        "dropped_length": 0,
        "dropped_alphabet": 0,
    }
    for header, seq in iter_fasta(path):
        stats["records"] += 1
        if "[pseudo=true]" in header:
            stats["dropped_pseudo"] += 1
            continue
        if "[partial=" in header:
            stats["dropped_partial"] += 1
            continue
        seq = seq.upper()
        if len(seq) == 0 or len(seq) % 3 != 0:
            stats["dropped_length"] += 1
            continue
        if not set(seq) <= _ACGT:
            stats["dropped_alphabet"] += 1
            continue
        stats["accepted"] += 1
        for i in range(0, len(seq), 3):
            counts[seq[i:i + 3]] += 1
    return counts, stats


def build_rows(
    counts: Counter, mapping: dict[str, str]
) -> dict[str, list[tuple[str, float]]]:
    """Group codons by amino acid and turn counts into rounded fractions."""
    by_aa: dict[str, list[str]] = {}
    for codon, aa in mapping.items():
        by_aa.setdefault(aa, []).append(codon)

    missing = sorted(set(by_aa) - set(AA_ORDER))
    if missing:
        raise SystemExit(f"amino acids absent from AA_ORDER: {missing}")

    rows: dict[str, list[tuple[str, float]]] = {}
    for aa in AA_ORDER:
        codons = by_aa[aa]
        total = sum(counts[c] for c in codons)
        if total == 0:
            raise SystemExit(f"no codons counted for amino acid {aa!r}")
        # Sort on the unrounded fraction so the emitted order can never
        # contradict the counts, and fall back to the codon string for an exact
        # tie. Descending raw order implies descending rounded order, so the
        # rendered numbers still read monotonically.
        ordered = sorted(codons, key=lambda c: (-counts[c] / total, c))
        rows[aa] = [(c, round(counts[c] / total, 2)) for c in ordered]
    return rows


def render(meta: dict, rows: dict[str, list[tuple[str, float]]]) -> str:
    """Render the JSON by hand to match the formatting of the shipped tables."""
    lines = ["{"]
    for key in ("name", "taxid", "source", "assembly", "strain", "n_cds",
                "transl_table", "source_release"):
        lines.append(f"  {json.dumps(key)}: {json.dumps(meta[key])},")
    lines.append('  "codons": {')
    last = len(AA_ORDER) - 1
    for index, aa in enumerate(AA_ORDER):
        body = ", ".join(f'["{c}", {f:.2f}]' for c, f in rows[aa])
        tail = "" if index == last else ","
        lines.append(f"    {json.dumps(aa)}: [{body}]{tail}")
    lines.append("  }")
    lines.append("}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("fasta", type=Path, help="CDS FASTA, plain or gzipped")
    parser.add_argument("--name", required=True, help="organism name as NCBI reports it")
    parser.add_argument("--taxid", required=True, type=int)
    parser.add_argument("--transl-table", required=True, type=int)
    parser.add_argument("--assembly", required=True, help="e.g. GCF_000009045.1_ASM904v1")
    parser.add_argument("--strain", required=True)
    parser.add_argument("--source", required=True, help="e.g. 'NCBI RefSeq'")
    parser.add_argument("--source-release", required=True,
                        help="annotation release date or name")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)

    mapping = codon_to_aa(args.transl_table)
    counts, stats = count_codons(args.fasta, mapping)
    unknown = sorted(set(counts) - set(mapping))
    if unknown:
        raise SystemExit(f"codons outside the genetic code were counted: {unknown}")
    rows = build_rows(counts, mapping)

    meta = {
        "name": args.name,
        "taxid": args.taxid,
        "source": args.source,
        "assembly": args.assembly,
        "strain": args.strain,
        "n_cds": stats["accepted"],
        "transl_table": args.transl_table,
        "source_release": args.source_release,
    }
    text = render(meta, rows)
    json.loads(text)  # fail loudly rather than ship malformed JSON
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")

    total_codons = sum(counts.values())
    print(
        f"{args.out}: {stats['accepted']} CDS accepted of {stats['records']} records, "
        f"{total_codons} codons counted",
        file=sys.stderr,
    )
    print(
        "  dropped: "
        f"pseudo={stats['dropped_pseudo']} "
        f"partial={stats['dropped_partial']} "
        f"length_not_multiple_of_3={stats['dropped_length']} "
        f"non_ACGT={stats['dropped_alphabet']}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
