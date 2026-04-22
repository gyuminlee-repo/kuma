import { lazy, Suspense, useCallback, useEffect, useState } from "react";
import { getCurrentWebview } from "@tauri-apps/api/webview";
import { useAppStore } from "../../store/appStore";
import { useSidecar } from "../../hooks/useSidecar";
import { InputPanel } from "../panels/InputPanel";
import { ParameterPanel } from "../panels/ParameterPanel";
import { ResultTable } from "../widgets/ResultTable";
import { SequenceViewer } from "../widgets/SequenceViewer";
import { PlateMap } from "../widgets/PlateMap";
import { Button } from "../ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "../ui/dialog";
import { MenuBar } from "./MenuBar";
import { StatusBar } from "./StatusBar";
import {
  handleExportExcel,
  handleSaveWorkspace,
  handleOpenSequence,
} from "./export-handlers";

const SEQUENCE_EXTENSIONS = new Set([".gb", ".gbk", ".gbff", ".dna", ".fa", ".fasta"]);
const CSV_EXTENSIONS = new Set([".csv"]);
const LazyDesignReport = lazy(async () => import("../dialogs/DesignReport").then((m) => ({ default: m.DesignReport })));
const LazyBenchmarkDialog = lazy(async () => import("../dialogs/BenchmarkDialog").then((m) => ({ default: m.BenchmarkDialog })));

export function AppLayout() {
  const { status: sidecarStatus, retry: retrySidecar } = useSidecar();
  const isDesigning = useAppStore((s) => s.isDesigning);
  const statusMessage = useAppStore((s) => s.statusMessage);
  const hasSequence = useAppStore((s) => Boolean(s.seqInfo));
  const hasMutationText = useAppStore((s) => s.mutationText.trim().length > 0);
  const hasDesignResults = useAppStore((s) => s.designResults.length > 0);
  const successCount = useAppStore((s) => s.successCount);
  const totalCount = useAppStore((s) => s.totalCount);
  const seqInfo = useAppStore((s) => s.seqInfo);
  const selectedGene = useAppStore((s) => s.selectedGene);
  const loadPolymerases = useAppStore((s) => s.loadPolymerases);
  const showReport = useAppStore((s) => s.showReport);
  const showBenchmark = useAppStore((s) => s.showBenchmark);
  const [clearConfirmOpen, setClearConfirmOpen] = useState(false);
  const [isDragOver, setIsDragOver] = useState(false);

  const selectedGeneInfo = seqInfo?.genes.find((gene) => String(gene.cds_start) === selectedGene);
  const plateEstimate = totalCount > 0 ? Math.ceil(totalCount / 96) : null;

  useEffect(() => {
    if (sidecarStatus === "ready") {
      void loadPolymerases();
    }
  }, [loadPolymerases, sidecarStatus]);

  // File drop via Tauri webview API
  useEffect(() => {
    let unlisten: (() => void) | undefined;
    getCurrentWebview()
      .onDragDropEvent((event) => {
        if (event.payload.type === "enter" || event.payload.type === "over") {
          setIsDragOver(true);
        } else if (event.payload.type === "leave") {
          setIsDragOver(false);
        } else if (event.payload.type === "drop") {
          setIsDragOver(false);
          const paths = event.payload.paths;
          for (const filePath of paths) {
            const ext = filePath.slice(filePath.lastIndexOf(".")).toLowerCase();
            if (SEQUENCE_EXTENSIONS.has(ext)) {
              useAppStore.getState().loadSequence(filePath);
              break;
            }
            if (CSV_EXTENSIONS.has(ext)) {
              useAppStore.getState().loadEvolveproCsv(filePath);
              break;
            }
          }
        }
      })
      .then((fn) => {
        unlisten = fn;
      });
    return () => {
      unlisten?.();
    };
  }, []);

  // Keyboard shortcuts
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    const mod = e.metaKey || e.ctrlKey;
    if (!mod) return;
    // Skip when input/textarea is focused
    if (!(e.target instanceof Element)) return;
    const tag = e.target.tagName;
    const isInput = tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";

    switch (e.key.toLowerCase()) {
      case "s":
        e.preventDefault();
        handleSaveWorkspace();
        break;
      case "e":
        if (isInput) return;
        e.preventDefault();
        if (useAppStore.getState().designResults.length > 0) handleExportExcel();
        break;
      case "d":
        if (isInput) return;
        e.preventDefault();
        {
          const s = useAppStore.getState();
          if (s.seqInfo && !s.isDesigning && s.mutationText.trim()) s.designPrimers();
        }
        break;
      case "o":
        e.preventDefault();
        handleOpenSequence();
        break;
    }
  }, []);

  useEffect(() => {
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);

  return (
    <div className={`flex h-screen flex-col bg-[linear-gradient(180deg,rgba(248,244,237,0.72),rgba(244,241,235,0.9))] ${isDragOver ? "ring-2 ring-inset ring-ring" : ""}`}>
      <MenuBar />

      <div className="flex flex-1 overflow-hidden px-3 pb-3 pt-2">
        <div className="grid flex-1 grid-cols-[var(--sidebar-w,320px)_1fr] gap-3 overflow-hidden">
          <aside
            data-testid="sidebar"
            className="flex min-h-0 flex-col overflow-hidden rounded-[22px] border border-zinc-900/8 bg-[linear-gradient(180deg,rgba(255,255,255,0.96),rgba(250,248,244,0.98))] shadow-[0_18px_38px_rgba(24,24,27,0.08)]"
          >
            <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3 space-y-3">
              <InputPanel />
              <ParameterPanel />
            </div>

            <div className="border-t border-zinc-900/8 bg-[linear-gradient(180deg,rgba(245,242,236,0.92),rgba(255,255,255,0.88))] px-4 py-3">
              <div className="mb-2 rounded-2xl border border-zinc-900/8 bg-white/90 px-3 py-2 shadow-[0_8px_20px_rgba(24,24,27,0.06)]">
                <div className="text-[10px] font-medium uppercase tracking-[0.18em] text-zinc-500">Status</div>
                <div className="mt-0.5 text-sm font-medium text-zinc-900">{statusMessage}</div>
              </div>
              <div className="flex gap-2">
                <Button
                  className="h-9 flex-1 rounded-xl text-sm font-semibold shadow-[0_10px_24px_rgba(24,24,27,0.18)]"
                  onClick={() => useAppStore.getState().designPrimers()}
                  disabled={!hasSequence || isDesigning || !hasMutationText}
                >
                  {isDesigning ? "Designing..." : "Run Design"}
                </Button>
                {isDesigning && (
                  <Button
                    variant="destructive"
                    className="h-9 rounded-md px-3"
                    onClick={() => useAppStore.getState().cancelDesign()}
                  >
                    Cancel
                  </Button>
                )}
              </div>
              <Button
                variant="outline"
                className="mt-2 h-8 w-full rounded-xl border-zinc-300 bg-white/80 text-sm text-zinc-600"
                onClick={() => {
                  if (hasDesignResults) {
                    setClearConfirmOpen(true);
                  } else {
                    useAppStore.getState().resetAll();
                  }
                }}
                disabled={isDesigning}
              >
                Clear All
              </Button>
            </div>
          </aside>

          <main
            data-testid="main-content"
            className="flex min-h-0 flex-col gap-3 overflow-hidden"
          >
            <div className="grid min-h-0 flex-1 grid-rows-[minmax(180px,0.72fr)_minmax(0,1fr)_240px] gap-3 overflow-hidden">
              <div className="overflow-hidden rounded-[24px] border border-zinc-900/8 bg-white/95 shadow-[0_18px_38px_rgba(24,24,27,0.08)]">
                <div className="flex items-center justify-between border-b border-zinc-900/8 bg-[linear-gradient(90deg,rgba(24,24,27,0.98),rgba(39,39,42,0.94))] px-3 py-2">
                  <span className="text-xs font-medium uppercase tracking-[0.14em] text-zinc-300">Sequence Context</span>
                  <span className="text-xs text-zinc-400">
                    {selectedGeneInfo ? `${selectedGeneInfo.gene} · ${selectedGeneInfo.aa_length} aa` : "Load a target gene"}
                  </span>
                </div>
                <div className="h-[calc(100%-33px)]">
                  <SequenceViewer />
                </div>
              </div>

              <div className="min-h-0 overflow-hidden rounded-[24px] border border-zinc-900/8 bg-white/95 shadow-[0_18px_38px_rgba(24,24,27,0.08)]">
                <div className="flex items-center justify-between border-b border-zinc-900/8 bg-[linear-gradient(90deg,rgba(24,24,27,0.98),rgba(39,39,42,0.94))] px-3 py-2">
                  <span className="text-xs font-medium uppercase tracking-[0.14em] text-zinc-300">Design Output</span>
                  <span className="text-xs text-zinc-400">
                    {hasDesignResults ? `${successCount}/${totalCount} successful` : "No results yet"}
                  </span>
                </div>
                <div className="min-h-0 h-[calc(100%-33px)]">
                  <ResultTable />
                </div>
              </div>

              <div className="overflow-hidden rounded-[24px] border border-zinc-900/8 bg-white/95 shadow-[0_18px_38px_rgba(24,24,27,0.08)]">
                <div className="flex items-center justify-between border-b border-zinc-900/8 bg-[linear-gradient(90deg,rgba(24,24,27,0.98),rgba(39,39,42,0.94))] px-3 py-2">
                  <span className="text-xs font-medium uppercase tracking-[0.14em] text-zinc-300">Plate Plan</span>
                  <span className="text-xs text-zinc-400">
                    {plateEstimate ? `${plateEstimate} plate${plateEstimate > 1 ? "s" : ""}` : "Awaiting design"}
                  </span>
                </div>
                <div className="h-[calc(100%-33px)]">
                  <PlateMap />
                </div>
              </div>
            </div>
          </main>
        </div>
      </div>

      <StatusBar sidecarStatus={sidecarStatus} onRetry={retrySidecar} />

      <Dialog open={clearConfirmOpen} onOpenChange={setClearConfirmOpen}>
        <DialogContent className="max-w-xs">
          <DialogHeader>
            <DialogTitle>Clear All</DialogTitle>
            <DialogDescription>
              All design results will be lost. Continue?
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="flex gap-2">
            <Button variant="outline" size="sm" onClick={() => setClearConfirmOpen(false)}>
              Cancel
            </Button>
            <Button size="sm" variant="destructive" onClick={() => {
              useAppStore.getState().resetAll();
              setClearConfirmOpen(false);
            }}>
              Clear
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Suspense fallback={null}>
        {showReport && <LazyDesignReport />}
        {showBenchmark && <LazyBenchmarkDialog />}
      </Suspense>
    </div>
  );
}
