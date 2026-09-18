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


def _parse_organism(value: str) -> str:
    """Resolve only a registered host, never an arbitrary resource path."""
    from .codon_table import CodonTableRegistry, resolve_organism_key

    registry = CodonTableRegistry()
    key = resolve_organism_key(value) or value.strip().lower()
    available = registry.list_organisms()
    if key not in available:
        raise argparse.ArgumentTypeError(
            f"Unknown organism {value!r}; choose one of {', '.join(available)}"
        )
    try:
        registry.get_codon_table(key)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc
    return key


def cmd_design(args: argparse.Namespace) -> None:
    """Run design, retaining partial successes and a machine-readable summary."""
    import json

    from kuma_core.shared.atomic_write import atomic_write_text
    from .sdm_engine import design_sdm_primers, export_results_tsv
    from .plate_mapper import deduplicate_reverse, export_plate_excel, generate_plate_map

    # Validate before creating any output. Keep programmatic Namespace callers
    # compatible with the historical command, which had no organism attribute.
    organism = _parse_organism(getattr(args, "organism", "ecoli"))
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "design_summary.json"
    parameter_names = (
        "fasta", "target_start", "mutations", "polymerase", "overlap",
        "codon_strategy", "tm_fwd_target", "tm_rev_target", "tm_overlap_target",
        "gc_min", "gc_max", "fwd_len_min", "fwd_len_max", "rev_len_min",
        "rev_len_max", "overlap_mode",
    )
    requested = {name: getattr(args, name) for name in parameter_names}
    # Namespace callers may supply Path objects, unlike argparse's str values.
    requested = {name: str(value) if isinstance(value, Path) else value
                 for name, value in requested.items()}
    report: dict[str, object] = {
        "schema_version": 1, "status": "running", "organism": organism,
        "requested_parameters": requested, "designed_count": 0,
        "failed_count": 0, "tm_condition_met_count": 0,
        "successful_mutations": [], "failed_reasons": {}, "artifacts": {},
    }

    def save_report() -> None:
        atomic_write_text(summary_path, json.dumps(
            report, indent=2, ensure_ascii=False, allow_nan=False,
        ) + "\n")

    # Replace a prior completion report before starting a new run. A crash can
    # leave running/error, but must not leave the previous run's complete label.
    save_report()
    try:
        results, _, failures = design_sdm_primers(
            fasta_path=Path(args.fasta), target_start=args.target_start,
            mutations_csv=Path(args.mutations), polymerase=args.polymerase,
            overlap_len=args.overlap, codon_strategy=args.codon_strategy,
            tm_fwd_target=args.tm_fwd_target, tm_rev_target=args.tm_rev_target,
            tm_overlap_target=args.tm_overlap_target, gc_min=args.gc_min,
            gc_max=args.gc_max, fwd_len_min=args.fwd_len_min,
            fwd_len_max=args.fwd_len_max, rev_len_min=args.rev_len_min,
            rev_len_max=args.rev_len_max, overlap_mode=args.overlap_mode,
            organism=organism,
        )
        total = len(results)
        tm_ok = sum(1 for result in results if result.tm_condition_met)
        report.update({
            "designed_count": total, "failed_count": len(failures),
            "tm_condition_met_count": tm_ok,
            "successful_mutations": [result.mutation.raw for result in results],
            "failed_reasons": dict(failures),
        })
        if results:
            tsv_path = output_dir / "sdm_primers.tsv"
            export_results_tsv(results, tsv_path, overlap_mode=args.overlap_mode)
            rev_groups = deduplicate_reverse(results)
            fwd_map, rev_map = generate_plate_map(results, deduplicate_rev=True)
            xlsx_path = output_dir / "plate_mapping.xlsx"
            export_plate_excel(fwd_map + rev_map, xlsx_path,
                               rev_groups=rev_groups, results=results)
            report["artifacts"] = {"primers": str(tsv_path), "plate_map": str(xlsx_path)}
            report["status"] = "partial" if failures else "complete"
        else:
            report["status"] = "failed"
        save_report()
    except Exception as exc:
        report.update({"status": "error", "error": str(exc), "artifacts": {}})
        try:
            save_report()
        except OSError:
            logging.exception("Could not persist the failed-run summary")
        raise

    print(f"\n{'='*60}")
    print("KURO Design Summary")
    print(f"{'='*60}")
    print(f"Host organism:         {organism}")
    print(f"Mutations designed:    {total}")
    print(f"Mutations failed:      {len(failures)}")
    print(f"Tm condition met:      {tm_ok}/{total}")
    print(f"Output directory:      {output_dir}")
    print(f"Execution summary:     {summary_path}")
    for mutation, reason in sorted(failures.items()):
        print(f"  FAILED {mutation}: {reason}")
    print(f"{'='*60}")
    if not results:
        logging.error("No primers designed. Check input files and parameters.")
        raise SystemExit(1)
    # Opt-in strict mode leaves the historical partial-success exit behavior
    # intact while allowing batch users to require every requested design.
    if failures and getattr(args, "fail_on_partial", False):
        raise SystemExit(2)


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


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser without reading process arguments."""
    parser = argparse.ArgumentParser(
        prog="kuro",
        description="KURO - EVOLVEpro SDM primer batch design tool",
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
        "--fasta", required=True, help="Annotated GenBank or SnapGene template (legacy option name)"
    )
    design_parser.add_argument(
        "--target-start", type=int, required=True,
        help="0-based position of CDS start codon (ATG)"
    )
    design_parser.add_argument(
        "--mutations", required=True, help="CSV file with 'mutation' column"
    )
    design_parser.add_argument(
        "--organism", "--host-organism", type=_parse_organism, default="ecoli",
        help="Registered host codon table or supported alias (default: ecoli)"
    )
    design_parser.add_argument(
        "--fail-on-partial", action="store_true",
        help="Exit 2 after exporting partial successes when any mutation failed"
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

    return parser


def main() -> None:
    """Main CLI entry point."""
    args = build_parser().parse_args()
    _setup_logging(args.verbose)

    if args.command == "design":
        cmd_design(args)
    elif args.command == "plate-map":
        cmd_plate_map(args)


if __name__ == "__main__":
    main()
