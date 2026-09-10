"""Generalised run1.py/run2.py: demux+ingest once, then run_analyze against
one workbook. Parameterised by run_dir/reference/workbook/native_barcodes so
the same script covers R3-1-amp and R2-amp with either code variant
(KUMA_WT/GUARD_MARK env vars set by the caller).

Usage:
  run_round.py <label> <run_dir> <workbook_xlsx> <reference_fasta> \
      <cds_start> <cds_end> <native_barcodes_csv> <out_dir> <barcodes_xlsx>
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from mame_common2 import log_open  # noqa: E402

from kuma_core.mame.detected import designed_mutant_ids  # noqa: E402
from kuma_core.mame.ingest import IngestMode, ingest_run_folder  # noqa: E402
from kuma_core.mame.io.variant_list import read_variant_source  # noqa: E402
from kuma_core.mame.layout import build_draft_layout  # noqa: E402
from kuma_core.mame.pipeline import run_analyze  # noqa: E402


def main() -> None:
    (label, run_dir, workbook, reference, cds_start, cds_end,
     native_barcodes_csv, out_dir, barcodes_xlsx) = sys.argv[1:10]
    run_dir = Path(run_dir)
    workbook = Path(workbook)
    reference = Path(reference)
    barcodes_xlsx = Path(barcodes_xlsx)
    cds_start = int(cds_start)
    cds_end = int(cds_end)
    native_barcodes = native_barcodes_csv.split(",")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    demux_dir = out_dir / "demux"
    log = log_open(out_dir / "run.log")

    def say(msg: str) -> None:
        log.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")
        print(msg, flush=True)

    say(f"=== {label} run_dir={run_dir} ref={reference} cds={cds_start}..{cds_end}")
    say(f"    workbook={workbook} native_barcodes={native_barcodes}")

    _last = [0.0]

    def progress(done: int, total: int, stage: str) -> None:
        now = time.time()
        if now - _last[0] < 20 and done != total:
            return
        _last[0] = now
        log.write(f"[{time.strftime('%H:%M:%S')}] demux {stage} {done}/{total}\n")

    stats: dict[str, int] = {}
    per_nb: list[dict] = []
    resume: dict[str, int] = {}

    t0 = time.time()
    records = ingest_run_folder(
        run_dir=run_dir,
        custom_barcodes_xlsx=barcodes_xlsx,
        reference_fasta=reference,
        demux_output_dir=demux_dir,
        native_barcodes=native_barcodes,
        mapq_threshold=25,
        coverage_fraction=0.98,
        trim_flank_bp=30,
        edit_dist_ratio=0.25,
        chimera_split=True,
        progress_callback=progress,
        stats_out=stats,
        per_nb_out=per_nb,
        resume_out=resume,
    )
    t_demux = time.time() - t0
    say(f"demux+ingest done in {t_demux:.1f}s -> {len(records)} records")
    say(f"    stats={stats}")

    (out_dir / "demux_stats.json").write_text(
        json.dumps(
            {
                "label": label, "reference": str(reference),
                "cds_start": cds_start, "cds_end": cds_end,
                "native_barcodes": native_barcodes,
                "wall_seconds": t_demux, "resumed": resume,
                "n_records": len(records), "stats": stats, "per_nb": per_nb,
            }, indent=2,
        ), encoding="utf-8",
    )

    t1 = time.time()
    read = read_variant_source(workbook)
    draft = build_draft_layout(read.expected, wt_ordinal=read.wt_ordinal)
    out_xlsx = out_dir / f"{label}_MAME.xlsx"
    say(
        f"analyze rows={len(read.expected)} wt_ordinal={read.wt_ordinal} "
        f"layout={len(draft.layout)} -> {out_xlsx.name}"
    )
    verdicts, replicates = run_analyze(
        input_dir=demux_dir,
        reference_path=reference,
        expected_path=workbook,
        output_path=out_xlsx,
        cds_start=cds_start,
        cds_end=cds_end,
        mode="amplicon",
        min_file_size_kb=50.0,
        min_read_count=30,
        max_consensus_n_fraction=0.0,
        many_cutoff=5,
        ingest_mode=IngestMode.BARCODE,
        well_layout=draft.layout,
        scored_wells=None,
        records=records,
        expected_mutations=read.expected,
        designed_mutant_ids=designed_mutant_ids(read.expected),
        perf_scope=None,
    )
    t_an = time.time() - t1
    say(f"    {len(verdicts)} verdicts, {len(replicates)} replicate groups, {t_an:.1f}s")
    (out_dir / f"{label}_meta.json").write_text(
        json.dumps(
            {
                "label": label, "workbook": str(workbook), "reference": str(reference),
                "cds_start": cds_start, "cds_end": cds_end,
                "native_barcodes": native_barcodes,
                "n_expected": len(read.expected), "wt_ordinal": read.wt_ordinal,
                "layout_size": len(draft.layout), "n_verdicts": len(verdicts),
                "analyze_wall_seconds": t_an, "demux_wall_seconds": t_demux,
                "demux_resumed": resume, "output": str(out_xlsx),
            }, indent=2,
        ), encoding="utf-8",
    )
    say(f"=== {label} complete, total {time.time() - t0:.1f}s")
    log.close()


if __name__ == "__main__":
    main()
