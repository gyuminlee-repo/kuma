"""CLI entry point (argparse-based)."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from kuma_core.mame.export import WellMapper, write_excel
from kuma_core.mame.ingest import IngestMode, route_ingest
from kuma_core.mame.models import (
    BarcodeRecord,
    NoisyPosition,
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
            "n_no_call_aa": t.n_no_call_aa,
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
                "min_variant_support": vr.translated.barcode.min_variant_support,
                "n_variant_positions": vr.translated.barcode.n_variant_positions,
                "min_variant_support_depth": vr.translated.barcode.min_variant_support_depth,
                "median_minor_allele_fraction": vr.translated.barcode.median_minor_allele_fraction,
                "max_minor_allele_strand_share": vr.translated.barcode.max_minor_allele_strand_share,
                "max_minor_allele_plus_count": vr.translated.barcode.max_minor_allele_plus_count,
                "max_minor_allele_minus_count": vr.translated.barcode.max_minor_allele_minus_count,
                "n_eligible_positions": vr.translated.barcode.n_eligible_positions,
                "noisy_positions": [
                    asdict(position) for position in vr.translated.barcode.noisy_positions
                ],
                "n_indel_event_positions": vr.translated.barcode.n_indel_event_positions,
                "max_indel_event_fraction": vr.translated.barcode.max_indel_event_fraction,
                "depth_cv": vr.translated.barcode.depth_cv,
                "depth_p10": vr.translated.barcode.depth_p10,
                "depth_min_covered": vr.translated.barcode.depth_min_covered,
                "breadth_at_mix_min_depth": vr.translated.barcode.breadth_at_mix_min_depth,
                "consensus_identity": vr.translated.barcode.consensus_identity,
                "source_path": str(vr.translated.barcode.source_path),
                "consensus_seq": vr.translated.barcode.consensus_seq,
                # The consensus indel evidence. Same fields the sidecar
                # serializer lost across a session boundary, missing here for
                # the same reason: this dump is written field by field. The two
                # net-indel values carry their ``None`` through JSON null
                # because None is NOT MEASURED and skips the FRAMESHIFT gate,
                # while 0 is a measured indel-free consensus
                # (kuma_core/mame/models.py:227-235).
                "max_del_run_length": vr.translated.barcode.max_del_run_length,
                "consensus_net_indel_bp": (
                    vr.translated.barcode.consensus_net_indel_bp
                ),
                "median_read_net_indel_bp": (
                    vr.translated.barcode.median_read_net_indel_bp
                ),
                "length_true_nt": vr.translated.length_true_nt,
                "aa_sequence": vr.translated.aa_sequence,
                "n_no_call_aa": vr.translated.n_no_call_aa,
                "observed_nt_changes": vr.translated.observed_nt_changes,
                "observed_aa_changes": vr.translated.observed_aa_changes,
                "expected_mutations": vr.expected_mutations,
                "verdict": vr.verdict.value,
                "verdict_notes": vr.verdict_notes,
                "mutant_id": vr.mutant_id,
            }
            for vr in verdicts
        ],
        "replicates": [
            {
                "mutant_id": rr.mutant_id,
                "selected_plate": rr.selected_plate,
                "selection_reason": rr.selection_reason,
                "failed": rr.failed,
                "is_fallback": rr.is_fallback,
                "fallback_reason": rr.fallback_reason,
                "plate_keys": list(rr.plate_verdicts.keys()),
                "plate_barcodes": {
                    plate: vr.translated.barcode.custom_barcode
                    for plate, vr in rr.plate_verdicts.items()
                },
            }
            for rr in replicates
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _opt_int(item: dict, key: str) -> int | None:
    """``None`` when the key is absent, so unmeasured never becomes 0."""
    value = item.get(key)
    return None if value is None else int(value)


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
            min_variant_support=item.get("min_variant_support"),
            n_variant_positions=int(item.get("n_variant_positions", 0)),
            min_variant_support_depth=int(item.get("min_variant_support_depth", 0)),
            median_minor_allele_fraction=float(item.get("median_minor_allele_fraction", 0.0)),
            max_minor_allele_strand_share=item.get("max_minor_allele_strand_share"),
            max_minor_allele_plus_count=int(item.get("max_minor_allele_plus_count", 0)),
            max_minor_allele_minus_count=int(item.get("max_minor_allele_minus_count", 0)),
            n_eligible_positions=int(item.get("n_eligible_positions", 0)),
            noisy_positions=tuple(
                NoisyPosition(**position) for position in item.get("noisy_positions", [])
            ),
            n_indel_event_positions=int(item.get("n_indel_event_positions", 0)),
            max_indel_event_fraction=float(item.get("max_indel_event_fraction", 0.0)),
            depth_cv=item.get("depth_cv"),
            depth_p10=item.get("depth_p10"),
            depth_min_covered=_opt_int(item, "depth_min_covered"),
            breadth_at_mix_min_depth=item.get("breadth_at_mix_min_depth"),
            consensus_identity=item.get("consensus_identity"),
            # Absent in a dump written before these keys existed, in which case
            # BarcodeRecord's own defaults stand and the record restores exactly
            # as it did. ``None`` is passed through rather than coerced, so an
            # unmeasured net indel never reads as a measured zero.
            max_del_run_length=int(item.get("max_del_run_length", 0)),
            consensus_net_indel_bp=_opt_int(item, "consensus_net_indel_bp"),
            median_read_net_indel_bp=_opt_int(item, "median_read_net_indel_bp"),
        )
        length_true_nt = item.get("length_true_nt")
        translated = TranslatedRecord(
            barcode=barcode,
            aa_sequence=item["aa_sequence"],
            observed_nt_changes=list(item["observed_nt_changes"]),
            observed_aa_changes=list(item["observed_aa_changes"]),
            n_no_call_aa=int(item.get("n_no_call_aa", 0)),
            length_true_nt=(
                None if length_true_nt is None else str(length_true_nt)
            ),
        )
        vr = VerdictRecord(
            translated=translated,
            expected_mutations=list(item["expected_mutations"]),
            verdict=VerdictClass(item["verdict"]),
            verdict_notes=item["verdict_notes"],
            mutant_id=item.get("mutant_id", ""),
        )
        verdicts.append(vr)
        by_key[(barcode.native_barcode, barcode.custom_barcode)] = vr

    replicates: list[ReplicateResult] = []
    for item in data.get("replicates", []):
        plate_verdicts: dict[str, VerdictRecord] = {}
        for plate in item.get("plate_keys", []):
            if "plate_barcodes" in item:
                plate_verdicts[plate] = by_key[(plate, item["plate_barcodes"][plate])]
                continue
            candidates = [
                vr for (native, _), vr in by_key.items()
                if native == plate and item["mutant_id"] in vr.expected_mutations
            ]
            if len(candidates) != 1:
                raise ValueError(
                    f"Cannot uniquely restore {item['mutant_id']} on {plate}; "
                    "regenerate verdict JSON with explicit plate_barcodes."
                )
            plate_verdicts[plate] = candidates[0]
        rr = ReplicateResult(
            mutant_id=item["mutant_id"],
            plate_verdicts=plate_verdicts,
            selected_plate=item.get("selected_plate"),
            selection_reason=item.get("selection_reason", ""),
            failed=bool(item.get("failed", False)),
            is_fallback=bool(item.get("is_fallback", False)),
            fallback_reason=item.get("fallback_reason"),
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
