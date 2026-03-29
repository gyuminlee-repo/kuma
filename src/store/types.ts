import type { SequenceSlice } from "./slices/sequenceSlice";
import type { DiversitySlice } from "./slices/diversitySlice";
import type { InputSlice } from "./slices/inputSlice";
import type { DesignSlice } from "./slices/designSlice";
import type { ExportSlice } from "./slices/exportSlice";

export type AppState = SequenceSlice & DiversitySlice & InputSlice & DesignSlice & ExportSlice;
