import type { InputSlice } from "./slices/inputSlice";
import type { DesignSlice } from "./slices/designSlice";
import type { ExportSlice } from "./slices/exportSlice";

export type AppState = InputSlice & DesignSlice & ExportSlice;
