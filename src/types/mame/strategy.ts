/**
 * Types for the strategy.classify_round JSON-RPC advisory slice (v0.3).
 *
 * Read-only. No confirmation button, no PI decision persistence.
 * Mirrors the Python handler return shapes in classify_round.py.
 */

/** Valid classification outcome labels from classify(). */
export type DecisionLabel =
  | "continue_walking"
  | "switch_combinatorial"
  | "stop"
  | "deferred";

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
 * Returned when required scalar plumbing fields are absent from the round store.
 * advisory === "unavailable"
 */
export interface ClassifyUnavailableResult {
  advisory: "unavailable";
  /** Field names from RoundState that are missing in the sidecar store. */
  missing: string[];
}

/** Union of the two possible successful handler responses. */
export type ClassifyRoundResult = ClassifyDecisionResult | ClassifyUnavailableResult;

/** Parameters for strategy.classify_round RPC. */
export interface ClassifyRoundParams {
  round_id: string;
}
