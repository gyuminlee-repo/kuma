/**
 * Slice dependency graph:
 *   sequenceSlice → diversitySlice.searchUniprot
 *   diversitySlice → inputSlice.loadEvolveproCsv, sequenceSlice.seqInfo
 *   inputSlice → diversitySlice.pipelineMode/domains/disabledDomains
 *   designSlice → inputSlice.mutationText, diversitySlice.cancelDiversityReload
 *   exportSlice → all slices (read-only for workspace save/load)
 */
import type { SequenceSlice } from "./slices/sequenceSlice";
import type { DiversitySlice } from "./slices/diversitySlice";
import type { InputSlice } from "./slices/inputSlice";
import type { DesignSlice } from "./slices/designSlice";
import type { ExportSlice } from "./slices/exportSlice";

export type AppState = SequenceSlice & DiversitySlice & InputSlice & DesignSlice & ExportSlice;
