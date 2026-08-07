import type { MameSubStepId } from "@/store/mame/slices/mameSubSteps";
import type {
  BuildEvolveproCompletionRecord,
  BuildEvolveproFormState,
} from "@/lib/mame/buildEvolveproFormStorage";
import { hasCompletedBuildEvolveproOutput } from "@/lib/mame/buildEvolveproFormStorage";
import type { AnalyzeSummary, VerdictRecord } from "@/types/mame/models";
import type { ClassifyRoundResult } from "@/types/mame/strategy";

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
  /** What the last advisory classification answered, or null if none has run. */
  advisoryDecision: ClassifyRoundResult | null;
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
  if (id === "activity.signals") {
    // Done means the classifier answered, not that it recommended anything.
    //
    // 4.2 is advisory: it reads per-round xlsx files and reports where the
    // signals stand. There is nothing for the operator to produce, so the only
    // thing "done" can mean is that an answer came back and is on record.
    //
    // Both answer shapes count, including "not_assessable". That shape says the
    // signals reached a transition candidate and the confirming test had no WT
    // replicates to run on, which is a real finding about these inputs rather
    // than a failed run. Requiring a switch_combinatorial or stop verdict would
    // leave the step permanently unfinished, since the purified xlsx format
    // cannot carry the inputs those labels are gated behind.
    //
    // A run that threw, or one still in flight, leaves this null and the step
    // open. So does clearing the picked files, which resets the stored answer.
    //
    // The answer survives a restart: AdvisoryDecisionCard files it on the round
    // with the files it was computed from, and republishes it here on restore
    // only while those files are still the ones selected.
    return state.advisoryDecision !== null;
  }
  return false;
}
