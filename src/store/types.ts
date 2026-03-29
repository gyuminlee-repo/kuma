import type { SequenceSlice } from "./slices/sequenceSlice";
import type { InputSlice } from "./slices/inputSlice";
import type { DesignSlice } from "./slices/designSlice";
import type { ExportSlice } from "./slices/exportSlice";

export type AppState = SequenceSlice & InputSlice & DesignSlice & ExportSlice;
