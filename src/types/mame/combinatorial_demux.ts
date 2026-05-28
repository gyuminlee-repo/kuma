/**
 * TypeScript mirror of the ``mame.run_combinatorial_demux`` RPC handler.
 *
 * Keep in sync with:
 *   - kuma_core/mame/ingest/combinatorial_demux.py  (DemuxStats, DemuxResult)
 *   - python-core/sidecar_mame/handlers/combinatorial_demux.py (response dict)
 *   - python-core/sidecar_mame/models.py (CombinatorialDemuxParams)
 */

/** Summary counters from a single run_combinatorial_demux call. */
export interface CombinatorialDemuxStats {
  total_reads: number
  passed_mapq: number
  passed_coverage: number
  assigned_reads: number
  ambiguous_dropped: number
  chimera_splits: number
  wells_with_reads: number
  wells_with_min_reads: number
}

/** Result of a mame.run_combinatorial_demux RPC call. */
export interface CombinatorialDemuxResult {
  /** Resolved path to the output directory. */
  output_dir: string
  /** Full summary counters. */
  stats: CombinatorialDemuxStats
  /** Shortcut for stats.wells_with_reads. */
  wells_with_reads: number
  /** Shortcut for stats.assigned_reads. */
  assigned_reads: number
  /** Shortcut for stats.chimera_splits. */
  chimera_splits: number
  /**
   * Per-well consensus sequences.
   * Key: well name (e.g. "1_1" for R1xF1), value: consensus FASTA sequence.
   */
  per_well_consensus: Record<string, string>
  /**
   * Per-well read counts.
   * Key: well name (e.g. "1_1"), value: number of reads assigned.
   */
  per_well_read_counts: Record<string, number>
}

/** Parameters for the mame.run_combinatorial_demux RPC method. */
export interface CombinatorialDemuxParams {
  /** Root of a MinKNOW run directory (must contain fastq_pass/). */
  minknow_run_dir: string
  /** Path to the barcodes xlsx (isps_f_1..12 / isps_r_1..8 rows). */
  custom_barcodes_xlsx: string
  /** Single-record DNA FASTA used as alignment reference. */
  reference_fasta: string
  /** Destination directory for per-well FASTA and consensus files. */
  output_dir: string
  /**
   * Per-well sample-name mapping xlsx (col A: name, col B: well e.g. "A1").
   * Not yet implemented in PR-A; will raise an error if provided.
   * Deferred to PR-B.
   */
  sample_map_xlsx?: string | null
  /**
   * KURO results xlsx with expected_mutations sheet.
   * Not yet implemented in PR-A; will raise an error if provided.
   * Deferred to PR-B.
   */
  kuro_xlsx?: string | null
  /** Minimum MAPQ for alignment hits [0, 60]. Default 25. */
  mapq_threshold?: number
  /** Minimum fraction of reference covered by each hit (0, 1]. Default 0.98. */
  coverage_fraction?: number
  /** Max edit distance fraction of barcode prefix length (0, 1). Default 0.25. */
  edit_dist_ratio?: number
  /** When true, all alignment hits per read are evaluated (chimera splitting). Default true. */
  chimera_split?: boolean
  /** Bases flanking alignment hits to include in FASTA slice [0, 200]. Default 30. */
  trim_flank_bp?: number
}
