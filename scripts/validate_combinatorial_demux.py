# ruff: noqa: T201
"""Integration validation: run_combinatorial_demux against barcode06 real data.

Usage:
    python3 scripts/validate_combinatorial_demux.py [--ngs-root PATH]

Compares output well read counts against reference sort output.

Default paths assume WSL2 workspace layout. Override via env vars:
    NGS_ROOT   -- parent dir of the nanopore_NGS project folder
    DEMUX_OUT  -- output directory for test run (default: /tmp/demux_test_out)
"""

from __future__ import annotations

import os
import sys
import tempfile as _tempfile
from pathlib import Path

# Add repo root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from kuma_core.mame.ingest.combinatorial_demux import run_combinatorial_demux
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

# ---------------------------------------------------------------------------
# Path resolution (env-var overrideable, no hardcoded absolute paths)
# ---------------------------------------------------------------------------

_WORKSPACE = Path(os.environ.get("WORKSPACE_ROOT", Path.home() / "_workspace"))
_NGS_ROOT = Path(os.environ.get("NGS_ROOT", _WORKSPACE / "020.admin/projects/060.nanopore_NGS"))
_DEMUX_OUT = Path(os.environ.get("DEMUX_OUT", Path(_tempfile.gettempdir()) / "demux_test_out"))

FASTQ_DIR = _NGS_ROOT / "20260212_2227_X4_FBF10847_e7145f8e/fastq_pass/barcode06"
BARCODES_XLSX = _NGS_ROOT / "barcodes sequence.xlsx"
REFERENCE_OUTPUT_DIR = _NGS_ROOT / "NGS_260212/sort_barcode06"
OUTPUT_DIR = _DEMUX_OUT / "sort_barcode06"

_PROJECTS_ROOT = Path(os.environ.get("WORKSPACE_ROOT", Path.home() / "_workspace")) / "020.admin/projects"
GENBANK_PATH = _PROJECTS_ROOT / "030.EvolveProprimer/pTSN-PtIspS-idi(KanR)_corrected.gb"


def extract_isps_reference(dest: Path) -> Path:
    """Extract sispS CDS from GenBank file and write to FASTA."""
    if dest.exists():
        return dest
    from Bio import SeqIO
    gb = SeqIO.read(str(GENBANK_PATH), "genbank")
    # sispS(P.t) CDS at positions 267..1950 (verified from GenBank annotation)
    seq = gb.seq[267:1950]
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w") as fh:
        fh.write(f">sispS_PtIspS\n{seq}\n")
    print(f"[ref] Written {len(seq)} bp to {dest}")
    return dest


def count_reads_in_fasta(fasta_path: Path) -> int:
    """Count sequences in a FASTA file."""
    n = 0
    with fasta_path.open() as fh:
        for line in fh:
            if line.startswith(">"):
                n += 1
    return n


def main() -> None:
    # Validate input paths
    missing = [p for p in [FASTQ_DIR, BARCODES_XLSX, GENBANK_PATH] if not p.exists()]
    if missing:
        for p in missing:
            print(f"ERROR: Not found: {p}", file=sys.stderr)
        sys.exit(1)

    # Prepare reference
    ref_fasta = OUTPUT_DIR / "reference" / "sispS.fasta"
    ref_fasta = extract_isps_reference(ref_fasta)

    # Collect all fastq.gz files
    fastq_paths = sorted(FASTQ_DIR.glob("*.fastq.gz"))
    if not fastq_paths:
        print(f"ERROR: No fastq.gz files found in {FASTQ_DIR}", file=sys.stderr)
        sys.exit(1)
    print(f"[input] {len(fastq_paths)} fastq.gz files")

    # Run pipeline
    result = run_combinatorial_demux(
        raw_fastq_paths=fastq_paths,
        reference_fasta=ref_fasta,
        barcodes_xlsx=BARCODES_XLSX,
        output_dir=OUTPUT_DIR,
        mapq_threshold=25,
        coverage_fraction=0.98,
        trim_flank_bp=30,
        min_depth=3,
    )

    stats = result.stats
    print("\n=== Pipeline stats ===")
    print(f"Total reads:          {stats.total_reads:>8}")
    print(f"Passed MAPQ+coverage: {stats.passed_coverage:>8}  ({100*stats.passed_coverage/max(1,stats.total_reads):.1f}%)")
    print(f"Barcode assigned:     {stats.assigned_reads:>8}  ({100*stats.assigned_reads/max(1,stats.passed_coverage):.1f}% of filtered)")
    print(f"Wells with >=1 read:  {stats.wells_with_reads:>8} / 96")
    print(f"Wells with >=3 reads: {stats.wells_with_min_reads:>8} / 96")
    print(f"Chimera splits:       {stats.chimera_splits:>8}")

    # Compare against reference sort output
    sample_wells = ["1_1", "1_2", "8_12", "3_5", "5_8"]
    print("\n=== Well-by-well comparison (sample) ===")
    print(f"{'Well':<8} {'Ours':>8} {'Ref':>8} {'Ratio':>8}")
    print("-" * 36)

    for well in sample_wells:
        our_reads = len(result.per_well_reads.get(well, []))
        ref_fasta_well = REFERENCE_OUTPUT_DIR / f"{well}.fasta"
        ref_reads = count_reads_in_fasta(ref_fasta_well) if ref_fasta_well.exists() else 0
        ratio = our_reads / ref_reads if ref_reads > 0 else float("inf")
        flag = " OK" if 0.5 <= ratio <= 2.0 else " WARN"
        print(f"{well:<8} {our_reads:>8} {ref_reads:>8} {ratio:>8.2f}{flag}")

    wells_10 = sum(1 for reads in result.per_well_reads.values() if len(reads) >= 10)
    print(f"\n[goal] Wells with >=10 reads: {wells_10} / 96 (target: >=80)")

    if result.per_well_reads:
        print("\n=== Top 20 wells by read count ===")
        rows = sorted(
            [(w, len(r)) for w, r in result.per_well_reads.items()],
            key=lambda x: (-x[1], x[0]),
        )
        for well, cnt in rows[:20]:
            print(f"  {well}: {cnt}")
        if len(rows) > 20:
            print(f"  ... ({len(rows)-20} more wells)")


if __name__ == "__main__":
    main()
