/**
 * TypeScript mirror of kuma_core/strategy/models.py RoundMetrics Pydantic model.
 * Spec: notes/specs/2026-05-04-mame-activity-integration.md §12-A.1, §12-A.4
 * Phase 6 Task 6.3 — display-only type for RoundSummaryPanel.
 *
 * Keep in sync with:
 *   - kuma_core/strategy/models.py (RoundMetrics)
 *   - kuma_core/strategy/signals.py (signal functions)
 *
 * NOTE: Python model uses set[int] for top_k_positions_n / top_k_positions_n1.
 * JSON serialisation cannot round-trip sets, so TS uses number[] (list semantics).
 */

export interface RoundMetrics {
  /** Identifier of the ALE round (e.g. "round_1") */
  round_id: string
  /** ISO 8601 timestamp when signals were computed */
  computed_at: string

  // -----------------------------------------------------------------------
  // Raw inputs (displayed as contextual values alongside each signal)
  // -----------------------------------------------------------------------

  /** Total beneficial single mutations found cumulatively */
  cumulative_beneficial: number
  /** Required number of building blocks from compute_K_throughput */
  K_throughput: number
  /** EMA_2 of (best_n − best_{n-1}) */
  delta_best_ema: number
  /**
   * Assay noise estimate from WT replicate stdev.
   * null when WT replicates < 4 → T2 unavailable (spec §12-A.8).
   */
  sigma_assay: number | null
  /** Number of replicates per well used in T2 calculation */
  r: number
  /** Per-round hit rates (n_positive / n_designed) */
  hit_rates: number[]
  /** Residue positions in top-K variants of current round (list, not Set) */
  top_k_positions_n: number[]
  /** Residue positions in top-K variants of previous round (list, not Set) */
  top_k_positions_n1: number[]
  /** Flat list of residue positions in current top-K */
  top_k_positions: number[]
  /** Known active-site residue positions */
  active_residues: number[]
  /** Beneficial mutations not used as next baseline */
  unused_beneficial_count: number

  // -----------------------------------------------------------------------
  // Computed signal booleans (spec §12-A.1)
  // -----------------------------------------------------------------------

  /** T1: cumulative_beneficial >= K_throughput */
  T1: boolean
  /** T2: delta_best_ema below noise threshold (plateau) */
  T2: boolean
  /** T3: hit rate trend slope <= 0 */
  T3: boolean
  /** T4: top-K position Jaccard >= 0.5 */
  T4: boolean
  /** T_active: active-site fraction >= 0.4 */
  T_active: boolean
  /** T_unused: unused_beneficial_count >= M_min */
  T_unused: boolean
}
