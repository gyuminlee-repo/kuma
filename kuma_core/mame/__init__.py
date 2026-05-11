"""NGS screening decision orchestration layer (Phase 1 MVP).

MinKNOW run folder inputs consumed by this package:

Required
    fastq_pass/<barcode*|NB*>/*.fastq.gz
        Primary pipeline input. See ``ingest.sort_barcode`` and ``ingest.demux``.

Run metadata (auto-detected, optional)
    final_summary_*.txt, sample_sheet_*.csv
        Parsed by ``ingest.run_meta``.

QC / Health (auto-detected, optional)
    sequencing_summary*.{txt,tsv} (incl. ``_passed_`` variants)
        Used by ``cross_talk`` and ``ingest.quality_filter``.
    pore_activity_*.csv, throughput_*.csv,
    barcode_alignment_passed*.tsv (fallback: barcode_alignment*.tsv)
        Used by ``health``.

Everything else under a MinKNOW run directory (pod5/, fast5/, bam_pass/,
other_reports/, report_*.html/json, …) is ignored.
"""

__version__ = "0.1.0"
