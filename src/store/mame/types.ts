import type { AnalysisSlice, ExportSlice, InputSlice } from "./slice-interfaces";
import type { PhaseSlice } from "./slices/phaseSlice";
import type { NavigationSlice } from "./slices/navigationSlice";
import type { AnalyzeResult } from "@/types/mame/models";
import type { MameRunScope } from "@/lib/mame/runRequests";
import type { MameAutosaveSnapshot } from "@/lib/mame/autosaveSnapshot";

export type AppState = InputSlice & AnalysisSlice & ExportSlice & PhaseSlice & NavigationSlice & {
  runScope?: MameRunScope;
  janusRunScope?: MameRunScope;
  analyzeResult?: AnalyzeResult | null;
  resequenceSnapshot?: MameAutosaveSnapshot | null;
};
