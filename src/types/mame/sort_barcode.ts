/**
 * TypeScript mirror of kuma_core/mame/ingest/sort_barcode.py SortBarcodeResult.
 *
 * Keep in sync with:
 *   - kuma_core/mame/ingest/sort_barcode.py (SortBarcodeResult dataclass)
 *   - python-core/sidecar_mame/handlers/sort_barcode.py (response dict)
 */

/** Result of a sort_barcode_run RPC call. */
export interface SortBarcodeResult {
  /** Resolved path to the output directory containing sort_barcode{NN}/ subdirs. */
  output_dir: string
  /** Basenames of native-barcode directories that were successfully processed. */
  nb_dirs_processed: string[]
  /** Total reads across all processed NB directories. */
  n_total_reads: number
  /** Reads successfully assigned to a well. */
  n_total_assigned: number
  /** Reads not matched to any well (both axes failed or ambiguous). */
  n_total_unassigned: number
  /**
   * Per-NB, per-well read counts.
   * Key: NB dir basename (e.g. "barcode06").
   * Value: {filename_stem → count} mapping (e.g. {"A01_V5F_F1_R1": 3, "B02_K53R_F2_R2": 1}).
   * Without sample map: {"A01_F1_R1": 3, ...}.
   */
  per_nb_per_well_counts: Record<string, Record<string, number>>
  /** NB dirs with no FASTQ files that were skipped (not an error). */
  skipped_nb_dirs: string[]
}

/** Parameters for the sort_barcode_run RPC method. */
export interface SortBarcodeRunParams {
  /** Root of a MinKNOW run directory (must contain fastq_pass/). */
  minknow_run_dir: string
  /** Path to the combinatorial barcode xlsx (isps_f_* / isps_r_* rows). */
  custom_barcodes_path: string
  /** Destination root; sort_barcode{NN}/ subdirs are created automatically. */
  output_dir: string
  /**
   * If provided, only these native-barcode dir basenames are processed.
   * Each must exist under fastq_pass/.
   */
  nb_override?: string[]
  /** Per-base mismatch rate for Hamming matching [0.0, 0.5]. Default 0.1. */
  error_tolerance?: number
  /**
   * Reserved for future cutadapt extension.
   * Combinatorial matching is always performed in pure Python.
   * Default true.
   */
  use_cutadapt?: boolean
  /**
   * Optional path to a sample/mutant map xlsx (col A: name, col B: well position e.g. "A1").
   * When provided, output filenames include the sample name: "A01_V5F_F1_R1.fasta".
   * Without it, filenames are "A01_F1_R1.fasta".
   */
  sample_map_path?: string
}
