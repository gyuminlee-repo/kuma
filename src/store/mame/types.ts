import type { AnalysisSlice, ExportSlice, InputSlice } from "./slice-interfaces";
import type { PhaseSlice } from "./slices/phaseSlice";
import type { NavigationSlice } from "./slices/navigationSlice";

export type AppState = InputSlice & AnalysisSlice & ExportSlice & PhaseSlice & NavigationSlice;
