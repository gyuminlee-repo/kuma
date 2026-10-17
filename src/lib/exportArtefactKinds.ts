import type { ExportArtefactKind } from "../types/models";

/** Default selection for a project created after export-file selection existed. */
export const DEFAULT_EXPORT_ARTEFACT_KINDS: readonly ExportArtefactKind[] = ["macrogen", "primers", "echo"];

/**
 * Selection for a workspace or autosave saved before the selection was stored.
 * Export all wrote every kind then, so restoring such a save keeps doing so.
 */
export const LEGACY_EXPORT_ARTEFACT_KINDS: readonly ExportArtefactKind[] = ["macrogen", "primers", "echo", "janus"];
