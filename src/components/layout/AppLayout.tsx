import { useCallback, useEffect, useState } from "react";
import { open, save } from "@tauri-apps/plugin-dialog";
import { getCurrentWebview } from "@tauri-apps/api/webview";
import { sendRequest } from "../../lib/ipc";
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
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
} from "../ui/dropdown-menu";
import { Progress } from "../ui/progress";

const SEQUENCE_EXTENSIONS = new Set([".gb", ".gbk", ".gbff", ".dna", ".fa", ".fasta"]);
const CSV_EXTENSIONS = new Set([".csv"]);

const MOD_KEY = navigator.userAgent.includes("Mac") ? "\u2318" : "Ctrl+";

async function handleExportExcel() {
  const path = await save({
    filters: [{ name: "Excel", extensions: ["xlsx"] }],
  });
  if (path) await useAppStore.getState().exportExcel(path);
}

async function handleExportIdtOrder() {
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

async function handleExportTwistOrder() {
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

async function handleSaveWorkspace() {
  const path = await save({
    filters: [{ name: "KURO Workspace", extensions: ["kuro.json"] }],
  });
  if (!path) return;
  const workspace = useAppStore.getState().getWorkspaceSnapshot();
  await sendRequest("save_workspace", { filepath: path, data: workspace });
  useAppStore.getState().setStatus(`Workspace saved: ${path}`);
}

async function handleLoadWorkspace() {
  const path = await open({
    filters: [{ name: "KURO Workspace", extensions: ["kuro.json", "json"] }],
    multiple: false,
  });
  if (!path) return;
  const ws = await sendRequest<import("../../types/models").WorkspaceV1>("load_workspace", { filepath: path as string });
  if (ws.version !== 1) {
    useAppStore.getState().setStatus("Incompatible workspace version");
    return;
  }
  await useAppStore.getState().restoreWorkspace(ws);
}

async function handleOpenSequence() {
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

function MenuBar() {
  const designResults = useAppStore((s) => s.designResults);
  const [aboutOpen, setAboutOpen] = useState(false);

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
            <DropdownMenuItem onClick={handleOpenSequence}>
              <span className="flex-1">Open Sequence...</span>
              <kbd className="ml-4 text-[10px] text-gray-400">{MOD_KEY}O</kbd>
            </DropdownMenuItem>
            <DropdownMenuItem className="h-px bg-gray-200 my-1 p-0" disabled />
            <DropdownMenuItem onClick={handleSaveWorkspace}>
              <span className="flex-1">Save Workspace...</span>
              <kbd className="ml-4 text-[10px] text-gray-400">{MOD_KEY}S</kbd>
            </DropdownMenuItem>
            <DropdownMenuItem onClick={handleLoadWorkspace}>
              Load Workspace...
            </DropdownMenuItem>
            <DropdownMenuItem className="h-px bg-gray-200 my-1 p-0" disabled />
            <DropdownMenuItem
              onClick={handleExportExcel}
              disabled={designResults.length === 0}
            >
              <span className="flex-1">Export Excel...</span>
              <kbd className="ml-4 text-[10px] text-gray-400">{MOD_KEY}E</kbd>
            </DropdownMenuItem>
            <DropdownMenuItem className="h-px bg-gray-200 my-1 p-0" disabled />
            <DropdownMenuItem
              onClick={handleExportIdtOrder}
              disabled={designResults.length === 0}
            >
              Export IDT Order...
            </DropdownMenuItem>
            <DropdownMenuItem
              onClick={handleExportTwistOrder}
              disabled={designResults.length === 0}
            >
              Export Twist Order...
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
              KURO v{__APP_VERSION__}
              <br />
              SDM primer batch design tool with Tm-guided overlap extension.
              <br />
              <br />
              Built with Tauri + React + primer3-py
              <br />
              <br />
              <a href="https://github.com/gyuminlee-repo/KURO" target="_blank" rel="noopener noreferrer" className="text-blue-600 underline">
                github.com/gyuminlee-repo/KURO
              </a>
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

function StatusBar({ sidecarStatus }: { sidecarStatus: string }) {
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
      {sidecarStatus === "error" && (
        <span className="bg-red-600 text-white text-[10px] px-2 py-0.5 rounded whitespace-nowrap">
          Sidecar connection failed. Restart the app.
        </span>
      )}
      <span
        className={`w-2 h-2 rounded-full flex-shrink-0 ${
          sidecarStatus === "ready"
            ? "bg-green-500"
            : sidecarStatus === "connecting"
              ? "bg-yellow-500"
              : "bg-red-500"
        }`}
        role="status"
        aria-label={`Sidecar: ${sidecarStatus}`}
        title={`Sidecar: ${sidecarStatus}`}
      />
    </div>
  );
}

export function AppLayout() {
  const { status: sidecarStatus } = useSidecar();
  const isDesigning = useAppStore((s) => s.isDesigning);
  const seqInfo = useAppStore((s) => s.seqInfo);
  const mutationText = useAppStore((s) => s.mutationText);
  const designResults = useAppStore((s) => s.designResults);
  const [clearConfirmOpen, setClearConfirmOpen] = useState(false);
  const [isDragOver, setIsDragOver] = useState(false);

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
    const tag = (e.target as HTMLElement).tagName;
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
    <div className={`flex flex-col h-screen ${isDragOver ? "ring-2 ring-inset ring-blue-400 bg-blue-50/30" : ""}`}>
      <MenuBar />

      <div className="flex flex-1 overflow-hidden">
        {/* Left Sidebar */}
        <div className="w-[340px] flex-shrink-0 overflow-y-auto p-2 space-y-2 border-r border-gray-200">
          <InputPanel />
          <ParameterPanel />

          <div className="flex gap-1">
            <Button
              className="flex-1"
              onClick={() => useAppStore.getState().designPrimers()}
              disabled={!seqInfo || isDesigning || !mutationText.trim()}
            >
              {isDesigning ? "Designing..." : "Design Primers"}
            </Button>
            {isDesigning && (
              <Button
                variant="destructive"
                size="sm"
                className="px-3"
                onClick={() => useAppStore.getState().cancelDesign()}
              >
                Cancel
              </Button>
            )}
          </div>
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
          <SequenceViewer />
          <div className="flex-1 overflow-hidden">
            <ResultTable />
          </div>
          <div className="h-[280px] flex-shrink-0 border-t border-gray-200">
            <PlateMap />
          </div>
        </div>
      </div>

      <StatusBar sidecarStatus={sidecarStatus} />

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
