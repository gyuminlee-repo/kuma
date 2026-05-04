import { open, save } from "@tauri-apps/plugin-dialog";
import { sendRequest } from "../../lib/ipc-kuro";
import { useAppStore } from "../../store/appStore";
import { getSortedMutations, reorderMappings } from "../../lib/plate-utils";
import { defaultExportFilename, buildWorkspaceDefaultPath } from "../../lib/filename";
import type { KumaProject } from "../../state/projectContext";
import type { BenchmarkResult } from "../../types/models";

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

export async function handleExportExcel(projectId?: string) {
  const path = await save({
    filters: [{ name: "Excel", extensions: ["xlsx"] }],
    defaultPath: defaultExportFilename({ target: "KURO", ext: "xlsx" }),
  });
  if (path) {
    await useAppStore.getState().exportExcel(path, projectId);
    // Item 2: Handoff hint — flash message for 5 s then restore
    const prevMsg = useAppStore.getState().statusMessage;
    useAppStore.getState().setStatus("Export saved. Run sequencing, then Switch to Mame tab to verify →");
    setTimeout(() => {
      // Restore only if no new message has appeared
      if (useAppStore.getState().statusMessage === "Export saved. Run sequencing, then Switch to Mame tab to verify →") {
        useAppStore.getState().setStatus(prevMsg);
      }
    }, 5000);
  }
}

export async function handleExportMappingWithParams(
  format: "echo" | "janus",
  params: { transferVol: number },
) {
  const target = format === "echo" ? "Echo" : "JANUS";
  const selectedPath = await save({
    filters: [{ name: "Excel", extensions: ["xlsx"] }],
    defaultPath: defaultExportFilename({ target, ext: "xlsx" }),
  });
  if (!selectedPath) return;
  const { xlsxPath, csvPath } = deriveMappingExportPaths(selectedPath);

  const label = format === "echo" ? "Echo" : "JANUS";
  try {
    const { orderedMappings, dedupInfo } = getCurrentExportState();
    const payload = {
      format,
      transfer_vol: params.transferVol,
      mappings: orderedMappings,
      dedup_info: dedupInfo,
    };
    await sendRequest("export_mapping", { ...payload, filepath: xlsxPath });
    await sendRequest("export_mapping", { ...payload, filepath: csvPath });
    useAppStore.getState().setStatus(`${label} mapping exported: ${xlsxPath} + .csv`);
  } catch (err) {
    useAppStore
      .getState()
      .setStatus(
        `${label} mapping export failed: ${err instanceof Error ? err.message : String(err)}`,
      );
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

export async function handleLoadWorkspace(project: KumaProject) {
  try {
    const path = await open({
      filters: [{ name: "KURO Workspace", extensions: ["json"] }],
      multiple: false,
      defaultPath: project && !project.scratch && project.path ? project.path : undefined,
    });
    if (typeof path !== "string") return;
    const ws = await sendRequest("load_workspace", { filepath: path });
    const wsTyped = ws as { version?: number; schema_version?: string };
    const hasValidVersion =
      wsTyped.version === 1 ||
      wsTyped.version === 2 ||
      wsTyped.schema_version === "0.3";
    if (!hasValidVersion) {
      useAppStore.getState().setStatus("Incompatible workspace version");
      return;
    }
    await useAppStore.getState().restoreWorkspace(ws);
  } catch (err) {
    useAppStore.getState().setStatus(`Load failed: ${err instanceof Error ? err.message : String(err)}`);
  }
}

export async function handleSaveBenchmarkJson(data: unknown) {
  try {
    const path = await save({
      filters: [{ name: "Benchmark JSON", extensions: ["json"] }],
      defaultPath: defaultExportFilename({ target: "benchmark", ext: "json" }),
    });
    if (!path) return;
    await sendRequest("save_json", { filepath: path, data });
    useAppStore.getState().setStatus(`Benchmark JSON saved: ${path}`);
  } catch (err) {
    useAppStore.getState().setStatus(`Benchmark JSON save failed: ${err instanceof Error ? err.message : String(err)}`);
  }
}

export async function handleExportBenchmarkCsv(results: Record<string, BenchmarkResult>) {
  try {
    const path = await save({
      filters: [{ name: "CSV", extensions: ["csv"] }],
      defaultPath: defaultExportFilename({ target: "benchmark", ext: "csv" }),
    });
    if (!path) return;
    await sendRequest("export_benchmark_csv", { filepath: path, results });
    useAppStore.getState().setStatus(`Benchmark CSV exported: ${path}`);
  } catch (err) {
    useAppStore.getState().setStatus(`Benchmark CSV export failed: ${err instanceof Error ? err.message : String(err)}`);
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
