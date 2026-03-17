import { useState } from "react";
import { open, save } from "@tauri-apps/plugin-dialog";
import { sendRequest } from "../../lib/ipc";
import { useAppStore } from "../../store/appStore";
import { useSidecar } from "../../hooks/useSidecar";
import { InputPanel } from "../panels/InputPanel";
import { ParameterPanel } from "../panels/ParameterPanel";
import { ResultTable } from "../widgets/ResultTable";
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
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
} from "../ui/dropdown-menu";
import { Progress } from "../ui/progress";

function MenuBar() {
  const designResults = useAppStore((s) => s.designResults);
  const [aboutOpen, setAboutOpen] = useState(false);

  async function handleExportTsv() {
    const path = await save({
      filters: [{ name: "TSV", extensions: ["tsv"] }],
    });
    if (path) await useAppStore.getState().exportTsv(path);
  }

  async function handleExportExcel() {
    const path = await save({
      filters: [{ name: "Excel", extensions: ["xlsx"] }],
    });
    if (path) await useAppStore.getState().exportExcel(path);
  }

  async function handleSaveWorkspace() {
    const path = await save({
      filters: [{ name: "KURO Workspace", extensions: ["kuro.json"] }],
    });
    if (!path) return;
    const s = useAppStore.getState();
    const workspace = {
      version: 1,
      fastaPath: s.fastaPath,
      mutationInputMode: s.mutationInputMode,
      mutationText: s.mutationText,
      evolveproCsvPath: s.evolveproCsvPath,
      selectedGene: s.selectedGene,
      codonStrategy: s.codonStrategy,
      maxPrimers: s.maxPrimers,
      designResults: s.designResults,
      successCount: s.successCount,
      totalCount: s.totalCount,
      failedMutations: s.failedMutations,
      plateMappings: s.plateMappings,
      dedupInfo: s.dedupInfo,
      tableSorting: s.tableSorting,
      manuallySwapped: s.manuallySwapped,
      customCandidates: s.customCandidates,
      tmFwdTarget: s.tmFwdTarget,
      tmRevTarget: s.tmRevTarget,
      tmOverlapTarget: s.tmOverlapTarget,
      gcMin: s.gcMin,
      gcMax: s.gcMax,
    };
    await sendRequest("save_workspace", { filepath: path, data: workspace });
    useAppStore.setState({ statusMessage: `Workspace saved: ${path}` });
  }

  async function handleLoadWorkspace() {
    const path = await open({
      filters: [{ name: "KURO Workspace", extensions: ["kuro.json", "json"] }],
      multiple: false,
    });
    if (!path) return;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const ws: any = await sendRequest("load_workspace", { filepath: path as string });
    if (ws.version !== 1) {
      useAppStore.setState({ statusMessage: "Incompatible workspace version" });
      return;
    }
    useAppStore.getState().resetAll();
    useAppStore.setState({
      mutationInputMode: ws.mutationInputMode ?? "text",
      mutationText: ws.mutationText ?? "",
      evolveproCsvPath: ws.evolveproCsvPath ?? "",
      codonStrategy: ws.codonStrategy ?? "closest",
      maxPrimers: ws.maxPrimers ?? 95,
    });

    // Restore sequence file + selectedGene
    if (ws.fastaPath) {
      await useAppStore.getState().loadSequence(ws.fastaPath as string);
      // Validate selectedGene against loaded genes
      if (ws.selectedGene) {
        const seqInfo = useAppStore.getState().seqInfo;
        const geneExists = seqInfo?.genes.some(
          (g) => String(g.cds_start) === String(ws.selectedGene),
        );
        if (geneExists) {
          useAppStore.setState({ selectedGene: ws.selectedGene as string });
        }
      }
    }

    // Restore UI state first (shows previous results immediately)
    useAppStore.setState({
      designResults: ws.designResults ?? [],
      successCount: ws.successCount ?? 0,
      totalCount: ws.totalCount ?? 0,
      failedMutations: ws.failedMutations ?? [],
      plateMappings: ws.plateMappings ?? [],
      dedupInfo: ws.dedupInfo ?? {},
      tableSorting: ws.tableSorting ?? [],
      manuallySwapped: ws.manuallySwapped ?? {},
      customCandidates: ws.customCandidates ?? {},
      tmFwdTarget: ws.tmFwdTarget ?? 62,
      tmRevTarget: ws.tmRevTarget ?? 58,
      tmOverlapTarget: ws.tmOverlapTarget ?? 42,
      gcMin: ws.gcMin ?? 40,
      gcMax: ws.gcMax ?? 60,
      statusMessage: `Workspace loaded. Re-designing to sync backend...`,
    });

    // Re-design to sync sidecar state (_last_results, _last_candidates)
    // This enables Export and Candidate features
    if (ws.mutationText && ws.fastaPath) {
      await useAppStore.getState().designPrimers();
    }
  }

  return (
    <>
      <div className="flex items-center gap-1 px-4 py-1 bg-gray-100 border-b border-gray-300 text-xs">
        <span className="font-black text-sm mr-4 text-gray-900 tracking-wide">
          KURO
        </span>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button className="px-2 py-0.5 hover:bg-gray-200 rounded">
              File
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start">
            <DropdownMenuItem onClick={handleSaveWorkspace}>
              Save Workspace...
            </DropdownMenuItem>
            <DropdownMenuItem onClick={handleLoadWorkspace}>
              Load Workspace...
            </DropdownMenuItem>
            <DropdownMenuItem className="h-px bg-gray-200 my-1 p-0" disabled />
            <DropdownMenuItem
              onClick={handleExportTsv}
              disabled={designResults.length === 0}
            >
              Export TSV...
            </DropdownMenuItem>
            <DropdownMenuItem
              onClick={handleExportExcel}
              disabled={designResults.length === 0}
            >
              Export Excel...
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button className="px-2 py-0.5 hover:bg-gray-200 rounded">
              Help
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start">
            <DropdownMenuItem onClick={() => setAboutOpen(true)}>
              About
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <Dialog open={aboutOpen} onOpenChange={setAboutOpen}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>About KURO</DialogTitle>
            <DialogDescription>
              KURO v0.6.0
              <br />
              SDM primer batch design tool with Tm-guided overlap extension.
              <br />
              <br />
              Built with Tauri + React + primer3-py
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button size="sm" onClick={() => setAboutOpen(false)}>
              OK
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

function StatusBar() {
  const { status: sidecarStatus } = useSidecar();
  const isDesigning = useAppStore((s) => s.isDesigning);
  const progress = useAppStore((s) => s.progress);
  const statusMessage = useAppStore((s) => s.statusMessage);
  const successCount = useAppStore((s) => s.successCount);
  const totalCount = useAppStore((s) => s.totalCount);
  const designResults = useAppStore((s) => s.designResults);

  const tmOkCount = designResults.filter((r) => r.tm_condition_met).length;

  return (
    <div className="flex items-center gap-2 px-4 py-1 bg-gray-100 border-t border-gray-300 text-xs text-gray-600">
      <span className="flex-1 truncate">{statusMessage}</span>
      {totalCount > 0 && (
        <span className="text-gray-500">
          {successCount}/{totalCount} designed | Tm OK: {tmOkCount}/
          {successCount}
        </span>
      )}
      {isDesigning && <Progress value={progress} className="w-32 h-2" />}
      <span
        className={`w-2 h-2 rounded-full ${
          sidecarStatus === "ready"
            ? "bg-green-500"
            : sidecarStatus === "connecting"
              ? "bg-yellow-500"
              : "bg-red-500"
        }`}
        title={`Sidecar: ${sidecarStatus}`}
      />
    </div>
  );
}

export function AppLayout() {
  const isDesigning = useAppStore((s) => s.isDesigning);
  const seqInfo = useAppStore((s) => s.seqInfo);
  const mutationText = useAppStore((s) => s.mutationText);
  const designResults = useAppStore((s) => s.designResults);
  const [clearConfirmOpen, setClearConfirmOpen] = useState(false);

  return (
    <div className="flex flex-col h-screen">
      <MenuBar />

      <div className="flex flex-1 overflow-hidden">
        {/* Left Sidebar */}
        <div className="w-[340px] flex-shrink-0 overflow-y-auto p-2 space-y-2 border-r border-gray-200">
          <InputPanel />
          <ParameterPanel />

          <Button
            className="w-full"
            onClick={() => useAppStore.getState().designPrimers()}
            disabled={!seqInfo || isDesigning || !mutationText.trim()}
          >
            {isDesigning ? "Designing..." : "Design Primers"}
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="w-full text-gray-500"
            onClick={() => {
              if (designResults.length > 0) {
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

        {/* Right Content */}
        <div className="flex-1 flex flex-col overflow-hidden">
          <div className="flex-1 overflow-hidden">
            <ResultTable />
          </div>
          <div className="h-[280px] flex-shrink-0 border-t border-gray-200">
            <PlateMap />
          </div>
        </div>
      </div>

      <StatusBar />

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
    </div>
  );
}
