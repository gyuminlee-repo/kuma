/**
 * TypeScript mirror of the step 4.1 positive clone JANUS mapping RPCs,
 * `mame.activity.positive_janus_candidates` and
 * `mame.activity.export_positive_janus`.
 *
 * Hand-written like the rest of this directory. Source of truth is
 * `python-core/sidecar_mame/models.py` (`PositiveJanusCandidatesParams`,
 * `PositiveJanusExportParams`) and the two handlers in
 * `python-core/sidecar_mame/handlers/activity.py`.
 */

/** The round-1 screen and the mapping that names its wells. */
export interface PositiveJanusSourceParams {
  gc_data_xlsx?: string;
  round1_report_xlsx?: string;
  numeric_report_xlsx?: string;
  verdict_xlsx?: string;
  layout_xlsx?: string;
  expected_xlsx?: string;
}

/** One measured non-WT well of the screen. */
export interface PositiveJanusCandidate {
  /** Source well in the plain spelling the sheet writes, e.g. `A1`. */
  well: string;
  /** Mutant name the mapping gives that well. */
  name: string;
  /** Mean relative activity over the wild-type reference. */
  relative: number;
  n_replicates: number;
  /** Whether the shared above-WT rule selected it. */
  above_wt: boolean;
}

/** Deck defaults the sidecar states, so the panel shows its values. */
export interface PositiveJanusDefaults {
  volume: number;
  source_rack: string;
  dest_rack: string;
  sample_type: string;
}

export interface PositiveJanusCandidatesResult {
  candidates: PositiveJanusCandidate[];
  n_above_wt: number;
  warnings: string[];
  defaults: PositiveJanusDefaults;
}

export interface PositiveJanusExportParams extends PositiveJanusSourceParams {
  selected_wells: string[];
  volume: number;
  source_rack: string;
  dest_rack: string;
  output_csv: string;
}

export interface PositiveJanusExportResult {
  output_path: string;
  row_count: number;
  /** The written rows keyed by the device sheet header. */
  rows: Record<string, string | number>[];
}
