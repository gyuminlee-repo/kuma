import { AlertCircle, Download, Play, ShieldCheck, Square, Trash2 } from "lucide-react";
import { useAppStore } from "../../store/appStore";
import { selectCanRun } from "../../store/selectors";
import { InputPanel } from "../panels/InputPanel";
import { ParameterPanel } from "../panels/ParameterPanel";
import { Button } from "../ui/button";
import { Progress } from "../ui/progress";

interface SidebarProps {
  onClearRequest: () => void;
}

export function Sidebar({ onClearRequest }: SidebarProps) {
  const inputDir = useAppStore((s) => s.inputDir);
  const expectedPath = useAppStore((s) => s.expectedPath);
  const referencePath = useAppStore((s) => s.referencePath);
  const outputPath = useAppStore((s) => s.outputPath);
  const openExport = useAppStore((s) => s.openExport);
  const isAnalyzing = useAppStore((s) => s.isAnalyzing);
  const isValidating = useAppStore((s) => s.isValidating);
  const analyzeProgress = useAppStore((s) => s.analyzeProgress);
  const analyzeMessage = useAppStore((s) => s.analyzeMessage);
  const validationErrors = useAppStore((s) => s.validationErrors);
  const hasResults = useAppStore((s) => s.verdicts.length > 0);
  const runAnalysis = useAppStore((s) => s.runAnalysis);
  const cancelAnalysis = useAppStore((s) => s.cancelAnalysis);
  const validateInputs = useAppStore((s) => s.validateInputs);
  const canRun = useAppStore(selectCanRun);
  const readyCount = [inputDir, expectedPath, referencePath, outputPath].filter(Boolean).length;
  const readiness = Math.round((readyCount / 4) * 100);

  return (
    <aside
      data-testid="sidebar"
      className="flex w-[320px] shrink-0 flex-col overflow-hidden rounded-lg border border-border bg-background"
    >
      <div className="flex-1 space-y-3 overflow-y-auto px-3 py-3">
        <InputPanel />
        <ParameterPanel />
      </div>

      <footer className="space-y-2 border-t border-border bg-muted/30 px-3 py-3">
        <div className="rounded-md border border-border bg-background px-3 py-2">
          <div className="flex items-center justify-between gap-2">
            <div className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
              Run State
            </div>
            <span className="rounded-full border border-border/70 bg-muted px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
              {readyCount}/4 ready
            </span>
          </div>
          <div className="mt-0.5 truncate text-xs font-medium text-foreground" aria-live="polite">
            {analyzeMessage || (isAnalyzing ? "Analyzing…" : canRun ? "Ready to run" : "Setup incomplete")}
          </div>
          <Progress
            value={readiness}
            className="mt-1.5 h-1"
            aria-label={`Input readiness ${readiness}%`}
          />
          {isAnalyzing && (
            <Progress
              value={analyzeProgress}
              className="mt-1.5 h-1"
              aria-label={`Analysis progress ${analyzeProgress}%`}
            />
          )}
          {!isAnalyzing && (
            <div className="mt-1.5 flex items-center gap-1.5 text-[11px] text-muted-foreground">
              <span>{validationErrors.length > 0 ? `${validationErrors.length} validation issue(s)` : "No validation issues"}</span>
            </div>
          )}
        </div>

        {validationErrors.length > 0 && (
          <div
            className="flex items-start gap-2 rounded-md border border-[hsl(var(--verdict-fail))] bg-[hsl(var(--verdict-fail)/0.08)] px-2.5 py-1.5"
            role="alert"
          >
            <AlertCircle size={12} className="mt-0.5 flex-shrink-0 text-[hsl(var(--verdict-fail))]" aria-hidden="true" />
            <span className="text-[11px] text-[hsl(var(--verdict-fail))]">
              {validationErrors.length} input error(s)
            </span>
          </div>
        )}

        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            className="h-8 flex-1 gap-1.5 text-xs"
            onClick={() => void validateInputs()}
            disabled={isValidating || isAnalyzing}
          >
            <ShieldCheck size={12} aria-hidden="true" />
            {isValidating ? "Validating…" : "Validate"}
          </Button>
          {isAnalyzing ? (
            <Button
              size="sm"
              variant="destructive"
              className="h-8 flex-1 gap-1.5 text-xs"
              onClick={() => void cancelAnalysis()}
            >
              <Square size={12} aria-hidden="true" />
              Cancel
            </Button>
          ) : (
            <Button
              size="sm"
              className="h-8 flex-1 gap-1.5 text-xs"
              onClick={() => void runAnalysis()}
              disabled={!canRun}
            >
              <Play size={12} aria-hidden="true" />
              Run
            </Button>
          )}
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            className="h-7 flex-1 gap-1.5 text-xs"
            onClick={onClearRequest}
            disabled={!hasResults || isAnalyzing}
          >
            <Trash2 size={11} aria-hidden="true" />
            Clear
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="h-7 flex-1 gap-1.5 text-xs"
            onClick={openExport}
            disabled={!hasResults}
          >
            <Download size={11} aria-hidden="true" />
            Export
          </Button>
        </div>
      </footer>
    </aside>
  );
}
