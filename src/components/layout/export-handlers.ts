import { open, save } from "@tauri-apps/plugin-dialog";
import { sendRequest } from "../../lib/ipc-kuro";
import { useAppStore } from "../../store/appStore";
import { getSortedMutations, reorderMappings } from "../../lib/plate-utils";
import { defaultExportFilename } from "../../lib/filename";
import type { BenchmarkResult, WorkspaceData } from "../../types/models";
import {
  migrateWorkspace,
} from "../../lib/workspaceMigrate";
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

  await useAppStore.getState().enqueueJob("export", `${label} mapping export`, async () => {
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
      throw err;
    } finally {
      useAppStore.setState({ isExporting: false });
    }
  });
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

// ---------------------------------------------------------------------------
// Export All + Macrogen (spec 2026-05-13)
// ---------------------------------------------------------------------------

export interface ExportAllUiParams {
  projectId?: string;
  fwdPlateName?: string;
  rvsPlateName?: string;
  amount: "0.05" | "0.2";
  echoTransferVol: number;
  janusTransferVol: number;
  bom: boolean;
}

/**
 * Prompt user for an output directory and invoke the kuro sidecar `export_all`
 * RPC. Returns null when the directory picker is cancelled.
 */
export async function handleExportAll(
  params: ExportAllUiParams,
): Promise<{ success: string[]; failed: { path: string; reason: string }[]; output_dir: string } | null> {
  const dir = await open({ directory: true, multiple: false });
  if (!dir || typeof dir !== "string") {
    return null;
  }
  return sendRequest("export_all", {
    project_id: params.projectId,
    output_dir: dir,
    fwd_plate_name: params.fwdPlateName ?? "",
    rev_plate_name: params.rvsPlateName ?? "",
    amount: params.amount,
    echo_transfer_vol: params.echoTransferVol,
    janus_transfer_vol: params.janusTransferVol,
    bom: params.bom,
  });
}

/**
 * Invoke kuro sidecar `export_macrogen` RPC. Caller is responsible for the
 * output path (typically via the save dialog).
 */
export async function handleExportMacrogen(args: {
  projectId?: string;
  outputPath: string;
  fwdPlateName?: string;
  rvsPlateName?: string;
  amount?: "0.05" | "0.2";
}): Promise<{ ok: true; path: string }> {
  return sendRequest("export_macrogen", {
    project_id: args.projectId,
    output_path: args.outputPath,
    fwd_plate_name: args.fwdPlateName ?? "",
    rev_plate_name: args.rvsPlateName ?? "",
    amount: args.amount ?? "0.05",
    purification: "MOPC",
  });
}
