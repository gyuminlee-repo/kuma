import i18next from "i18next";
import { sendRequest } from "./ipc-kuro";
import type { WorkspaceData } from "@/types/models";

/** Throws when `ws` predates the oldest schema `restoreWorkspace` can read (0.3). */
export function assertRestorableWorkspace(ws: WorkspaceData): void {
  const { schema_version } = ws as WorkspaceData & { schema_version?: string };
  if (!schema_version || schema_version < "0.3") {
    throw new Error(i18next.t("exportSlice.legacyWorkspaceUnsupported"));
  }
}

/**
 * Reads a `.kuro.json` workspace file and checks that it can be restored, so a
 * broken file is refused where it was picked instead of after a session has
 * opened on it.
 */
export async function loadWorkspaceFile(filepath: string): Promise<WorkspaceData> {
  const ws = await sendRequest("load_workspace", { filepath });
  assertRestorableWorkspace(ws);
  return ws;
}
