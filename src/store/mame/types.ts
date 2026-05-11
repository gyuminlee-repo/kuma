import type { AnalysisSlice, ExportSlice, InputSlice } from "./slice-interfaces";
import type { PhaseSlice } from "./slices/phaseSlice";

export type AppState = InputSlice & AnalysisSlice & ExportSlice & PhaseSlice;
