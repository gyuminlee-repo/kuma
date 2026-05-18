import { open, save } from "@tauri-apps/plugin-dialog";
import { sendRequest } from "../../lib/ipc-kuro";
import { useAppStore } from "../../store/appStore";
import { defaultExportFilename } from "../../lib/filename";
import type { BenchmarkResult, WorkspaceData } from "../../types/models";
import {
  migrateWorkspace,
} from "../../lib/workspaceMigrate";
import { MIGRATE_DIALOG_CLOSED } from "../dialogs/WorkspaceMigrateDialog";
import { revealInOSFolder } from "../../lib/openFolder";
import { fileExists, requestOverwriteConfirm } from "../../lib/overwriteConfirm";
import { getSortedMutations, reorderMappings } from "../../lib/plate-utils";
import { toast } from "sonner";

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
  try {
    // Mirror exportExcel: pass UI-capped mappings so Export All respects
    // maxPrimers cap (frontend designResults is the source of truth, backend
    // state may contain uncapped plate_mappings).
    const state = useAppStore.getState();
    const { designResults, plateMappings, dedupInfo, tableSorting } = state;
    const sortedMuts = getSortedMutations(designResults, tableSorting, {
      yPredMap: state.yPredMap,
      customCandidates: state.customCandidates,
    });
    const ordered = reorderMappings(plateMappings, dedupInfo, sortedMuts);
    const resultByMut = new Map(designResults.map((r) => [r.mutation, r]));
    const enriched = ordered.map((m) => {
      const r = resultByMut.get(m.mutation);
      if (!r) return m;
      return {
        ...m,
        tm: m.primer_type === "forward" ? r.tm_no_fwd : r.tm_no_rev,
        tm_overlap: r.tm_overlap,
        wt_codon: r.wt_codon,
        mt_codon: r.mt_codon,
      };
    });

    const result = (await sendRequest("export_all", {
      project_id: params.projectId,
      output_dir: dir,
      fwd_plate_name: params.fwdPlateName ?? "",
      rev_plate_name: params.rvsPlateName ?? "",
      amount: params.amount,
      echo_transfer_vol: params.echoTransferVol,
      janus_transfer_vol: params.janusTransferVol,
      bom: params.bom,
      mappings: enriched,
      dedup_info: dedupInfo,
    })) as { success: string[]; failed: { path: string; reason: string }[]; output_dir: string };

    const successCount = result.success?.length ?? 0;
    const failedCount = result.failed?.length ?? 0;
    const totalCount = successCount + failedCount;
    const outputDir = result.output_dir ?? dir;

    if (failedCount === 0 && successCount > 0) {
      toast.success("Export all complete", {
        description: `${successCount} of ${totalCount} files exported to ${outputDir}`,
        duration: 6000,
        action: { label: "Open folder", onClick: () => void revealInOSFolder(outputDir) },
      });
    } else if (successCount > 0 && failedCount > 0) {
      const firstFailed = result.failed
        .slice(0, 3)
        .map((f) => f.path)
        .join(", ");
      toast.warning("Export all: partial success", {
        description: `${successCount} of ${totalCount} files exported to ${outputDir}. Failed: ${firstFailed}${failedCount > 3 ? ` (+${failedCount - 3} more)` : ""}`,
        duration: 8000,
        action: { label: "Open folder", onClick: () => void revealInOSFolder(outputDir) },
      });
    } else if (failedCount > 0) {
      const firstFailed = result.failed
        .slice(0, 3)
        .map((f) => `${f.path}: ${f.reason}`)
        .join("; ");
      toast.error("Export all failed", {
        description: `0 of ${totalCount} files exported. ${firstFailed}${failedCount > 3 ? ` (+${failedCount - 3} more)` : ""}`,
        duration: 8000,
      });
    } else {
      toast.info("Export all: nothing to export", {
        description: `No files were generated in ${outputDir}.`,
        duration: 6000,
      });
    }

    return result;
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    toast.error("Export all failed", { description: msg, duration: 8000 });
    return null;
  }
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
