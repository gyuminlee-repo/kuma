import { useEffect, useState } from "react";
import { getCurrentWebview } from "@tauri-apps/api/webview";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import { selectCanRun } from "@/store/mame/selectors";
import { useMameSidecar } from "@/hooks/mame/useMameSidecar";
import { ClearConfirmDialog } from "../dialogs/ClearConfirmDialog";
import { ExportDialog } from "../dialogs/ExportDialog";
import { MenuBar } from "./MenuBar";
import { Sidebar } from "./Sidebar";
import { StatusBar } from "./StatusBar";
import { PlateView } from "../widgets/PlateView";
import { SummaryRow } from "../widgets/SummaryRow";
import { VerdictTable } from "../widgets/VerdictTable";
import { DataPanel } from "@/components/ui/Panel";

const SEQUENCE_EXTENSIONS = new Set([".fa", ".fasta", ".fna"]);
const XLSX_EXTENSIONS = new Set([".xlsx"]);

export function MameAppLayout() {
  const { status, retry } = useMameSidecar();
  const clearResults = useMameAppStore((s) => s.clearResults);
  const [isDragOver, setIsDragOver] = useState(false);
  const [clearConfirmOpen, setClearConfirmOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let unlisten: (() => void) | undefined;
    getCurrentWebview()
      .onDragDropEvent((event) => {
        if (event.payload.type === "enter" || event.payload.type === "over") {
          setIsDragOver(true);
        } else if (event.payload.type === "leave") {
          setIsDragOver(false);
        } else if (event.payload.type === "drop") {
          setIsDragOver(false);
          for (const filePath of event.payload.paths) {
            const ext = filePath.slice(filePath.lastIndexOf(".")).toLowerCase();
            if (SEQUENCE_EXTENSIONS.has(ext)) {
              useMameAppStore.getState().setReferencePath(filePath);
              break;
            }
            if (XLSX_EXTENSIONS.has(ext)) {
              window.dispatchEvent(
                new CustomEvent("kuma:mame-xlsx-dropped", { detail: { path: filePath } }),
              );
              useMameAppStore.getState().setExpectedPath(filePath);
              break;
            }
          }
        }
      })
      .then((fn) => {
        if (cancelled) fn();
        else unlisten = fn;
      })
      .catch((err) => {
        console.warn("[AppLayout] onDragDropEvent failed:", err);
      });
    return () => {
      cancelled = true;
      unlisten?.();
    };
  }, []);

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (!(e.metaKey || e.ctrlKey)) return;
      if (!(e.target instanceof Element)) return;
      const tag = e.target.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      const s = useMameAppStore.getState();
      switch (e.key.toLowerCase()) {
        case "o":
          e.preventDefault();
          void s.loadWorkspace();
          break;
        case "s":
          e.preventDefault();
          void s.saveWorkspace();
          break;
        case "e":
          e.preventDefault();
          if (s.verdicts.length > 0) s.openExport();
          break;
        case "d":
          e.preventDefault();
          if (selectCanRun(s)) void s.runAnalysis();
          break;
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  return (
    <div
      className={`flex h-full flex-col bg-background ${isDragOver ? "ring-2 ring-inset ring-ring" : ""}`}
    >
      <MenuBar onClearRequest={() => setClearConfirmOpen(true)} />

      <div className="flex flex-1 gap-3 overflow-hidden p-3">
        <Sidebar onClearRequest={() => setClearConfirmOpen(true)} />

        <main
          className="grid min-h-0 flex-1 grid-rows-[auto_minmax(0,1fr)_320px] gap-3 overflow-hidden"
          role="main"
          aria-label="Analysis workspace"
        >
          <SummaryRow />
          <DataPanel title="Verdict table" className="min-h-0">
            <VerdictTable />
          </DataPanel>
          <DataPanel title="Plate plan">
            <PlateView />
          </DataPanel>
        </main>
      </div>

      <StatusBar sidecarStatus={status} onRetry={retry} />

      <ExportDialog />
      <ClearConfirmDialog
        open={clearConfirmOpen}
        onOpenChange={setClearConfirmOpen}
        onConfirm={clearResults}
      />
    </div>
  );
}

