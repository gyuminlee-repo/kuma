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
 * metrics internally.  The "unavailable" response is retired; the handler
 * always returns a Decision (or raises a JSON-RPC error on bad input).
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
 * Returned when classify() ran successfully and produced a Decision.
 * advisory === "decision"
 */
export interface ClassifyDecisionResult {
  advisory: "decision";
  label: DecisionLabel;
  reason: string;
  confidence: number | null;
}

/**
 * Union of possible successful handler responses.
 * Fork D retires the "unavailable" shape; only "decision" is returned on success.
 * JSON-RPC errors (-32602 / -32002) are returned for bad input or missing files.
 *
 * Note for integrators: remove handling of ClassifyUnavailableResult from UI
 * components; the handler no longer emits it.
 */
export type ClassifyRoundResult = ClassifyDecisionResult;

/**
 * @deprecated Fork D: "unavailable" is no longer returned by the handler.
 * Kept here for rollback compatibility during the transition period.
 * Remove once UI callers are updated.
 */
export interface ClassifyUnavailableResult {
  advisory: "unavailable";
  missing: string[];
}
