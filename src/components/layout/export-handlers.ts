import { open, save } from "@tauri-apps/plugin-dialog";
import { mkdir } from "@tauri-apps/plugin-fs";
import { join } from "@tauri-apps/api/path";
import { sendRequest } from "../../lib/ipc-kuro";
import { useAppStore } from "../../store/appStore";
import { getSortedMutations, reorderMappings } from "../../lib/plate-utils";
import { defaultExportFilename, buildWorkspaceDefaultPath } from "../../lib/filename";
import type { KumaProject } from "../../state/projectContext";
import type { BenchmarkResult, WorkspaceData } from "../../types/models";
import {
  detectWorkspaceVersion,
  migrateWorkspace,
  MIGRATIONS,
} from "../../lib/workspaceMigrate";
import type { MigrateDialogState } from "../dialogs/WorkspaceMigrateDialog";
import { MIGRATE_DIALOG_CLOSED } from "../dialogs/WorkspaceMigrateDialog";
import { revealInOSFolder } from "../../lib/openFolder";
import { fileExists, requestOverwriteConfirm } from "../../lib/overwriteConfirm";
import { toast } from "sonner";

function deriveMappingExportPaths(path: string) {
  const base = path.trim().replace(/\.(xlsx|csv)$/i, "");
  return {
    xlsxPath: `${base}.xlsx`,
    csvPath: `${base}.csv`,
  };
}

function getCurrentExportState() {
  const state = useAppStore.getState();
  const sortedMuts = getSortedMutations(state.designResults, state.tableSorting, {
    yPredMap: state.yPredMap,
    customCandidates: state.customCandidates,
  });
  return {
    results: state.designResults.map((r) => ({
      mutation: r.mutation,
      forward_seq: r.forward_seq,
      reverse_seq: r.reverse_seq,
    })),
    orderedMappings: reorderMappings(state.plateMappings, state.dedupInfo, sortedMuts),
    dedupInfo: state.dedupInfo,
  };
}

/**
 * Core export: writes sdm_primers.xlsx to `targetPath` via the store action.
 * Auto-overwrite without confirmation (caller is responsible for path selection).
 */
async function exportSdmPrimersExcel(targetPath: string, projectId?: string): Promise<void> {
  await useAppStore.getState().exportExcel(targetPath, projectId);
}

export async function handleExportExcel(projectId?: string) {
  const path = await save({
    filters: [{ name: "Excel", extensions: ["xlsx"] }],
    defaultPath: defaultExportFilename({ target: "KURO", ext: "xlsx" }),
  });
  if (!path) return;

  // §5 덮어쓰기 confirm (OS dialog 외 앱 레벨 추가 검사)
  if (await fileExists(path)) {
    const decision = await requestOverwriteConfirm(path);
    if (decision === "cancel") return;
  }

  await exportSdmPrimersExcel(path, projectId);

  // §5 Open folder 버튼이 있는 toast
  toast.success("Export saved", {
    description: "Run sequencing, then switch to Mame tab to verify →",
    duration: 6000,
    action: {
      label: "Open folder",
      onClick: () => void revealInOSFolder(path),
    },
  });
}

/**
 * Export All (Feature C): saves sdm_primers.xlsx to {project.path}/design/
 * without a save dialog. Auto-overwrites existing file.
 */
export async function handleExportAll(project: KumaProject | null | undefined): Promise<void> {
  if (!project || project.scratch || !project.path) {
    toast.error("Open a project first to use Export All.");
    return;
  }

  const state = useAppStore.getState();
  if (state.designResults.length === 0) {
    toast.error("No design results to export.");
    return;
  }

  const designDir = await join(project.path, "design");
  const targetPath = await join(designDir, "sdm_primers.xlsx");

  useAppStore.setState({ isExporting: true });
  try {
    await mkdir(designDir, { recursive: true });
    await exportSdmPrimersExcel(targetPath, project.project_id);

    toast.success("Exported sdm_primers.xlsx", {
      description: "design/sdm_primers.xlsx",
      duration: 6000,
      action: {
        label: "Open folder",
        onClick: () => void revealInOSFolder(targetPath),
      },
    });
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    toast.error(`Export All failed: ${msg}`);
    state.setStatus(`Export All failed: ${msg}`);
  } finally {
    useAppStore.setState({ isExporting: false });
  }
}

export async function handleExportMappingWithParams(
  format: "echo" | "janus",
  params: { transferVol: number; bom: boolean },
) {
  const target = format === "echo" ? "Echo" : "JANUS";
  const selectedPath = await save({
    filters: [{ name: "Excel", extensions: ["xlsx"] }],
    defaultPath: defaultExportFilename({ target, ext: "xlsx" }),
  });
  if (!selectedPath) return;
  const { xlsxPath, csvPath } = deriveMappingExportPaths(selectedPath);
  const label = format === "echo" ? "Echo" : "JANUS";

  // §5 덮어쓰기 confirm
  if (await fileExists(xlsxPath)) {
    const decision = await requestOverwriteConfirm(xlsxPath);
    if (decision === "cancel") return;
  }

  useAppStore.setState({ isExporting: true });
  try {
    const { orderedMappings, dedupInfo } = getCurrentExportState();
    const payload = {
      format,
      transfer_vol: params.transferVol,
      mappings: orderedMappings,
      dedup_info: dedupInfo,
      bom: params.bom,
    };
    await sendRequest("export_mapping", { ...payload, filepath: xlsxPath });
    await sendRequest("export_mapping", { ...payload, filepath: csvPath });
    useAppStore.getState().setStatus(`${label} mapping exported: ${xlsxPath} + .csv`);

    // §5 Open folder toast
    toast.success(`${label} mapping exported`, {
      description: xlsxPath,
      duration: 6000,
      action: {
        label: "Open folder",
        onClick: () => void revealInOSFolder(xlsxPath),
      },
    });
  } catch (err) {
    useAppStore
      .getState()
      .setStatus(
        `${label} mapping export failed: ${err instanceof Error ? err.message : String(err)}`,
      );
  } finally {
    useAppStore.setState({ isExporting: false });
  }
}

export async function handleSaveWorkspace(project: KumaProject) {
  try {
    const path = await save({
      filters: [{ name: "KURO Workspace", extensions: ["json"] }],
      defaultPath: buildWorkspaceDefaultPath(project, "kuro"),
    });
    if (!path) return;
    const workspace = useAppStore.getState().getWorkspaceSnapshot();
    await sendRequest("save_workspace", { filepath: path, data: workspace });
    useAppStore.getState().setStatus(`Workspace saved: ${path}`);
  } catch (err) {
    useAppStore.getState().setStatus(`Save failed: ${err instanceof Error ? err.message : String(err)}`);
  }
}

/**
 * §14 Migration-aware workspace loader.
 *
 * If the workspace is schema_version "0.3", loads directly.
 * If older (v1/v2), invokes `onMigrationNeeded` so the caller (MenuBar) can
 * show the migration confirmation modal. The modal's onConfirm callback should
 * call `executeMigrateAndLoad` with the already-fetched data.
 *
 * Returns the raw workspace object only if no migration is needed; otherwise
 * returns undefined (migration flow is handed off to the modal).
 */
export async function handleLoadWorkspace(
  project: KumaProject,
  onMigrationNeeded: (state: MigrateDialogState, rawWs: Record<string, unknown>) => void,
): Promise<void> {
  try {
    const path = await open({
      filters: [{ name: "KURO Workspace", extensions: ["json"] }],
      multiple: false,
      defaultPath: project && !project.scratch && project.path ? project.path : undefined,
    });
    if (typeof path !== "string") return;
    const ws = await sendRequest("load_workspace", { filepath: path });
    const rawWs = ws as unknown as Record<string, unknown>;
    const fromVer = detectWorkspaceVersion(rawWs);

    if (fromVer === "unknown") {
      useAppStore.getState().setStatus("Incompatible workspace version");
      return;
    }

    // Already current — load directly.
    if (fromVer === "0.3") {
      await useAppStore.getState().restoreWorkspace(ws as WorkspaceData);
      return;
    }

    // Older version — hand off to migration modal.
    const targetVer = "0.3";
    const migrationKey = `${fromVer}->${targetVer}`;
    const noPath = !(migrationKey in MIGRATIONS);

    onMigrationNeeded(
      {
        open: true,
        filePath: path,
        fromVersion: fromVer,
        toVersion: targetVer,
        noPath,
      },
      rawWs,
    );
  } catch (err) {
    useAppStore.getState().setStatus(`Load failed: ${err instanceof Error ? err.message : String(err)}`);
  }
}

/**
 * §14 Execute the migration after user confirms in the dialog.
 * 1. Backup the original file as `<path>.backup-<ISO>.json`
 * 2. Apply migration
 * 3. Overwrite original with migrated data
 * 4. Load into store
 *
 * Throws on backup failure (safety-first: never migrate without backup).
 */
export async function executeMigrateAndLoad(
  filePath: string,
  rawWs: Record<string, unknown>,
  fromVer: string,
  toVer: string,
): Promise<void> {
  // Build backup path: same dir, timestamp suffix.
  const ts = new Date().toISOString().replace(/[:.]/g, "-");
  const backupPath = filePath.replace(/\.json$/i, "") + `.backup-${ts}.json`;

  // Step 1: backup via sidecar (Tauri sandboxing — use save_json RPC).
  await sendRequest("save_json", { filepath: backupPath, data: rawWs });

  // Step 2: migrate.
  const migrated = migrateWorkspace(rawWs, fromVer, toVer);

  // Step 3: overwrite original.
  await sendRequest("save_json", { filepath: filePath, data: migrated });

  // Step 4: load.
  await useAppStore.getState().restoreWorkspace(migrated as unknown as WorkspaceData);
}

// Re-export for backward-compat callers that only need the closed sentinel.
export { MIGRATE_DIALOG_CLOSED };

export async function handleSaveBenchmarkJson(data: unknown) {
  const path = await save({
    filters: [{ name: "Benchmark JSON", extensions: ["json"] }],
    defaultPath: defaultExportFilename({ target: "benchmark", ext: "json" }),
  });
  if (!path) return;

  if (await fileExists(path)) {
    const decision = await requestOverwriteConfirm(path);
    if (decision === "cancel") return;
  }

  useAppStore.setState({ isExporting: true });
  try {
    await sendRequest("save_json", { filepath: path, data });
    useAppStore.getState().setStatus(`Benchmark JSON saved: ${path}`);
    toast.success("Benchmark JSON saved", {
      description: path,
      duration: 6000,
      action: { label: "Open folder", onClick: () => void revealInOSFolder(path) },
    });
  } catch (err) {
    useAppStore.getState().setStatus(`Benchmark JSON save failed: ${err instanceof Error ? err.message : String(err)}`);
  } finally {
    useAppStore.setState({ isExporting: false });
  }
}

export async function handleExportBenchmarkCsv(results: Record<string, BenchmarkResult>) {
  const path = await save({
    filters: [{ name: "CSV", extensions: ["csv"] }],
    defaultPath: defaultExportFilename({ target: "benchmark", ext: "csv" }),
  });
  if (!path) return;

  if (await fileExists(path)) {
    const decision = await requestOverwriteConfirm(path);
    if (decision === "cancel") return;
  }

  useAppStore.setState({ isExporting: true });
  try {
    await sendRequest("export_benchmark_csv", { filepath: path, results });
    useAppStore.getState().setStatus(`Benchmark CSV exported: ${path}`);
    toast.success("Benchmark CSV exported", {
      description: path,
      duration: 6000,
      action: { label: "Open folder", onClick: () => void revealInOSFolder(path) },
    });
  } catch (err) {
    useAppStore.getState().setStatus(`Benchmark CSV export failed: ${err instanceof Error ? err.message : String(err)}`);
  } finally {
    useAppStore.setState({ isExporting: false });
  }
}

export async function handleOpenSequence() {
  const path = await open({
    filters: [
      { name: "Sequence (GenBank/SnapGene)", extensions: ["gb", "gbff", "gbk", "dna"] },
      { name: "FASTA", extensions: ["fa", "fasta"] },
      { name: "All Files", extensions: ["*"] },
    ],
    multiple: false,
  });
  if (typeof path === "string") {
    await useAppStore.getState().loadSequence(path);
  }
}
