import { open, save } from "@tauri-apps/plugin-dialog";
import { sendRequest } from "../../lib/ipc";
import { useAppStore } from "../../store/appStore";
import { getSortedMutations, reorderMappings } from "../../lib/plate-utils";
import { defaultExportFilename } from "../../lib/filename";
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

export async function handleExportExcel() {
  const path = await save({
    filters: [{ name: "Excel", extensions: ["xlsx"] }],
    defaultPath: defaultExportFilename({ target: "KURO", ext: "xlsx" }),
  });
  if (path) await useAppStore.getState().exportExcel(path);
}

export async function handleExportIdtOrder() {
  const path = await save({
    filters: [{ name: "CSV", extensions: ["csv"] }],
    defaultPath: defaultExportFilename({ target: "IDT", ext: "csv" }),
  });
  if (path) {
    try {
      const { results } = getCurrentExportState();
      await sendRequest("export_order", { filepath: path, format: "idt", results });
      useAppStore.getState().setStatus(`IDT order exported: ${path}`);
    } catch (err) {
      useAppStore.getState().setStatus(`IDT export failed: ${err instanceof Error ? err.message : String(err)}`);
    }
  }
}

export async function handleExportTwistOrder() {
  const path = await save({
    filters: [{ name: "CSV", extensions: ["csv"] }],
    defaultPath: defaultExportFilename({ target: "Twist", ext: "csv" }),
  });
  if (path) {
    try {
      const { results } = getCurrentExportState();
      await sendRequest("export_order", { filepath: path, format: "twist", results });
      useAppStore.getState().setStatus(`Twist order exported: ${path}`);
    } catch (err) {
      useAppStore.getState().setStatus(`Twist export failed: ${err instanceof Error ? err.message : String(err)}`);
    }
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

export async function handleSaveWorkspace() {
  try {
    const path = await save({
      filters: [{ name: "KURO Workspace", extensions: ["json"] }],
      defaultPath: defaultExportFilename({ target: "workspace", ext: "kuro.json" }),
    });
    if (!path) return;
    const workspace = useAppStore.getState().getWorkspaceSnapshot();
    await sendRequest("save_workspace", { filepath: path, data: workspace });
    useAppStore.getState().setStatus(`Workspace saved: ${path}`);
  } catch (err) {
    useAppStore.getState().setStatus(`Save failed: ${err instanceof Error ? err.message : String(err)}`);
  }
}

export async function handleLoadWorkspace() {
  try {
    const path = await open({
      filters: [{ name: "KURO Workspace", extensions: ["json"] }],
      multiple: false,
    });
    if (typeof path !== "string") return;
    const ws = await sendRequest("load_workspace", { filepath: path });
    if (ws.version !== 1 && ws.version !== 2) {
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
