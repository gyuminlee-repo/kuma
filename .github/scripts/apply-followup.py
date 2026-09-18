"""Temporary exact-preimage patch runner for PR 428; removed before merge."""
from pathlib import Path
import subprocess

EXPECTED = {
    "kuma_core/kuro/cli.py": "0e2a5b3da24c6e11e29076713906599900832c47",
    "kuma_core/mame/models.py": "e3c1b830de49a5337f36011c8f03c1366aa4be13",
    "kuma_core/mame/ingest/combinatorial_demux.py": "e14005cb1f1e60b54f1938e22dc048d3d6d63dd2",
    ".github/workflows/ci.yml": "cba9d7d740d58dd2583134708c6de4761e4766ef",
}
for filename, sha in EXPECTED.items():
    actual = subprocess.check_output(["git", "hash-object", filename], text=True).strip()
    if actual != sha:
        raise SystemExit(f"Refusing changed preimage: {filename}: {actual} != {sha}")


def replace_one(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError(f"Expected one exact match, got {text.count(old)}: {old[:90]!r}")
    return text.replace(old, new, 1)


CLI_DESIGN = r'''def _parse_organism(value: str) -> str:
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

'''
path = Path("kuma_core/kuro/cli.py")
text = path.read_text(encoding="utf-8")
start = text.index("def cmd_design(")
end = text.index("\ndef cmd_plate_map(", start)
text = text[:start] + CLI_DESIGN + text[end:]
text = replace_one(text, 'def main() -> None:\n    """Main CLI entry point."""',
                   'def build_parser() -> argparse.ArgumentParser:\n    """Build the CLI parser without reading process arguments."""')
text = replace_one(text, '        "--fasta", required=True, help="Template FASTA file"',
                   '        "--fasta", required=True, help="Annotated GenBank or SnapGene template (legacy option name)"')
anchor = '    design_parser.add_argument(\n        "--polymerase", default="Q5",'
text = replace_one(text, anchor, '''    design_parser.add_argument(
        "--organism", "--host-organism", type=_parse_organism, default="ecoli",
        help="Registered host codon table or supported alias (default: ecoli)"
    )
    design_parser.add_argument(
        "--fail-on-partial", action="store_true",
        help="Exit 2 after exporting partial successes when any mutation failed"
    )
''' + anchor)
text = replace_one(text, '    args = parser.parse_args()\n    _setup_logging(args.verbose)',
                   '    return parser\n\n\ndef main() -> None:\n    """Main CLI entry point."""\n    args = build_parser().parse_args()\n    _setup_logging(args.verbose)')
path.write_text(text, encoding="utf-8")

path = Path("kuma_core/mame/models.py")
text = path.read_text(encoding="utf-8")
text = replace_one(text,
    '    """8-class verdict enum. Order reflects comparison priority (fail-first checks)."""',
    '    """Stable serialized/display labels, NOT verdict-gate priority.\n\n    Runtime precedence belongs to compare.verdict.classify_verdict and is\n    exercised by tests/mame/test_verdict_behavior_contract.py. Keep this enum\n    order stable; sorting it cannot express gates that share the same label.\n    """')
path.write_text(text, encoding="utf-8")

path = Path("kuma_core/mame/ingest/combinatorial_demux.py")
text = path.read_text(encoding="utf-8")
text = replace_one(text, 'from __future__ import annotations\n',
    'from __future__ import annotations\n\nfrom kuma_core.mame.ingest.barcode_windows import barcode_window_bounds\n')
start = text.index('    L = len(read_seq)\n', text.index('def _extract_barcode_windows('))
end = text.index('\n\ndef _demux_read_anchored(', start)
text = text[:start] + '''    f_start, f_end, r_start, r_end = barcode_window_bounds(
        len(read_seq), q_st, q_en, strand, window_bp, max_f_len, max_r_len,
    )
    f_window = read_seq[f_start:f_end].upper()
    r_window = read_seq[r_start:r_end].upper()
    if strand == -1:
        f_window = _reverse_complement(f_window)
        r_window = _reverse_complement(r_window)
    return f_window, r_window
''' + text[end:]
text = replace_one(text, 'Align all raw FASTQ reads to reference using mappy (map-ont preset).',
                   'Align all raw FASTQ reads to reference using minimap2 CLI (map-ont preset).')
text = replace_one(text, '[max(0, q_st - window_bp - max_f_len), q_st + window_bp]',
                   '[max(0, q_st - window_bp - max_f_len), min(L, q_st)]')
text = replace_one(text, '[max(0, q_en - window_bp), min(L, q_en + window_bp + max_r_len)]',
                   '[max(0, q_en), min(L, q_en + window_bp + max_r_len)]')
text = replace_one(text, 'mappy and edlib available (pyproject.toml restricts mappy to Linux).',
                   'minimap2 executable and edlib available.')
# A now-extracted derivation is explained by the helper and its independent test.
text = replace_one(text, 'The -1 branch below is the second identity with the window bounds folded\n    in; see the comment there for the coordinate derivation.',
                   'The minus-strand bounds in barcode_window_bounds are the second identity\n    with the window bounds folded in; the whole-read oracle tests both forms.')
path.write_text(text, encoding="utf-8")

path = Path(".github/workflows/ci.yml")
text = path.read_text(encoding="utf-8")
start = text.index('      - name: Run Python tests\n')
end = text.index('\n  # A Python type gate', start)
text = text[:start] + '''      - name: Run Python tests
        # Actual execution outcomes, not a stale prose count of external tests.
        run: python -m pytest tests/ -v -rs --junitxml=validation-python.xml

      - name: Report external-data validation coverage
        if: always()
        run: python scripts/report_validation_coverage.py --junit validation-python.xml --output validation-coverage.json

      - name: Archive validation evidence
        if: always()
        uses: actions/upload-artifact@v6
        with:
          name: validation-${{ matrix.os }}-${{ matrix.python-version }}
          path: |
            validation-python.xml
            validation-coverage.json
          retention-days: 7
          if-no-files-found: error
''' + text[end:]
path.write_text(text, encoding="utf-8")

subprocess.run(["git", "diff", "--check"], check=True)
subprocess.run(["git", "diff", "--stat"], check=True)
print("Exact-preimage production changes applied; tests must pass before publication.")
