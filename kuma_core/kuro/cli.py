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

    if getattr(args, "method", "overlap") == "goldengate":
        _cmd_design_goldengate(args, output_dir)
        return

    results, _, _failures = design_sdm_primers(
        fasta_path=Path(args.fasta),
        target_start=args.target_start,
        mutations_csv=Path(args.mutations),
        polymerase=args.polymerase,
        overlap_len=args.overlap,
        codon_strategy=args.codon_strategy,
        tm_fwd_target=args.tm_fwd_target,
        tm_rev_target=args.tm_rev_target,
        tm_overlap_target=args.tm_overlap_target,
        gc_min=args.gc_min,
        gc_max=args.gc_max,
        fwd_len_min=args.fwd_len_min,
        fwd_len_max=args.fwd_len_max,
        rev_len_min=args.rev_len_min,
        rev_len_max=args.rev_len_max,
        overlap_mode=args.overlap_mode,
    )

    if not results:
        logging.error("No primers designed. Check input files and parameters.")
        sys.exit(1)

    # Export TSV
    tsv_path = output_dir / "sdm_primers.tsv"
    export_results_tsv(results, tsv_path, overlap_mode=args.overlap_mode)
    logging.info("Primer results saved to %s", tsv_path)

    # Export plate map
    from .plate_mapper import deduplicate_reverse
    rev_groups = deduplicate_reverse(results)
    fwd_map, rev_map = generate_plate_map(results, deduplicate_rev=True)
    xlsx_path = output_dir / "plate_mapping.xlsx"
    export_plate_excel(
        fwd_map + rev_map, xlsx_path,
        rev_groups=rev_groups,
        results=results,
    )
    logging.info("Plate mapping saved to %s", xlsx_path)

    # Summary
    total = len(results)
    tm_ok = sum(1 for r in results if r.tm_condition_met)
    print(f"\n{'='*60}")
    print("KURO Design Summary")
    print(f"{'='*60}")
    print(f"Mutations designed:    {total}")
    print(f"Tm condition met:      {tm_ok}/{total}")
    print(f"Output directory:      {output_dir}")
    print(f"{'='*60}")


def _cmd_design_goldengate(args: argparse.Namespace, output_dir: Path) -> None:
    """Golden Gate (Type IIS) primer design path for the CLI."""
    import csv

    from .goldengate import (
        design_goldengate_batch,
        export_goldengate_tsv,
        extract_cds,
        translate_dna,
    )
    from .sdm_engine import load_sequence

    _header, sequence, _genes = load_sequence(Path(args.fasta))
    cds = extract_cds(sequence, args.target_start)
    protein = translate_dna(cds)

    mutations: list[str] = []
    with open(args.mutations, encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        col = "mutation" if reader.fieldnames and "mutation" in reader.fieldnames else "variant"
        for row in reader:
            value = (row.get(col) or "").strip()
            if value:
                mutations.append(value)

    forbidden_overhangs = None
    if getattr(args, "forbidden_overhangs", None):
        forbidden_overhangs = [s.strip().upper() for s in args.forbidden_overhangs.replace(",", " ").split() if s.strip()]
    results, failed = design_goldengate_batch(
        cds, protein, mutations,
        enzyme=args.enzyme,
        organism=getattr(args, "organism", "ecoli"),
        prefix_override=getattr(args, "prefix_override", None),
        forbidden_overhangs=forbidden_overhangs,
    )
    if not results:
        logging.error("No Golden Gate primers designed. Failures: %s", failed)
        sys.exit(1)

    tsv_path = output_dir / "goldengate_primers.tsv"
    export_goldengate_tsv(results, tsv_path, enzyme=args.enzyme)
    logging.info("Golden Gate primer results saved to %s", tsv_path)

    print(f"\n{'='*60}")
    print("KURO Golden Gate Design Summary")
    print(f"{'='*60}")
    print(f"Enzyme:                {args.enzyme}")
    print(f"Mutations designed:    {len(results)}")
    print(f"Failed:                {len(failed)}")
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
                tm_condition_met=row.get("Tm_Condition_Met", "YES") == "YES",
            )
            results.append(r)

    rev_groups = deduplicate_reverse(results)
    fwd_map, rev_map = generate_plate_map(results, deduplicate_rev=True)
    output_path = Path(args.output)
    export_plate_excel(fwd_map + rev_map, output_path, rev_groups=rev_groups)
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
        "--overlap", type=int, default=None,
        help="Overlap window length in bp (default: polymerase profile, slide spec 18)"
    )
    design_parser.add_argument(
        "--output", default="results/",
        help="Output directory (default: results/)"
    )
    design_parser.add_argument(
        "--codon-strategy", default="closest",
        choices=["closest", "optimal"],
        help="Codon selection strategy (default: closest)"
    )
    design_parser.add_argument(
        "--overlap-mode", default="partial",
        choices=["partial", "full"],
        help="Design strategy: partial (Gibson, fwd/rev independent) or full (Q5 SDM, rev=rc(fwd)). Default: partial."
    )
    design_parser.add_argument(
        "--tm-fwd-target", type=float, default=None,
        help="Forward primer Tm target in C (default: polymerase default)"
    )
    design_parser.add_argument(
        "--tm-rev-target", type=float, default=None,
        help="Reverse primer Tm target in C (default: polymerase default)"
    )
    design_parser.add_argument(
        "--tm-overlap-target", type=float, default=None,
        help="Overlap Tm target in C (default: polymerase default)"
    )
    design_parser.add_argument(
        "--gc-min", type=float, default=40,
        help="Minimum GC%% for primers (default: 40)"
    )
    design_parser.add_argument(
        "--gc-max", type=float, default=60,
        help="Maximum GC%% for primers (default: 60)"
    )
    design_parser.add_argument(
        "--fwd-len-min", type=int, default=None,
        help="Minimum forward primer length (default: polymerase profile, slide spec 17)"
    )
    design_parser.add_argument(
        "--fwd-len-max", type=int, default=None,
        help="Maximum forward primer length (default: polymerase profile, slide spec 39)"
    )
    design_parser.add_argument(
        "--rev-len-min", type=int, default=None,
        help="Minimum reverse primer length (default: polymerase profile, slide spec 19)"
    )
    design_parser.add_argument(
        "--rev-len-max", type=int, default=None,
        help="Maximum reverse primer length (default: polymerase profile, slide spec 27)"
    )
    design_parser.add_argument(
        "--method", default="overlap", choices=["overlap", "goldengate"],
        help="Design method: overlap-extension (default) or goldengate (Type IIS)"
    )
    design_parser.add_argument(
        "--enzyme", default="BsaI",
        help="Type IIS enzyme for Golden Gate design (default: BsaI)"
    )
    design_parser.add_argument(
        "--organism", default="ecoli",
        help="Organism codon table for Golden Gate codon selection (default: ecoli)"
    )
    design_parser.add_argument(
        "--prefix-override", default=None,
        help="Golden Gate: override the junction prefix (default: enzyme catalog prefix)"
    )
    design_parser.add_argument(
        "--forbidden-overhangs", default=None,
        help="Golden Gate: comma/space-separated overhangs to exclude (default: AATG,AGGT)"
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
