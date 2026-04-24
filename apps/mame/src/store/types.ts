import type { AnalysisSlice, ExportSlice, InputSlice } from "./slice-interfaces";

export type AppState = InputSlice & AnalysisSlice & ExportSlice;
