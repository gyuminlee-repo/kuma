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
 *   "not_assessable" the classifier was never asked, because an input it needs
 *                    is absent from the file format.
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
 * `wt_replicates`: the per-round xlsx holds one measured activity per designed
 * variant and no wild-type replicate column, so sigma_assay cannot be computed
 * and the bootstrap confidence test cannot run.
 */
export type MissingClassifierInput = "wt_replicates";

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
  reason: string;
  missing_inputs: MissingClassifierInput[];
  blocked_decisions: DecisionLabel[];
}

/**
 * Union of possible successful handler responses.
 * JSON-RPC errors (-32602 / -32002) are returned for bad input or missing files.
 */
export type ClassifyRoundResult =
  | ClassifyDecisionResult
  | ClassifyNotAssessableResult;
