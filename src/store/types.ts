/**
 * Slice dependency graph:
 *   sequenceSlice → diversitySlice.searchUniprot
 *   diversitySlice → inputSlice.loadEvolveproCsv, sequenceSlice.seqInfo
 *   inputSlice → diversitySlice.pipelineMode/domains/disabledDomains
 *   designSlice → inputSlice.mutationText, diversitySlice.cancelDiversityReload
 *   exportSlice → all slices (read-only for workspace save/load)
 *
 * Interfaces live in slice-interfaces.ts (no slice implementation imports)
 * so that this file does not create a circular import chain with the slices.
 */
import type { SequenceSlice } from "./slice-interfaces";
import type { DiversitySlice } from "./slice-interfaces";
import type { InputSlice } from "./slice-interfaces";
import type { DesignSlice } from "./slice-interfaces";
import type { ExportSlice } from "./slice-interfaces";
import type { NetworkConsentSlice } from "./slice-interfaces";
import type { MemorySlice } from "./slice-interfaces";
import type { JobQueueSlice } from "./slice-interfaces";
import type { LogSlice } from "./slice-interfaces";
import type { NavigationSlice } from "./slices/navigationSlice";

export type AppState = SequenceSlice & DiversitySlice & InputSlice & DesignSlice & ExportSlice & NetworkConsentSlice & MemorySlice & JobQueueSlice & LogSlice & NavigationSlice;
