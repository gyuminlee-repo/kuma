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
