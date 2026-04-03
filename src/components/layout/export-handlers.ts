import { open, save } from "@tauri-apps/plugin-dialog";
import { sendRequest } from "../../lib/ipc";
import { useAppStore } from "../../store/appStore";

export async function handleExportExcel() {
  const path = await save({
    filters: [{ name: "Excel", extensions: ["xlsx"] }],
  });
  if (path) await useAppStore.getState().exportExcel(path);
}

export async function handleExportIdtOrder() {
  const path = await save({
    filters: [{ name: "CSV", extensions: ["csv"] }],
    defaultPath: "idt_order.csv",
  });
  if (path) {
    try {
      await sendRequest("export_order", { filepath: path, format: "idt" });
      useAppStore.getState().setStatus(`IDT order exported: ${path}`);
    } catch (err) {
      useAppStore.getState().setStatus(`IDT export failed: ${err instanceof Error ? err.message : String(err)}`);
    }
  }
}

export async function handleExportTwistOrder() {
  const path = await save({
    filters: [{ name: "CSV", extensions: ["csv"] }],
    defaultPath: "twist_order.csv",
  });
  if (path) {
    try {
      await sendRequest("export_order", { filepath: path, format: "twist" });
      useAppStore.getState().setStatus(`Twist order exported: ${path}`);
    } catch (err) {
      useAppStore.getState().setStatus(`Twist export failed: ${err instanceof Error ? err.message : String(err)}`);
    }
  }
}

export async function handleExportEchoMapping() {
  const path = await save({
    filters: [{ name: "CSV", extensions: ["csv"] }],
    defaultPath: "echo_mapping.csv",
  });
  if (path) {
    try {
      await sendRequest("export_mapping", { filepath: path, format: "echo" });
      useAppStore.getState().setStatus(`Echo mapping exported: ${path}`);
    } catch (err) {
      useAppStore.getState().setStatus(`Echo mapping export failed: ${err instanceof Error ? err.message : String(err)}`);
    }
  }
}

export async function handleExportJanusMapping() {
  const path = await save({
    filters: [{ name: "CSV", extensions: ["csv"] }],
    defaultPath: "janus_mapping.csv",
  });
  if (path) {
    try {
      await sendRequest("export_mapping", { filepath: path, format: "janus" });
      useAppStore.getState().setStatus(`JANUS mapping exported: ${path}`);
    } catch (err) {
      useAppStore.getState().setStatus(`JANUS mapping export failed: ${err instanceof Error ? err.message : String(err)}`);
    }
  }
}

export async function handleSaveWorkspace() {
  try {
    const path = await save({
      filters: [{ name: "KURO Workspace", extensions: ["kuro.json"] }],
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
      filters: [{ name: "KURO Workspace", extensions: ["kuro.json", "json"] }],
      multiple: false,
    });
    if (!path) return;
    const ws = await sendRequest<import("../../types/models").WorkspaceData>("load_workspace", { filepath: path as string });
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
      defaultPath: "kuro_benchmark.json",
    });
    if (!path) return;
    await sendRequest("save_workspace", { filepath: path, data });
    useAppStore.getState().setStatus(`Benchmark JSON saved: ${path}`);
  } catch (err) {
    useAppStore.getState().setStatus(`Benchmark JSON save failed: ${err instanceof Error ? err.message : String(err)}`);
  }
}

export async function handleExportBenchmarkCsv(results: Record<string, unknown>) {
  try {
    const path = await save({
      filters: [{ name: "CSV", extensions: ["csv"] }],
      defaultPath: "kuro_benchmark.csv",
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
  if (path) await useAppStore.getState().loadSequence(path as string);
}
