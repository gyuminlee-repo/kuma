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

function SummaryMetric({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: string;
  tone?: "default" | "success" | "warning";
}) {
  const toneClass =
    tone === "success"
      ? "border-emerald-300/70 bg-emerald-50 text-emerald-900"
      : tone === "warning"
        ? "border-amber-300/70 bg-amber-50 text-amber-900"
        : "border-slate-300/80 bg-white/80 text-slate-900";

  return (
    <div className={`rounded-2xl border px-4 py-3 shadow-sm backdrop-blur ${toneClass}`}>
      <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">{label}</div>
      <div className="mt-1 text-lg font-semibold leading-none">{value}</div>
    </div>
  );
}

function WorkflowStep({
  index,
  title,
  description,
  active,
  complete,
}: {
  index: number;
  title: string;
  description: string;
  active: boolean;
  complete: boolean;
}) {
  return (
    <div
      className={`rounded-2xl border px-3 py-3 transition-colors ${
        active
          ? "border-amber-300 bg-amber-50/90 shadow-sm"
          : complete
            ? "border-emerald-300 bg-emerald-50/80"
            : "border-slate-200 bg-white/70"
      }`}
    >
      <div className="flex items-center gap-3">
        <div
          className={`flex h-7 w-7 items-center justify-center rounded-full text-[11px] font-bold ${
            active
              ? "bg-amber-500 text-white"
              : complete
                ? "bg-emerald-600 text-white"
                : "bg-slate-200 text-slate-600"
          }`}
        >
          {index}
        </div>
        <div>
          <div className="text-sm font-semibold text-slate-900">{title}</div>
          <div className="text-xs text-slate-600">{description}</div>
        </div>
      </div>
    </div>
  );
}

export function AppLayout() {
  const { status: sidecarStatus, retry: retrySidecar } = useSidecar();
  const isDesigning = useAppStore((s) => s.isDesigning);
  const progress = useAppStore((s) => s.progress);
  const statusMessage = useAppStore((s) => s.statusMessage);
  const hasSequence = useAppStore((s) => Boolean(s.seqInfo));
  const seqInfo = useAppStore((s) => s.seqInfo);
  const selectedGene = useAppStore((s) => s.selectedGene);
  const hasMutationText = useAppStore((s) => s.mutationText.trim().length > 0);
  const hasDesignResults = useAppStore((s) => s.designResults.length > 0);
  const successCount = useAppStore((s) => s.successCount);
  const totalCount = useAppStore((s) => s.totalCount);
  const failedMutations = useAppStore((s) => s.failedMutations);
  const loadPolymerases = useAppStore((s) => s.loadPolymerases);
  const showReport = useAppStore((s) => s.showReport);
  const showBenchmark = useAppStore((s) => s.showBenchmark);
  const [clearConfirmOpen, setClearConfirmOpen] = useState(false);
  const [isDragOver, setIsDragOver] = useState(false);

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

  const stage = !hasSequence ? 1 : !hasMutationText ? 2 : !hasDesignResults ? 3 : 4;
  const selectedGeneInfo = seqInfo?.genes.find((gene) => String(gene.cds_start) === selectedGene);
  const plateEstimate = totalCount > 0 ? Math.ceil(totalCount / 96) : null;

  return (
    <div className={`kuro-shell flex h-screen flex-col ${isDragOver ? "ring-2 ring-inset ring-amber-400 bg-amber-50/40" : ""}`}>
      <MenuBar />

      <div className="flex flex-1 overflow-hidden px-4 pb-4 pt-3">
        <div className="grid flex-1 grid-cols-[380px_minmax(0,1fr)] gap-4 overflow-hidden">
          <aside className="kuro-sidebar flex min-h-0 flex-col overflow-hidden rounded-[28px] border border-white/70 bg-white/85 shadow-[0_24px_60px_rgba(18,39,58,0.08)] backdrop-blur">
            <div className="border-b border-slate-200/80 px-5 pb-5 pt-5">
              <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-amber-700">Primer Design Workflow</div>
              <div className="mt-2 text-[28px] font-semibold leading-[1.05] text-slate-950">
                Batch-directed mutagenesis without dashboard clutter.
              </div>
              <div className="mt-2 max-w-sm text-sm leading-6 text-slate-600">
                Guide the operator from sequence intake to exportable plates. The screen should always answer what is loaded, what is missing, and whether the batch is design-ready.
              </div>
              <div className="mt-4 grid grid-cols-2 gap-2">
                <SummaryMetric
                  label="Sequence"
                  value={seqInfo ? `${seqInfo.seq_length.toLocaleString()} bp` : "Not loaded"}
                  tone={hasSequence ? "success" : "default"}
                />
                <SummaryMetric
                  label="Design State"
                  value={isDesigning ? `${Math.round(progress)}% running` : hasDesignResults ? "Results ready" : "Waiting"}
                  tone={isDesigning ? "warning" : hasDesignResults ? "success" : "default"}
                />
                <SummaryMetric
                  label="Target Batch"
                  value={totalCount > 0 ? `${successCount}/${totalCount}` : hasMutationText ? "Prepared" : "No mutations"}
                  tone={hasDesignResults ? "success" : "default"}
                />
                <SummaryMetric
                  label="Plate Estimate"
                  value={plateEstimate ? `${plateEstimate} plate${plateEstimate > 1 ? "s" : ""}` : "Pending"}
                  tone={plateEstimate ? "warning" : "default"}
                />
              </div>
            </div>

            <div className="space-y-3 border-b border-slate-200/80 px-5 py-4">
              <WorkflowStep
                index={1}
                title="Load construct"
                description={hasSequence && seqInfo ? seqInfo.header : "Import a GenBank, SnapGene, or FASTA sequence."}
                active={stage === 1}
                complete={hasSequence}
              />
              <WorkflowStep
                index={2}
                title="Define mutation set"
                description={hasMutationText ? "Mutation batch is present and parseable." : "Enter text mutations or load EVOLVEpro variants."}
                active={stage === 2}
                complete={hasMutationText}
              />
              <WorkflowStep
                index={3}
                title="Tune design policy"
                description={selectedGeneInfo ? `${selectedGeneInfo.gene} • ${selectedGeneInfo.aa_length} aa target window` : "Set gene, organism, polymerase, and design constraints."}
                active={stage === 3}
                complete={hasSequence && hasMutationText}
              />
              <WorkflowStep
                index={4}
                title="Review output"
                description={hasDesignResults ? `${failedMutations.length} failed variants flagged for rescue or retry.` : "Results, candidate swaps, and plate map appear here."}
                active={stage === 4}
                complete={hasDesignResults}
              />
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4 space-y-4">
              <InputPanel />
              <ParameterPanel />
            </div>

            <div className="border-t border-slate-200/80 bg-slate-50/70 px-5 py-4">
              <div className="mb-3 rounded-2xl border border-slate-200 bg-white/80 px-4 py-3">
                <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">Current Status</div>
                <div className="mt-1 text-sm font-medium text-slate-900">{statusMessage}</div>
              </div>
              <div className="flex gap-2">
                <Button
                  className="h-11 flex-1 rounded-xl bg-slate-950 text-sm font-semibold text-white shadow-[0_14px_30px_rgba(15,23,42,0.22)] hover:bg-slate-800"
                  onClick={() => useAppStore.getState().designPrimers()}
                  disabled={!hasSequence || isDesigning || !hasMutationText}
                >
                  {isDesigning ? "Designing..." : "Run Design"}
                </Button>
                {isDesigning && (
                  <Button
                    variant="destructive"
                    className="h-11 rounded-xl px-4"
                    onClick={() => useAppStore.getState().cancelDesign()}
                  >
                    Cancel
                  </Button>
                )}
              </div>
              <Button
                variant="outline"
                className="mt-2 h-10 w-full rounded-xl border-slate-300 bg-white/70 text-slate-600 hover:bg-slate-100"
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

          <main className="flex min-h-0 flex-col gap-4 overflow-hidden">
            <section className="relative overflow-hidden rounded-[30px] border border-slate-200/80 bg-[radial-gradient(circle_at_top_left,_rgba(245,158,11,0.18),_transparent_30%),linear-gradient(135deg,#fff8ef_0%,#fffdf8_46%,#f8fbff_100%)] p-6 shadow-[0_24px_60px_rgba(18,39,58,0.08)]">
              <div className="absolute inset-y-0 right-0 w-1/3 bg-[radial-gradient(circle_at_center,_rgba(148,163,184,0.18),_transparent_62%)]" />
              <div className="relative flex items-start justify-between gap-6">
                <div className="max-w-2xl">
                  <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-amber-700">Representative View</div>
                  <div className="mt-2 text-[32px] font-semibold leading-[1.02] text-slate-950">
                    {hasDesignResults ? "Primer candidates, failures, and plate planning in one scene." : "Set up a batch that is visibly ready before you click design."}
                  </div>
                  <div className="mt-3 text-sm leading-6 text-slate-600">
                    {hasDesignResults
                      ? "Sequence context stays anchored above the ranked result table so swaps, failures, and downstream plate assignments remain connected."
                      : "The first screen now foregrounds the workflow: load a construct, define mutations, tune policy, then run a batch design with clear readiness signals."}
                  </div>
                </div>
                <div className="grid min-w-[300px] grid-cols-2 gap-2">
                  <SummaryMetric
                    label="Target Gene"
                    value={selectedGeneInfo ? selectedGeneInfo.gene : "Not selected"}
                    tone={selectedGeneInfo ? "success" : "default"}
                  />
                  <SummaryMetric
                    label="Failures"
                    value={failedMutations.length > 0 ? String(failedMutations.length) : "0"}
                    tone={failedMutations.length > 0 ? "warning" : "success"}
                  />
                  <SummaryMetric
                    label="Sidecar"
                    value={sidecarStatus === "ready" ? "Connected" : sidecarStatus}
                    tone={sidecarStatus === "ready" ? "success" : "warning"}
                  />
                  <SummaryMetric
                    label="Export Readiness"
                    value={hasDesignResults ? "Ready" : "Pending"}
                    tone={hasDesignResults ? "success" : "default"}
                  />
                </div>
              </div>
            </section>

            <section className="grid min-h-0 flex-1 grid-rows-[minmax(220px,0.72fr)_minmax(0,1fr)_280px] gap-4 overflow-hidden">
              <div className="overflow-hidden rounded-[28px] border border-slate-200/80 bg-white/88 p-4 shadow-[0_16px_44px_rgba(18,39,58,0.08)] backdrop-blur">
                <div className="mb-3 flex items-center justify-between gap-3">
                  <div>
                    <div className="text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-500">Sequence Context</div>
                    <div className="mt-1 text-sm text-slate-600">Domains, mutation density, and outcome distribution stay visible while reviewing results.</div>
                  </div>
                  <div className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-[11px] font-medium text-slate-600">
                    {selectedGeneInfo ? `${selectedGeneInfo.gene} • ${selectedGeneInfo.aa_length} aa` : "Load a target gene"}
                  </div>
                </div>
                <SequenceViewer />
              </div>

              <div className="min-h-0 overflow-hidden rounded-[28px] border border-slate-200/80 bg-white/92 shadow-[0_18px_48px_rgba(18,39,58,0.08)] backdrop-blur">
                <div className="flex items-center justify-between border-b border-slate-200/80 px-5 py-4">
                  <div>
                    <div className="text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-500">Design Output</div>
                    <div className="mt-1 text-sm text-slate-600">Sortable primer set with rescue candidates, failure diagnostics, and manual swaps.</div>
                  </div>
                  <div className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-[11px] font-medium text-slate-600">
                    {hasDesignResults ? `${successCount}/${totalCount} successful` : "No results yet"}
                  </div>
                </div>
                <div className="min-h-0 h-[calc(100%-73px)]">
                  <ResultTable />
                </div>
              </div>

              <div className="overflow-hidden rounded-[28px] border border-slate-200/80 bg-white/88 shadow-[0_16px_44px_rgba(18,39,58,0.08)] backdrop-blur">
                <div className="flex items-center justify-between border-b border-slate-200/80 px-5 py-4">
                  <div>
                    <div className="text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-500">Plate Plan</div>
                    <div className="mt-1 text-sm text-slate-600">Downstream export surface for liquid handler mapping and order handoff.</div>
                  </div>
                  <div className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-[11px] font-medium text-slate-600">
                    {plateEstimate ? `${plateEstimate} plate${plateEstimate > 1 ? "s" : ""}` : "Awaiting design"}
                  </div>
                </div>
                <div className="h-[calc(100%-73px)]">
                  <PlateMap />
                </div>
              </div>
            </section>
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
