import { useState } from "react";
import { useAppStore } from "../../store/appStore";
import { selectCanRun } from "../../store/selectors";
import { Button } from "../ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuShortcut,
  DropdownMenuTrigger,
} from "../ui/dropdown-menu";

const MOD_KEY = typeof navigator !== "undefined" && navigator.userAgent.includes("Mac") ? "\u2318" : "Ctrl+";

interface MenuBarProps {
  onClearRequest: () => void;
}

export function MenuBar({ onClearRequest }: MenuBarProps) {
  const hasResults = useAppStore((s) => s.verdicts.length > 0);
  const isAnalyzing = useAppStore((s) => s.isAnalyzing);
  const runAnalysis = useAppStore((s) => s.runAnalysis);
  const validateInputs = useAppStore((s) => s.validateInputs);
  const openExport = useAppStore((s) => s.openExport);
  const saveWorkspace = useAppStore((s) => s.saveWorkspace);
  const loadWorkspace = useAppStore((s) => s.loadWorkspace);
  const cancelAnalysis = useAppStore((s) => s.cancelAnalysis);
  const loadSampleData = useAppStore((s) => s.loadSampleData);
  const canRun = useAppStore(selectCanRun);
  const [aboutOpen, setAboutOpen] = useState(false);

  return (
    <>
      <header
        role="banner"
        className="flex h-11 flex-shrink-0 items-center gap-4 border-b border-border bg-muted/20 px-4 text-xs"
      >
        <div className="flex items-center gap-2.5">
          <span className="text-base" aria-hidden="true">
            🐟
          </span>
          <div className="flex items-center gap-2">
            <span className="font-semibold tracking-wide text-primary">mame</span>
            <span className="rounded-full border border-border/70 bg-background px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
              kuro flow
            </span>
          </div>
          <span className="hidden text-[10px] uppercase tracking-widest text-muted-foreground md:inline">
            Mutagenesis Assessment · Microplate Export
          </span>
        </div>

        <nav className="flex items-center gap-0.5">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button className="rounded-md px-2 py-1 font-medium text-foreground/80 transition-colors hover:bg-background">
                File
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start">
              <DropdownMenuItem onClick={() => void loadWorkspace()}>
                <span className="flex-1">Open Workspace…</span>
                <DropdownMenuShortcut>{MOD_KEY}O</DropdownMenuShortcut>
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => void saveWorkspace()}>
                <span className="flex-1">Save Workspace…</span>
                <DropdownMenuShortcut>{MOD_KEY}S</DropdownMenuShortcut>
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={() => void validateInputs()} disabled={isAnalyzing}>
                <span className="flex-1">Validate Inputs</span>
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => void runAnalysis()} disabled={!canRun}>
                <span className="flex-1">Run Analysis</span>
                <DropdownMenuShortcut>{MOD_KEY}D</DropdownMenuShortcut>
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => void cancelAnalysis()} disabled={!isAnalyzing}>
                <span className="flex-1">Cancel Analysis</span>
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={openExport} disabled={!hasResults}>
                <span className="flex-1">Export Excel…</span>
                <DropdownMenuShortcut>{MOD_KEY}E</DropdownMenuShortcut>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button className="rounded-md px-2 py-1 font-medium text-foreground/80 transition-colors hover:bg-background">
                Edit
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start">
              <DropdownMenuItem onClick={onClearRequest} disabled={!hasResults || isAnalyzing}>
                Clear Results
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button className="rounded-md px-2 py-1 font-medium text-foreground/80 transition-colors hover:bg-background">
                Help
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start">
              <DropdownMenuItem onClick={loadSampleData} disabled={isAnalyzing}>
                Load Sample Data
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={() => setAboutOpen(true)}>About</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </nav>
      </header>

      <Dialog open={aboutOpen} onOpenChange={setAboutOpen}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>About mame</DialogTitle>
            <DialogDescription>
              MAME — Mutagenesis Assessment & Microplate Export
              <br />
              <br />
              Desktop verdict analysis tool for NB-plate mutagenesis runs.
              <br />
              Built with Tauri + React + Python sidecar.
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
