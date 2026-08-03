# ruff: noqa: T201
"""Integration validation: run_combinatorial_demux against user-supplied data.

Usage::

    python3 scripts/validate_combinatorial_demux.py \\
        --fastq-dir /path/to/fastq_pass/barcode06 \\
        --barcodes-xlsx /path/to/barcodes_sequence.xlsx \\
        --genbank /path/to/construct.gb

Optional flags::

    --output-dir PATH            # default: fresh subdirectory under system temp
    --reference-output-dir PATH  # enables well-by-well comparison
    --cds-gene GENE_NAME         # select CDS by 'gene' qualifier
    --cds-locus-tag LOCUS_TAG    # select CDS by 'locus_tag' qualifier
    # When neither --cds-gene nor --cds-locus-tag is given, the GenBank record
    # must contain exactly one CDS or the script exits with a diagnostic listing
    # all candidates.

All dataset-specific paths are supplied as arguments; no workspace or project
paths are embedded in this script.
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
import tempfile
from pathlib import Path

# Add repo root to sys.path so the script is runnable directly from the repo root.
sys.path.insert(0, str(Path(__file__).parent.parent))

from kuma_core.mame.ingest.combinatorial_demux import run_combinatorial_demux

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


# ---------------------------------------------------------------------------
# CDS selection
# ---------------------------------------------------------------------------


def _cds_label(feature) -> str:
    """Return a filename-safe label (gene > locus_tag > product > 'cds')."""
    raw_label = "cds"
    for qualifier in ("gene", "locus_tag", "product"):
        values = feature.qualifiers.get(qualifier)
        if values and values[0].strip():
            raw_label = values[0].strip()
            break
    label = re.sub(r"[^A-Za-z0-9._-]+", "_", raw_label).strip("._-")
    return label or "cds"


def _format_candidates(cds_features) -> str:
    lines: list[str] = []
    for f in cds_features:
        gene = f.qualifiers.get("gene", ["-"])[0]
        locus_tag = f.qualifiers.get("locus_tag", ["-"])[0]
        product = f.qualifiers.get("product", ["-"])[0]
        location = str(f.location)
        lines.append(
            f"  gene={gene!r} locus_tag={locus_tag!r} "
            f"product={product!r} location={location}"
        )
    return "\n".join(lines) or "  (none)"


def select_cds(record, *, gene: str | None = None, locus_tag: str | None = None):
    """Return the matching CDS ``SeqFeature`` from *record*.

    When both selectors are supplied, both must match the same feature. When
    neither is given, succeeds only when the record contains exactly one CDS.

    Exits with a descriptive message listing all candidates on any failure so
    that ambiguous or missing selectors are never silent.
    """
    cds_features = [f for f in record.features if f.type == "CDS"]

    if gene is not None or locus_tag is not None:
        matches = cds_features
        selectors: list[str] = []
        if gene is not None:
            matches = [
                f for f in matches if gene in f.qualifiers.get("gene", [])
            ]
            selectors.append(f"gene={gene!r}")
        if locus_tag is not None:
            matches = [
                f
                for f in matches
                if locus_tag in f.qualifiers.get("locus_tag", [])
            ]
            selectors.append(f"locus_tag={locus_tag!r}")

        selector_text = " and ".join(selectors)
        if len(matches) == 1:
            return matches[0]

        print(
            f"ERROR: {len(matches)} CDS features match {selector_text} "
            f"in record {record.id!r}.\n"
            f"Available CDS features:\n{_format_candidates(cds_features)}",
            file=sys.stderr,
        )
        sys.exit(1)

    # No selector supplied — require exactly one CDS.
    if len(cds_features) == 1:
        return cds_features[0]

    print(
        f"ERROR: Record {record.id!r} contains {len(cds_features)} CDS features; "
        f"select one with --cds-gene or --cds-locus-tag.\n"
        f"Candidates:\n{_format_candidates(cds_features)}",
        file=sys.stderr,
    )
    sys.exit(1)


# ---------------------------------------------------------------------------
# Reference FASTA extraction
# ---------------------------------------------------------------------------


def extract_cds_reference(
    genbank_path: Path,
    dest_dir: Path,
    *,
    gene: str | None = None,
    locus_tag: str | None = None,
) -> Path:
    """Extract the selected CDS from *genbank_path* and write a FASTA to *dest_dir*.

    The output filename is derived from the CDS annotation (``gene`` qualifier,
    then ``locus_tag``, then ``product``, then ``"cds"``). Strand is preserved
    via ``feature.extract()``. Returns the FASTA path.
    """
    from Bio import SeqIO

    record = SeqIO.read(str(genbank_path), "genbank")
    feature = select_cds(record, gene=gene, locus_tag=locus_tag)
    label = _cds_label(feature)
    dest = dest_dir / f"{label}.fasta"

    seq = feature.extract(record).seq
    dest_dir.mkdir(parents=True, exist_ok=True)
    with dest.open("w") as fh:
        fh.write(f">{label}\n{seq}\n")
    print(f"[ref] Written {len(seq)} bp to {dest}")
    return dest


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def count_reads_in_fasta(fasta_path: Path) -> int:
    """Count sequences (header lines) in a FASTA file."""
    n = 0
    with fasta_path.open() as fh:
        for line in fh:
            if line.startswith(">"):
                n += 1
    return n


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--fastq-dir",
        required=True,
        metavar="PATH",
        help="Directory containing *.fastq.gz files to demultiplex.",
    )
    p.add_argument(
        "--barcodes-xlsx",
        required=True,
        metavar="PATH",
        help="Barcode workbook (.xlsx) mapping barcodes to wells.",
    )
    p.add_argument(
        "--genbank",
        required=True,
        metavar="PATH",
        help="GenBank file (.gb) for CDS reference extraction.",
    )
    p.add_argument(
        "--output-dir",
        default=None,
        metavar="PATH",
        help=(
            "Directory for demux output.  "
            "Defaults to a fresh subdirectory under the system temp directory."
        ),
    )
    p.add_argument(
        "--reference-output-dir",
        default=None,
        metavar="PATH",
        help=(
            "Directory of reference sorted-FASTA outputs.  "
            "When supplied, well read counts are compared against the "
            "*.fasta files present in this directory."
        ),
    )
    p.add_argument(
        "--cds-gene",
        default=None,
        metavar="GENE",
        help="Select the CDS feature whose 'gene' qualifier matches GENE.",
    )
    p.add_argument(
        "--cds-locus-tag",
        default=None,
        metavar="TAG",
        help="Select the CDS feature whose 'locus_tag' qualifier matches TAG.",
    )
    return p


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    fastq_dir = Path(args.fastq_dir)
    barcodes_xlsx = Path(args.barcodes_xlsx)
    genbank_path = Path(args.genbank)
    reference_output_dir = (
        Path(args.reference_output_dir) if args.reference_output_dir else None
    )

    # Validate required inputs exist.
    missing = [
        path
        for path in (fastq_dir, barcodes_xlsx, genbank_path)
        if not path.exists()
    ]
    if missing:
        for p in missing:
            print(f"ERROR: Not found: {p}", file=sys.stderr)
        sys.exit(1)
    if reference_output_dir is not None and not reference_output_dir.exists():
        print(
            f"ERROR: Reference output dir not found: {reference_output_dir}",
            file=sys.stderr,
        )
        sys.exit(1)

    # Resolve output directory.
    if args.output_dir is not None:
        output_dir = Path(args.output_dir)
    else:
        output_dir = Path(tempfile.mkdtemp(prefix="demux_validate_"))
        print(f"[output] Using temp directory: {output_dir}")

    # Extract CDS reference FASTA; filename derived from annotation.
    ref_fasta = extract_cds_reference(
        genbank_path,
        output_dir / "reference",
        gene=args.cds_gene,
        locus_tag=args.cds_locus_tag,
    )

    # Collect FASTQ inputs.
    fastq_paths = sorted(fastq_dir.glob("*.fastq.gz"))
    if not fastq_paths:
        print(f"ERROR: No fastq.gz files found in {fastq_dir}", file=sys.stderr)
        sys.exit(1)
    print(f"[input] {len(fastq_paths)} fastq.gz files")

    # Run pipeline.
    result = run_combinatorial_demux(
        raw_fastq_paths=fastq_paths,
        reference_fasta=ref_fasta,
        barcodes_xlsx=barcodes_xlsx,
        output_dir=output_dir,
        mapq_threshold=25,
        coverage_fraction=0.98,
        trim_flank_bp=30,
        min_depth=3,
    )

    stats = result.stats
    print("\n=== Pipeline stats ===")
    print(f"Total reads:          {stats.total_reads:>8}")
    print(
        f"Passed MAPQ+coverage: {stats.passed_coverage:>8}  "
        f"({100*stats.passed_coverage/max(1,stats.total_reads):.1f}%)"
    )
    print(
        f"Barcode assigned:     {stats.assigned_reads:>8}  "
        f"({100*stats.assigned_reads/max(1,stats.passed_coverage):.1f}% of filtered)"
    )
    print(f"Wells with >=1 read:  {stats.wells_with_reads:>8} / 96")
    print(f"Wells with >=3 reads: {stats.wells_with_min_reads:>8} / 96")
    print(f"Chimera splits:       {stats.chimera_splits:>8}")

    # Optional well-by-well comparison against reference output directory.
    if reference_output_dir is not None:
        ref_well_fastas = sorted(reference_output_dir.glob("*.fasta"))
        if not ref_well_fastas:
            print(
                f"\n[warn] No .fasta files found in reference dir {reference_output_dir}"
            )
        else:
            wells_to_compare = [f.stem for f in ref_well_fastas]
            print(
                f"\n=== Well-by-well comparison ({len(wells_to_compare)} wells from reference) ==="
            )
            print(f"{'Well':<8} {'Ours':>8} {'Ref':>8} {'Ratio':>8}")
            print("-" * 36)
            for well in sorted(wells_to_compare):
                our_reads = result.per_well_read_counts.get(well, 0)
                ref_well_path = reference_output_dir / f"{well}.fasta"
                ref_reads = count_reads_in_fasta(ref_well_path)
                ratio = our_reads / ref_reads if ref_reads > 0 else float("inf")
                flag = " OK" if 0.5 <= ratio <= 2.0 else " WARN"
                print(f"{well:<8} {our_reads:>8} {ref_reads:>8} {ratio:>8.2f}{flag}")

    wells_10 = sum(1 for n in result.per_well_read_counts.values() if n >= 10)
    print(f"\n[goal] Wells with >=10 reads: {wells_10} / 96 (target: >=80)")

    if result.per_well_read_counts:
        print("\n=== Top 20 wells by read count ===")
        rows = sorted(
            list(result.per_well_read_counts.items()),
            key=lambda x: (-x[1], x[0]),
        )
        for well, cnt in rows[:20]:
            print(f"  {well}: {cnt}")
        if len(rows) > 20:
            print(f"  ... ({len(rows)-20} more wells)")


if __name__ == "__main__":
    main()
