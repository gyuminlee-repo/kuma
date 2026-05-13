/**
 * MAME sub-step 상수 정의.
 *
 * phaseSlice와 navigationSlice 양쪽에서 import하므로
 * 순환 의존성을 피하기 위해 MamePhase를 인라인으로 정의한다.
 * phaseSlice.ts의 MamePhase와 동일한 union이어야 한다.
 */

export type MameSubStepId =
  | "setup.files"
  | "setup.design"
  | "setup.output"
  | "analyze.inputs"
  | "analyze.verdict"
  | "analyze.plate"
  | "activity.ingest"
  | "activity.mergeExport";

export const MAME_SUBSTEP_ORDER: Record<
  "setup" | "analyze" | "activity",
  MameSubStepId[]
> = {
  setup: ["setup.files", "setup.design", "setup.output"],
  analyze: ["analyze.inputs", "analyze.verdict", "analyze.plate"],
  activity: ["activity.ingest", "activity.mergeExport"],
};
