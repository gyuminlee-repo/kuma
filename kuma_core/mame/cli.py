"""CLI entry point (argparse-based)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from kuma_core.mame.export import WellMapper, write_excel
from kuma_core.mame.ingest import IngestMode, route_ingest
from kuma_core.mame.models import (
    BarcodeRecord,
    ReplicateResult,
    TranslatedRecord,
    VerdictClass,
    VerdictRecord,
)
from kuma_core.mame.pipeline import run_analyze
from kuma_core.mame.translate import translate_and_diff

_MODE_DEFAULTS = {
    "amplicon": {"min_file_size_kb": 50.0},
    "plasmid": {"min_file_size_kb": 1000.0},
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mame",
        description="NGS screening decision orchestration (Phase 1 MVP).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    analyze = sub.add_parser("analyze", help="Full pipeline -> Excel export")
    analyze.add_argument("--input-dir", type=Path, required=True)
    analyze.add_argument("--reference", type=Path, required=True)
    analyze.add_argument("--expected", type=Path, required=True, help="KURO xlsx path")
    analyze.add_argument("--output", type=Path, default=Path("./output.xlsx"))
    analyze.add_argument("--mode", choices=["amplicon", "plasmid"], default="amplicon")
    analyze.add_argument("--min-file-size", type=float, default=None)
    analyze.add_argument("--min-read-count", type=int, default=30)
    analyze.add_argument("--max-consensus-n-fraction", type=float, default=0.0)
    analyze.add_argument("--many-cutoff", type=int, default=5)
    analyze.add_argument("--cds-start", type=int, default=0)
    analyze.add_argument("--cds-end", type=int, required=True)
    analyze.add_argument(
        "--ingest-mode",
        choices=[m.value for m in IngestMode],
        default=IngestMode.BARCODE.value,
    )

    translate = sub.add_parser("translate", help="Ingest + translate only (JSON dump)")
    translate.add_argument("--input-dir", type=Path, required=True)
    translate.add_argument("--reference", type=Path, required=True)
    translate.add_argument("--cds-start", type=int, default=0)
    translate.add_argument("--cds-end", type=int, required=True)
    translate.add_argument("--output-json", type=Path, required=True)
    translate.add_argument(
        "--ingest-mode",
        choices=[m.value for m in IngestMode],
        default=IngestMode.BARCODE.value,
    )

    export = sub.add_parser("export", help="Regenerate Excel from a verdict JSON dump")
    export.add_argument("--verdict-json", type=Path, required=True)
    export.add_argument("--output", type=Path, required=True)
    export.add_argument("--mode", choices=["amplicon", "plasmid"], default="amplicon")

    return parser


def _cmd_analyze(args: argparse.Namespace) -> int:
    min_kb = args.min_file_size
    if min_kb is None:
        min_kb = _MODE_DEFAULTS[args.mode]["min_file_size_kb"]
    verdicts, replicates = run_analyze(
        input_dir=args.input_dir,
        reference_path=args.reference,
        expected_path=args.expected,
        output_path=args.output,
        cds_start=args.cds_start,
        cds_end=args.cds_end,
        mode=args.mode,
        min_file_size_kb=min_kb,
        min_read_count=args.min_read_count,
        max_consensus_n_fraction=args.max_consensus_n_fraction,
        many_cutoff=args.many_cutoff,
        ingest_mode=IngestMode(args.ingest_mode),
    )
    # Sidecar JSON next to the xlsx so `export` subcommand can reuse it.
    side = args.output.with_suffix(".verdicts.json")
    _dump_verdicts(verdicts, replicates, side)
    print(f"[mame] wrote {args.output}")
    print(f"[mame] wrote {side}")
    return 0


def _cmd_translate(args: argparse.Namespace) -> int:
    from kuma_core.mame.pipeline import _read_reference_fasta  # local import to avoid cycle

    records = route_ingest(args.input_dir, IngestMode(args.ingest_mode))
    reference_seq = _read_reference_fasta(args.reference)
    translated_list: list[TranslatedRecord] = []
    for rec in records:
        translated_list.append(
            translate_and_diff(
                record=rec,
                reference_seq=reference_seq,
                cds_start=args.cds_start,
                cds_end=args.cds_end,
            )
        )
    payload = [
        {
            "native_barcode": t.barcode.native_barcode,
            "custom_barcode": t.barcode.custom_barcode,
            "file_size_kb": t.barcode.file_size_kb,
            "source_path": str(t.barcode.source_path),
            "aa_sequence": t.aa_sequence,
            "observed_nt_changes": t.observed_nt_changes,
            "observed_aa_changes": t.observed_aa_changes,
        }
        for t in translated_list
    ]
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"[mame] wrote {args.output_json}")
    return 0


def _cmd_export(args: argparse.Namespace) -> int:
    verdicts, replicates = _load_verdicts(args.verdict_json)
    write_excel(
        verdict_records=verdicts,
        replicate_results=replicates,
        output_path=args.output,
        mapper=WellMapper(),
        mode="amplicon" if args.mode == "amplicon" else "plasmid",
    )
    print(f"[mame] wrote {args.output}")
    return 0


def _dump_verdicts(
    verdicts: list[VerdictRecord],
    replicates: list[ReplicateResult],
    path: Path,
) -> None:
    payload = {
        "verdicts": [
            {
                "native_barcode": vr.translated.barcode.native_barcode,
                "custom_barcode": vr.translated.barcode.custom_barcode,
                "file_size_kb": vr.translated.barcode.file_size_kb,
                "read_count": vr.translated.barcode.read_count,
                "n_mixed_positions": vr.translated.barcode.n_mixed_positions,
                "max_minor_allele_fraction": (
                    vr.translated.barcode.max_minor_allele_fraction
                ),
                "n_low_depth_positions": (
                    vr.translated.barcode.n_low_depth_positions
                ),
                "consensus_n_fraction": vr.translated.barcode.consensus_n_fraction,
                "n_low_quality_bases": (
                    vr.translated.barcode.n_low_quality_bases
                ),
                "n_input_reads": vr.translated.barcode.n_input_reads,
                "n_aligned_reads": vr.translated.barcode.n_aligned_reads,
                "n_mapq_failed": vr.translated.barcode.n_mapq_failed,
                "n_span_failed": vr.translated.barcode.n_span_failed,
                "source_path": str(vr.translated.barcode.source_path),
                "consensus_seq": vr.translated.barcode.consensus_seq,
                "aa_sequence": vr.translated.aa_sequence,
                "observed_nt_changes": vr.translated.observed_nt_changes,
                "observed_aa_changes": vr.translated.observed_aa_changes,
                "expected_mutations": vr.expected_mutations,
                "verdict": vr.verdict.value,
                "verdict_notes": vr.verdict_notes,
            }
            for vr in verdicts
        ],
        "replicates": [
            {
                "mutant_id": rr.mutant_id,
                "selected_plate": rr.selected_plate,
                "selection_reason": rr.selection_reason,
                "failed": rr.failed,
                "plate_keys": list(rr.plate_verdicts.keys()),
            }
            for rr in replicates
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _load_verdicts(path: Path) -> tuple[list[VerdictRecord], list[ReplicateResult]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    verdicts: list[VerdictRecord] = []
    by_key: dict[tuple[str, str], VerdictRecord] = {}
    for item in data["verdicts"]:
        barcode = BarcodeRecord(
            native_barcode=item["native_barcode"],
            custom_barcode=item["custom_barcode"],
            consensus_seq=item["consensus_seq"],
            file_size_kb=item["file_size_kb"],
            source_path=Path(item["source_path"]),
            read_count=item.get("read_count"),
            n_mixed_positions=int(item.get("n_mixed_positions", 0)),
            max_minor_allele_fraction=float(
                item.get("max_minor_allele_fraction", 0.0)
            ),
            n_low_depth_positions=int(item.get("n_low_depth_positions", 0)),
            consensus_n_fraction=float(item.get("consensus_n_fraction", 0.0)),
            n_low_quality_bases=int(item.get("n_low_quality_bases", 0)),
            n_input_reads=item.get("n_input_reads"),
            n_aligned_reads=item.get("n_aligned_reads"),
            n_mapq_failed=int(item.get("n_mapq_failed", 0)),
            n_span_failed=int(item.get("n_span_failed", 0)),
        )
        translated = TranslatedRecord(
            barcode=barcode,
            aa_sequence=item["aa_sequence"],
            observed_nt_changes=list(item["observed_nt_changes"]),
            observed_aa_changes=list(item["observed_aa_changes"]),
        )
        vr = VerdictRecord(
            translated=translated,
            expected_mutations=list(item["expected_mutations"]),
            verdict=VerdictClass(item["verdict"]),
            verdict_notes=item["verdict_notes"],
        )
        verdicts.append(vr)
        by_key[(barcode.native_barcode, barcode.custom_barcode)] = vr

    replicates: list[ReplicateResult] = []
    for item in data.get("replicates", []):
        rr = ReplicateResult(
            mutant_id=item["mutant_id"],
            plate_verdicts={},
            selected_plate=item.get("selected_plate"),
            selection_reason=item.get("selection_reason", ""),
            failed=bool(item.get("failed", False)),
        )
        replicates.append(rr)
    return verdicts, replicates


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "analyze":
        return _cmd_analyze(args)
    if args.command == "translate":
        return _cmd_translate(args)
    if args.command == "export":
        return _cmd_export(args)
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
