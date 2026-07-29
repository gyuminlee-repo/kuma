/**
 * MAME sub-step 상수 정의.
 *
 * phaseSlice와 navigationSlice 양쪽에서 import하므로
 * 순환 의존성을 피하기 위해 MamePhase를 인라인으로 정의한다.
 * phaseSlice.ts의 MamePhase와 동일한 union이어야 한다.
 */

export type MameSubStepId =
  | "setup.files"
  | "analyze.inputs"
  | "analyze.review"
  // Legacy ids retained for redirect/migration. Not in MAME_SUBSTEP_ORDER.
  | "analyze.verdict"
  | "analyze.plate"
  | "setup.design"
  | "activity.ingest"
  | "activity.signals"
  // activity.mergeExport merged into the single activity.ingest step; kept as legacy redirect id.
  | "activity.mergeExport";

export const MAME_SUBSTEP_ORDER: Record<
  "setup" | "analyze" | "activity",
  MameSubStepId[]
> = {
  setup: ["setup.files"],
  analyze: ["analyze.inputs", "analyze.review"],
  activity: ["activity.ingest", "activity.signals"],
};
