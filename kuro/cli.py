"""CLI interface for KURO."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def cmd_design(args: argparse.Namespace) -> None:
    """Run the SDM primer design pipeline."""
    from .sdm_engine import design_sdm_primers, export_results_tsv
    from .plate_mapper import export_plate_excel, generate_plate_map

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    results, _ = design_sdm_primers(
        fasta_path=Path(args.fasta),
        target_start=args.target_start,
        mutations_csv=Path(args.mutations),
        polymerase=args.polymerase,
        overlap_len=args.overlap,
    )

    if not results:
        logging.error("No primers designed. Check input files and parameters.")
        sys.exit(1)

    # Export TSV
    tsv_path = output_dir / "sdm_primers.tsv"
    export_results_tsv(results, tsv_path)
    logging.info("Primer results saved to %s", tsv_path)

    # Export plate map
    from .plate_mapper import deduplicate_reverse
    rev_groups = deduplicate_reverse(results)
    plate_mappings = generate_plate_map(results, deduplicate_rev=True)
    xlsx_path = output_dir / "plate_mapping.xlsx"
    export_plate_excel(plate_mappings, xlsx_path, rev_groups=rev_groups)
    logging.info("Plate mapping saved to %s", xlsx_path)

    # Summary
    total = len(results)
    tm_ok = sum(1 for r in results if r.tm_condition_met)
    print(f"\n{'='*60}")
    print(f"KURO Design Summary")
    print(f"{'='*60}")
    print(f"Mutations designed:    {total}")
    print(f"Tm condition met:      {tm_ok}/{total}")
    print(f"Output directory:      {output_dir}")
    print(f"{'='*60}")


def cmd_plate_map(args: argparse.Namespace) -> None:
    """Generate plate mapping from existing primer results."""
    import csv
    from .sdm_engine import SdmPrimerResult
    from .mutation import Mutation
    from .overlap import OverlapWindow
    from .plate_mapper import deduplicate_reverse, export_plate_excel, generate_plate_map

    # Read primer TSV
    results: list[SdmPrimerResult] = []
    with open(args.primers) as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            mut = Mutation(
                raw=row["Mutation"],
                wt_aa=row["Mutation"][0],
                position=int(row["Mutation"][1:-1]),
                mt_aa=row["Mutation"][-1],
                codon_start=0,
                wt_codon=row.get("WT_Codon", ""),
                mt_codon=row.get("MT_Codon", ""),
            )
            window = OverlapWindow(
                sequence=row.get("Overlap_Seq", ""),
                start=0,
                end=0,
                codon_offset=0,
            )
            r = SdmPrimerResult(
                mutation=mut,
                forward_seq=row["Forward_Primer"],
                reverse_seq=row["Reverse_Primer"],
                forward_binding="",
                reverse_binding="",
                overlap_window=window,
                tm_fwd=float(row.get("Tm_Fwd", row.get("Tm_NonOverlap_Fwd", 0))),
                tm_rev=float(row.get("Tm_Rev", row.get("Tm_NonOverlap_Rev", 0))),
                tm_overlap=float(row.get("Tm_Overlap", 0)),
                tm_condition_met=row.get("Tm_Condition_Met", row.get("Off_Target", "")) != "YES",
            )
            results.append(r)

    rev_groups = deduplicate_reverse(results)
    mappings = generate_plate_map(results, deduplicate_rev=True)
    output_path = Path(args.output)
    export_plate_excel(mappings, output_path, rev_groups=rev_groups)
    logging.info("Plate mapping saved to %s", output_path)


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="kuro",
        description="KURO — EVOLVEpro SDM primer batch design tool",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose logging"
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # design subcommand
    design_parser = subparsers.add_parser(
        "design", help="Design SDM primers for a batch of mutations"
    )
    design_parser.add_argument(
        "--fasta", required=True, help="Template FASTA file"
    )
    design_parser.add_argument(
        "--target-start", type=int, required=True,
        help="0-based position of CDS start codon (ATG)"
    )
    design_parser.add_argument(
        "--mutations", required=True, help="CSV file with 'mutation' column"
    )
    design_parser.add_argument(
        "--polymerase", default="Q5",
        help="Polymerase name (default: Q5)"
    )
    design_parser.add_argument(
        "--overlap", type=int, default=20,
        help="Overlap window length in bp (default: 20)"
    )
    design_parser.add_argument(
        "--output", default="results/",
        help="Output directory (default: results/)"
    )

    # plate-map subcommand
    plate_parser = subparsers.add_parser(
        "plate-map", help="Generate plate mapping from primer results"
    )
    plate_parser.add_argument(
        "--primers", required=True, help="Primer TSV file from design step"
    )
    plate_parser.add_argument(
        "--output", default="plate_mapping.xlsx",
        help="Output Excel file (default: plate_mapping.xlsx)"
    )

    args = parser.parse_args()
    _setup_logging(args.verbose)

    if args.command == "design":
        cmd_design(args)
    elif args.command == "plate-map":
        cmd_plate_map(args)


if __name__ == "__main__":
    main()
