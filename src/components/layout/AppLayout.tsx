import { useCallback, useEffect, useState } from "react";
import { getCurrentWebview } from "@tauri-apps/api/webview";
import { useAppStore } from "../../store/appStore";
import { useSidecar } from "../../hooks/useSidecar";
import { InputPanel } from "../panels/InputPanel";
import { ParameterPanel } from "../panels/ParameterPanel";
import { ResultTable } from "../widgets/ResultTable";
import { SequenceViewer } from "../widgets/SequenceViewer";
import { PlateMap } from "../widgets/PlateMap";
import { DesignReport } from "../dialogs/DesignReport";
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

export function AppLayout() {
  const { status: sidecarStatus, retry: retrySidecar } = useSidecar();
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

      {/* Design Report Modal */}
      <DesignReport />
    </div>
  );
}
