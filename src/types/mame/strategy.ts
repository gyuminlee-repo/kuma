/**
 * Types for the strategy.classify_round JSON-RPC advisory slice (v0.4 Fork D).
 *
 * Read-only. No confirmation button, no PI decision persistence.
 * Mirrors the Python handler return shapes in classify_round.py.
 *
 * RPC contract change (Fork D):
 *   OLD: { round_id: string }
 *   NEW: { round_files: RoundFileEntry[], c_next?: number }
 *
 * The handler now reads xlsx files directly and computes all cross-round
 * metrics internally.
 *
 * Two success shapes, discriminated by `advisory`:
 *   "decision"       the classifier answered.
 *   "not_assessable" the classifier was never asked, because the wild-type
 *                    replicates it needs were absent or too few.
 * Bad input still raises a JSON-RPC error.
 */

/** Valid classification outcome labels from classify(). */
export type DecisionLabel =
  | "continue_walking"
  | "switch_combinatorial"
  | "stop"
  | "deferred";

/**
 * One round xlsx file entry.
 * n: round number (1-based, ascending).
 * path: absolute path to the xlsx file.
 */
export interface RoundFileEntry {
  n: number;
  path: string;
  /**
   * Wild-type replicates step 4.1 recorded for that round, on the scale of the
   * activity column in the same file. They travel beside the file because the
   * file cannot hold them: it carries one row per designed variant and the WT
   * rows were filtered out to build it.
   *
   * Only the highest-numbered entry is read. The bootstrap resamples the noise
   * of the round being judged, and the earlier entries are in the list to
   * supply the hit-rate trend.
   *
   * Absent on a file the operator picked by hand and on rounds built before
   * step 4.1 kept them, which is what leaves the answer not assessable.
   */
  wt_values?: number[];

  /**
   * The replicates behind each exported activity in that round, keyed by
   * variant. Absent on rounds built before the build recorded them.
   */
  variant_replicates?: Record<string, number[]>;
}

/**
 * Parameters for strategy.classify_round RPC (Fork D).
 *
 * round_files: ordered list of xlsx file references; the handler sorts by n.
 * c_next: capacity of the next combinatorial plate (wells).
 *         Used to derive K_throughput = floor((1+sqrt(1+8*c_next))/2).
 *         Default: 96 if absent.
 */
export interface ClassifyRoundParams {
  round_files: RoundFileEntry[];
  c_next?: number;
}

/**
 * An input the handler could not hand to the classifier.
 *
 * `wt_replicates`: the wild-type replicates the current round recorded. The
 * per-round xlsx has no column for them, so they travel beside it on the round
 * entry; when none arrive, or fewer than the noise estimate needs, sigma_assay
 * cannot be estimated and the bootstrap test behind the gated labels cannot
 * run.
 */
export type MissingClassifierInput = "wt_replicates";

/**
 * Why the classifier was never asked.
 *
 * The two are different facts about the round and call for different remedies:
 * `wt_replicates_missing` means nothing was recorded at all, and
 * `wt_replicates_insufficient` means some were, just fewer than the minimum.
 */
export type NotAssessableReason =
  | "wt_replicates_missing"
  | "wt_replicates_insufficient";

/**
 * Returned when classify() ran and produced a Decision.
 * advisory === "decision"
 *
 * `missing_inputs` is reported even here: an answered decision was still
 * reached with T2 and T_model unavailable, and the caller should say so.
 */
export interface ClassifyDecisionResult {
  advisory: "decision";
  label: DecisionLabel;
  reason: string;
  confidence: number | null;
  missing_inputs: MissingClassifierInput[];
}

/**
 * Returned when the classifier reached a branch it could not be asked about.
 * advisory === "not_assessable"
 *
 * This is not a verdict and deliberately carries no `label`. The core decision
 * tree did propose a transition, which is why the bootstrap gate was reached at
 * all, but the gate had no inputs. `blocked_decisions` names the labels that
 * are unreachable until those inputs exist; everything else the classifier can
 * still answer normally.
 */
export interface ClassifyNotAssessableResult {
  advisory: "not_assessable";
  reason: NotAssessableReason;
  missing_inputs: MissingClassifierInput[];
  blocked_decisions: DecisionLabel[];
  /**
   * Wild-type replicates the current round handed over.
   *
   * Optional because an answer stored on a round before this field existed is
   * replayed verbatim from the snapshot (`Round.advisory.result`), and those
   * records carry neither count. Such a record always has reason
   * `wt_replicates_missing`, the only value that existed then, which the card
   * renders without either number.
   */
  wt_replicate_count?: number;
  /** Replicates the noise estimate needs before the bootstrap can run. */
  wt_replicate_min?: number;
}

/**
 * Union of possible successful handler responses.
 * JSON-RPC errors (-32602 / -32002) are returned for bad input or missing files.
 */
export type ClassifyRoundResult =
  | ClassifyDecisionResult
  | ClassifyNotAssessableResult;
