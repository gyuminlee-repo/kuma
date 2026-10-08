import type { MameSubStepId } from "@/store/mame/slices/mameSubSteps";
import type {
  BuildEvolveproCompletionRecord,
  BuildEvolveproFormState,
} from "@/lib/mame/buildEvolveproFormStorage";
import { hasCompletedBuildEvolveproOutput } from "@/lib/mame/buildEvolveproFormStorage";
import type { AnalyzeSummary, VerdictRecord } from "@/types/mame/models";
import type { RoundAdvisoryRecord } from "@/types/round";

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
  /**
   * The advisory answer the active round holds, already checked against the
   * files it was computed from. Callers get it from currentRoundAdvisory
   * (lib/round/roundArtifacts.ts), which returns null when no answer was ever
   * computed and when the round outputs behind one have been rebuilt since.
   */
  advisory: RoundAdvisoryRecord | null;
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
    // Done means the round holds a classifier answer that current round data
    // does not contradict, not that the classifier recommended anything.
    //
    // 4.2 is advisory: it reads per-round xlsx files and reports where the
    // signals stand. There is nothing for the operator to produce, so the only
    // thing "done" can mean is that an answer came back and is on record.
    //
    // Both answer shapes count, including "not_assessable". That shape says the
    // signals reached a transition candidate and the confirming test had too
    // few WT replicates on record to run on, which is a real finding about
    // these inputs rather than a failed run. Requiring a switch_combinatorial
    // or stop verdict would leave the step unfinished for every round whose
    // measurements carry fewer WT wells than the noise estimate needs, which is
    // a property of the bench run rather than of the operator work in step 4.
    //
    // A run that threw, or one still in flight, records nothing and leaves the
    // step open. So does a rebuild in step 4.1 of a file the answer was
    // computed from: currentRoundAdvisory stops returning that answer, here and
    // in the card alike, and the operator is asked to run it again.
    //
    // The single source is the record on the round (Round.advisory), which
    // rides in the mame autosave snapshot with rounds[]. Nothing is published
    // by the card into the app store, so a restarted app reports the step from
    // what is on disk instead of waiting for the screen to be opened.
    return state.advisory !== null;
  }
  return false;
}
