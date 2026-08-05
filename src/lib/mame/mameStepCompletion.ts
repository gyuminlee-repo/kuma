import type { MameSubStepId } from "@/store/mame/slices/mameSubSteps";
import type {
  BuildEvolveproCompletionRecord,
  BuildEvolveproFormState,
} from "@/lib/mame/buildEvolveproFormStorage";
import { hasCompletedBuildEvolveproOutput } from "@/lib/mame/buildEvolveproFormStorage";
import type { AnalyzeSummary, VerdictRecord } from "@/types/mame/models";

export interface MameCompletionState {
  inputDir: string;
  expectedPath: string;
  referencePath: string;
  outputPath: string;
  verdicts: VerdictRecord[];
  summary: AnalyzeSummary | null;
  activityComplete: boolean;
  buildEvolveproForm: BuildEvolveproFormState;
  buildEvolveproCompletion: BuildEvolveproCompletionRecord | null;
  /**
   * Janus liquid class. The one instrument value with no default and no way to
   * derive it, so it is what separates "settings were entered" from "shipped
   * defaults". Blank never blocks a run; it only leaves step 3 not-done.
   */
  janusLiquidClass: string;
  /** A run (or an export) already wrote the instrument mapping file. */
  janusMappingWritten: boolean;
}

export function isMameSubStepDone(
  id: MameSubStepId,
  state: MameCompletionState,
): boolean {
  if (id === "setup.files" || id === "setup.design") {
    return Boolean(
      state.inputDir &&
        state.expectedPath &&
        state.referencePath &&
        state.outputPath,
    );
  }
  if (
    id === "analyze.inputs" ||
    id === "analyze.review" ||
    id === "analyze.verdict" ||
    id === "analyze.plate"
  ) {
    return state.verdicts.length > 0 || state.summary !== null;
  }
  if (id === "janus.settings") {
    // Optional step: done once the operator supplied the value nothing can
    // derive, or once a mapping file actually exists. Never a gate for step 2
    // or step 4 — a sequencing-only run leaves this step untouched.
    return Boolean(state.janusLiquidClass) || state.janusMappingWritten;
  }
  if (id === "activity.ingest") {
    return (
      state.activityComplete ||
      hasCompletedBuildEvolveproOutput(
        state.buildEvolveproForm,
        state.buildEvolveproCompletion,
      )
    );
  }
  return false;
}
