import { useState } from "react";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import { useKumaProject } from "@/state/projectContext";
import { CrashLogDialog } from "@/components/dialogs/CrashLogDialog";
import { JanusMappingDialog } from "@/components/mame/dialogs/JanusMappingDialog";
import { RunReportDialog } from "@/components/mame/dialogs/RunReportDialog";
import { selectCanRun } from "@/store/mame/selectors";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuShortcut,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { SubtoolMenuBar } from "@/components/layout/SubtoolMenuBar";

const MOD_KEY = typeof navigator !== "undefined" && navigator.userAgent.includes("Mac") ? "⌘" : "Ctrl+";

/** 메뉴 트리거 공통 클래스 (계획서 §6.1 권장) */
const TRIGGER_CLS =
  "h-control px-3 rounded-control hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 transition-colors duration-fast text-caption font-medium text-foreground/80";

interface MenuBarProps {
  onClearRequest: () => void;
}

export function MenuBar({ onClearRequest }: MenuBarProps) {
  const project = useKumaProject();
  const hasResults = useMameAppStore((s) => s.verdicts.length > 0);
  const isAnalyzing = useMameAppStore((s) => s.isAnalyzing);
  const runAnalysis = useMameAppStore((s) => s.runAnalysis);
  const validateInputs = useMameAppStore((s) => s.validateInputs);
  const openExport = useMameAppStore((s) => s.openExport);
  const saveWorkspace = useMameAppStore((s) => s.saveWorkspace);
  const loadWorkspace = useMameAppStore((s) => s.loadWorkspace);
  const cancelAnalysis = useMameAppStore((s) => s.cancelAnalysis);
  const loadSampleData = useMameAppStore((s) => s.loadSampleData);
  const canRun = useMameAppStore(selectCanRun);
  const [aboutOpen, setAboutOpen] = useState(false);
  const [bibtexCopied, setBibtexCopied] = useState(false);
  const [crashLogOpen, setCrashLogOpen] = useState(false);

  const MAME_BIBTEX = `@software{mame_TBD,
  title  = {MAME: Multi-round Activity & Mutation Engine},
  author = {Kang, Hyemin and KRIBB C1 Lab},
  year   = {2026},
  note   = {DOI/citation forthcoming},
  url    = {TBD}
}`;

  async function handleCopyBibtex() {
    await navigator.clipboard.writeText(MAME_BIBTEX);
    setBibtexCopied(true);
    setTimeout(() => setBibtexCopied(false), 2000);
  }
  const [janusOpen, setJanusOpen] = useState(false);
  const [runReportOpen, setRunReportOpen] = useState(false);

  const menus = (
    <>
      {/* File 메뉴 */}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button className={TRIGGER_CLS}>File</button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start">
          <DropdownMenuItem onClick={() => void loadWorkspace(project)}>
            <span className="flex-1">Open Workspace…</span>
            <DropdownMenuShortcut>{MOD_KEY}O</DropdownMenuShortcut>
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => void saveWorkspace(project)}>
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
          <DropdownMenuItem onClick={() => setJanusOpen(true)} disabled={!hasResults}>
            <span className="flex-1">Export Janus Mapping…</span>
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => setRunReportOpen(true)} disabled={!hasResults}>
            <span className="flex-1">Export Run Report…</span>
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      {/* Edit 메뉴 */}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button className={TRIGGER_CLS}>Edit</button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start">
          <DropdownMenuItem onClick={onClearRequest} disabled={!hasResults || isAnalyzing}>
            Clear Results
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      {/* Help 메뉴 */}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button className={TRIGGER_CLS}>Help</button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start">
          <DropdownMenuItem onClick={loadSampleData} disabled={isAnalyzing}>
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
          <DropdownMenuItem onClick={() => setAboutOpen(true)}>About</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </>
  );

  return (
    <>
      <CrashLogDialog open={crashLogOpen} onOpenChange={setCrashLogOpen} />
      <JanusMappingDialog open={janusOpen} onOpenChange={setJanusOpen} />
      <RunReportDialog open={runReportOpen} onOpenChange={setRunReportOpen} />

      <SubtoolMenuBar
        label="Mame"
        subtitle="Mutagenesis Assessment & Microplate Export"
        menus={menus}
      />

      <Dialog
        open={aboutOpen}
        onOpenChange={(open: boolean) => {
          setAboutOpen(open);
          if (!open) setBibtexCopied(false);
        }}
      >
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>About Mame</DialogTitle>
            <DialogDescription>
              MAME v{__APP_VERSION__}
              <br />
              Mutagenesis Assessment &amp; Microplate Export
              <br />
              Desktop verdict analysis tool for NB-plate mutagenesis runs.
              <br />
              Built with Tauri + React + Python sidecar.
            </DialogDescription>
          </DialogHeader>

          {/* How to cite */}
          <div className="flex flex-col gap-1.5">
            <p className="text-sm font-semibold text-foreground">How to cite</p>
            <pre className="overflow-x-auto whitespace-pre rounded-md bg-muted px-3 py-2 text-xs text-muted-foreground">
              {MAME_BIBTEX}
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

          {/* External services */}
          <div className="flex flex-col gap-1.5">
            <p className="text-sm font-semibold text-foreground">External services</p>
            <p className="text-xs text-muted-foreground">
              MAME는 외부 네트워크 서비스를 사용하지 않습니다. 모든 분석은 로컬에서 실행됩니다.
            </p>
          </div>

          {/* Third-party licenses */}
          <div className="flex flex-col gap-1">
            <p className="text-sm font-semibold text-foreground">Third-party licenses</p>
            <p className="text-xs text-muted-foreground">
              Third-party licenses available in distribution package.
            </p>
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
