import { useState } from "react";
import { useAppStore } from "../../store/appStore";
import { useKumaProject } from "../../state/projectContext";
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
  DropdownMenuSeparator,
} from "../ui/dropdown-menu";
import { getCrashLog } from "../../lib/crashLog";
import { CrashLogDialog } from "../dialogs/CrashLogDialog";
import {
  handleExportExcel,
  handleExportMappingWithParams,
  handleSaveWorkspace,
  handleLoadWorkspace,
  handleOpenSequence,
} from "./export-handlers";
import { MappingExportDialog } from "../dialogs/MappingExportDialog";
import { SubtoolMenuBar } from "./SubtoolMenuBar";

const MOD_KEY = navigator.userAgent.includes("Mac") ? "⌘" : "Ctrl+";

/** 메뉴 트리거 공통 클래스 (계획서 §6.1 권장) */
const TRIGGER_CLS =
  "h-control px-3 rounded-control hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 transition-colors duration-fast text-caption font-medium text-foreground/80";

export function MenuBar() {
  const project = useKumaProject();
  const hasDesignResults = useAppStore((s) => s.designResults.length > 0);
  const loadSampleData = useAppStore((s) => s.loadSampleData);
  const [aboutOpen, setAboutOpen] = useState(false);
  const [crashCopied, setCrashCopied] = useState(false);
  const [bibtexCopied, setBibtexCopied] = useState(false);
  const [crashLogOpen, setCrashLogOpen] = useState(false);
  const [mappingDialogOpen, setMappingDialogOpen] = useState(false);
  const [mappingDialogFormat, setMappingDialogFormat] = useState<"echo" | "janus">("echo");

  const KURO_BIBTEX = `@software{kuro_TBD,
  title  = {KURO: Kernel for Upstream Recombination Oligodesign},
  author = {Kang, Hyemin and KRIBB C1 Lab},
  year   = {2026},
  note   = {DOI/citation forthcoming},
  url    = {TBD}
}`;

  async function handleCopyBibtex() {
    await navigator.clipboard.writeText(KURO_BIBTEX);
    setBibtexCopied(true);
    setTimeout(() => setBibtexCopied(false), 2000);
  }

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

  const menus = (
    <>
      {/* File 메뉴 */}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button className={TRIGGER_CLS}>File</button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start">
          <DropdownMenuItem onClick={handleOpenSequence}>
            <span className="flex-1">Open Sequence...</span>
            <kbd className="ml-4 text-caption text-muted-foreground">{MOD_KEY}O</kbd>
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={() => void handleSaveWorkspace(project)}>
            <span className="flex-1">Save Workspace...</span>
            <kbd className="ml-4 text-caption text-muted-foreground">{MOD_KEY}S</kbd>
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => void handleLoadWorkspace(project)}>
            Load Workspace...
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            onClick={() => handleExportExcel(project?.project_id)}
            disabled={!hasDesignResults}
          >
            <span className="flex-1">Export Excel...</span>
            <kbd className="ml-4 text-caption text-muted-foreground">{MOD_KEY}E</kbd>
          </DropdownMenuItem>
          <DropdownMenuSeparator />
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

      {/* Help 메뉴 */}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button className={TRIGGER_CLS}>Help</button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start">
          <DropdownMenuItem onClick={loadSampleData}>
            Load Sample Data
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={() => window.dispatchEvent(new CustomEvent("kuma:show-onboarding"))}>
            Show Onboarding
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => setCrashLogOpen(true)}>
            View Crash Log
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={() => setAboutOpen(true)}>
            About
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </>
  );

  return (
    <>
      <SubtoolMenuBar
        label="Kuro"
        subtitle="Kernel for Upstream Recombination Oligodesign"
        menus={menus}
      />

      <CrashLogDialog open={crashLogOpen} onOpenChange={setCrashLogOpen} />

      <MappingExportDialog
        open={mappingDialogOpen}
        initialFormat={mappingDialogFormat}
        onOpenChange={setMappingDialogOpen}
        onExport={({ format, transferVol }) => {
          setMappingDialogOpen(false);
          handleExportMappingWithParams(format, { transferVol });
        }}
      />

      <Dialog
        open={aboutOpen}
        onOpenChange={(open: boolean) => {
          setAboutOpen(open);
          if (!open) {
            setCrashCopied(false);
            setBibtexCopied(false);
          }
        }}
      >
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>About Kuro</DialogTitle>
            <DialogDescription>
              Kuro v{__APP_VERSION__}
              <br />
              SDM primer batch design tool with Tm-guided overlap extension.
              <br />
              <br />
              Built with Tauri + React + primer3-py
              <br />
              <br />
              <a
                href="https://github.com/gyuminlee-repo/KURO"
                target="_blank"
                rel="noopener noreferrer"
                className="text-info underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              >
                github.com/gyuminlee-repo/KURO
              </a>
            </DialogDescription>
          </DialogHeader>

          {/* How to cite */}
          <div className="flex flex-col gap-1.5">
            <p className="text-sm font-semibold text-foreground">How to cite</p>
            <pre className="overflow-x-auto whitespace-pre rounded-md bg-muted px-3 py-2 text-xs text-muted-foreground">
              {KURO_BIBTEX}
            </pre>
            <Button
              size="sm"
              variant="outline"
              onClick={() => void handleCopyBibtex()}
            >
              {bibtexCopied ? "Copied!" : "Copy BibTeX"}
            </Button>
          </div>

          {/* License */}
          <div className="flex flex-col gap-1">
            <p className="text-sm font-semibold text-foreground">License</p>
            <p className="text-xs text-muted-foreground">
              Internal use, KRIBB C1 Lab — DOI/citation forthcoming
            </p>
          </div>

          {/* Third-party licenses */}
          <div className="flex flex-col gap-1">
            <p className="text-sm font-semibold text-foreground">Third-party licenses</p>
            <p className="text-xs text-muted-foreground">
              Third-party licenses available in distribution package.
            </p>
          </div>

          <div className="flex flex-col gap-2 mt-1">
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
