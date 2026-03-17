import { useEffect, useState } from "react";
import { save } from "@tauri-apps/plugin-dialog";
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

  return (
    <>
      <div className="flex items-center gap-1 px-4 py-1 bg-gray-100 border-b border-gray-300 text-xs">
        <span className="font-bold text-sm mr-4 text-green-700">
          SDMBench
        </span>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button className="px-2 py-0.5 hover:bg-gray-200 rounded">
              File
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start">
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
            <DialogTitle>About SDMBench</DialogTitle>
            <DialogDescription>
              SDMBench v0.1.0
              <br />
              EVOLVEpro SDM primer batch design tool with Tm-guided overlap
              extension.
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
  const { status: sidecarStatus } = useSidecar();
  const fetchPolymerases = useAppStore((s) => s.fetchPolymerases);
  const isDesigning = useAppStore((s) => s.isDesigning);
  const seqInfo = useAppStore((s) => s.seqInfo);

  useEffect(() => {
    if (sidecarStatus === "ready") {
      fetchPolymerases();
    }
  }, [sidecarStatus, fetchPolymerases]);

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
            disabled={!seqInfo || isDesigning}
          >
            {isDesigning ? "Designing..." : "Design Primers"}
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
    </div>
  );
}
