import { useState } from "react";
import { useAppStore } from "../../store/appStore";
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
import { getCrashLog } from "../../lib/crashLog";
import {
  handleExportExcel,
  handleExportIdtOrder,
  handleExportMappingWithParams,
  handleExportTwistOrder,
  handleSaveWorkspace,
  handleLoadWorkspace,
  handleOpenSequence,
} from "./export-handlers";
import { MappingExportDialog } from "../dialogs/MappingExportDialog";

const MOD_KEY = navigator.userAgent.includes("Mac") ? "\u2318" : "Ctrl+";

export function MenuBar() {
  const hasDesignResults = useAppStore((s) => s.designResults.length > 0);
  const [aboutOpen, setAboutOpen] = useState(false);
  const [crashCopied, setCrashCopied] = useState(false);
  const [mappingDialogOpen, setMappingDialogOpen] = useState(false);
  const [mappingDialogFormat, setMappingDialogFormat] = useState<"echo" | "janus">("echo");

  async function handleCopyCrashLog() {
    const log = getCrashLog();
    if (log.length === 0) {
      setCrashCopied(false);
      return;
    }
    const text = log
      .map(
        (e) =>
          `[${e.timestamp}] ${e.component}: ${e.message}${e.stack ? "\n" + e.stack : ""}`,
      )
      .join("\n---\n");
    await navigator.clipboard.writeText(text);
    setCrashCopied(true);
    setTimeout(() => setCrashCopied(false), 2000);
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
              disabled={!hasDesignResults}
            >
              <span className="flex-1">Export Excel...</span>
              <kbd className="ml-4 text-[10px] text-gray-400">{MOD_KEY}E</kbd>
            </DropdownMenuItem>
            <DropdownMenuItem className="h-px bg-gray-200 my-1 p-0" disabled />
            <DropdownMenuItem
              onClick={handleExportIdtOrder}
              disabled={!hasDesignResults}
            >
              Export IDT Order...
            </DropdownMenuItem>
            <DropdownMenuItem
              onClick={handleExportTwistOrder}
              disabled={!hasDesignResults}
            >
              Export Twist Order...
            </DropdownMenuItem>
            <DropdownMenuItem className="h-px bg-gray-200 my-1 p-0" disabled />
            <DropdownMenuItem
              onClick={() => { setMappingDialogFormat("echo"); setMappingDialogOpen(true); }}
              disabled={!hasDesignResults}
            >
              Export Echo Mapping...
            </DropdownMenuItem>
            <DropdownMenuItem
              onClick={() => { setMappingDialogFormat("janus"); setMappingDialogOpen(true); }}
              disabled={!hasDesignResults}
            >
              Export JANUS Mapping...
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

      <MappingExportDialog
        open={mappingDialogOpen}
        initialFormat={mappingDialogFormat}
        onOpenChange={setMappingDialogOpen}
        onExport={({ format, transferVol }) => {
          setMappingDialogOpen(false);
          handleExportMappingWithParams(format, { transferVol });
        }}
      />

      <Dialog open={aboutOpen} onOpenChange={(open: boolean) => {
        setAboutOpen(open);
        if (!open) {
          setCrashCopied(false);
        }
      }}>
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
          <div className="flex flex-col gap-2 mt-2">
            <Button
              size="sm"
              variant="outline"
              onClick={handleCopyCrashLog}
            >
              {crashCopied ? "Copied!" : "Copy Crash Log"}
            </Button>
          </div>
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
