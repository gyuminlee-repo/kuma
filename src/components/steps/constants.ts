/**
 * KURO wizard step numbering — 단일 진실 원천.
 *
 * [source: spec §0.3 — KURO wizard step numbering 통합 1..6]
 *
 * Design(4) + Output(1) + Export(1) = 6 sub-steps.
 */

export const TOTAL_KURO_STEPS = 6;

export const KURO_STEP_INDEX = {
  "design.load": 1,
  "design.mutation": 2,
  "design.params": 3,
  "design.submit": 4,
  "output.summary": 5,
  "export.all": 6,
} as const;

export type KuroSubStepId = keyof typeof KURO_STEP_INDEX;
