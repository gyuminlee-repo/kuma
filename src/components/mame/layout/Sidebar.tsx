import { AlertCircle, Download, Play, ShieldCheck, Square, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useMameAppStore } from "@/store/mame/mameAppStore";

const RUN_HINT = typeof navigator !== "undefined" && navigator.userAgent.includes("Mac") ? "⌘↵" : "Ctrl+↵";
import { selectCanRun } from "@/store/mame/selectors";
import { InputPanel } from "../panels/InputPanel";
import { ParameterPanel } from "../panels/ParameterPanel";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";

interface SidebarProps {
  onClearRequest: () => void;
  /** Pre-flight-wrapped Run trigger from MameAppLayout. */
  onRunRequest?: () => void;
}

export function Sidebar({ onClearRequest, onRunRequest }: SidebarProps) {
  const { t } = useTranslation();
  const inputDir = useMameAppStore((s) => s.inputDir);
  const expectedPath = useMameAppStore((s) => s.expectedPath);
  const referencePath = useMameAppStore((s) => s.referencePath);
  const outputPath = useMameAppStore((s) => s.outputPath);
  const inputMode = useMameAppStore((s) => s.inputMode);
  const customBarcodesPath = useMameAppStore((s) => s.rawRunParams.customBarcodesPath);
  const openExport = useMameAppStore((s) => s.openExport);
  const isAnalyzing = useMameAppStore((s) => s.isAnalyzing);
  const isValidating = useMameAppStore((s) => s.isValidating);
  const analyzeProgress = useMameAppStore((s) => s.analyzeProgress);
  const analyzeMessage = useMameAppStore((s) => s.analyzeMessage);
  const validationErrors = useMameAppStore((s) => s.validationErrors);
  const hasResults = useMameAppStore((s) => s.verdicts.length > 0);
  const runAnalysis = useMameAppStore((s) => s.runAnalysis);
  const cancelAnalysis = useMameAppStore((s) => s.cancelAnalysis);
  const validateInputs = useMameAppStore((s) => s.validateInputs);
  const canRun = useMameAppStore(selectCanRun);
  const requiredInputs = inputMode === "raw_run"
    ? [inputDir, customBarcodesPath, expectedPath, referencePath, outputPath]
    : [inputDir, expectedPath, referencePath, outputPath];
  const readyCount = requiredInputs.filter(Boolean).length;
  const readiness = Math.round((readyCount / requiredInputs.length) * 100);

  return (
    <aside
      data-testid="sidebar"
      className="flex w-sidebar shrink-0 flex-col overflow-hidden rounded-container border border-border bg-card"
    >
      <div className="flex-1 space-y-3 overflow-y-auto p-3">
        <InputPanel />
        <ParameterPanel />
      </div>

      <footer className="space-y-2 border-t border-border px-3 py-3">
        <div className="space-y-1 px-1">
          <div className="flex items-center justify-between gap-2">
            <span className="text-caption text-muted-foreground">{t("mameSidebar.runStateLabel")}</span>
            <span className="rounded-full border border-border/70 bg-muted px-2 py-0.5 text-caption font-medium text-muted-foreground">
              {t("mameSidebar.readyCount", { ready: readyCount, total: requiredInputs.length })}
            </span>
          </div>
          <div className="truncate text-body font-medium text-foreground" aria-live="polite">
            {analyzeMessage || (isAnalyzing ? t("mameSidebar.statusAnalyzing") : canRun ? t("mameSidebar.statusReady") : t("mameSidebar.statusIncomplete"))}
          </div>
          <Progress
            value={readiness}
            className="mt-1.5 h-1"
            aria-label={t("mameSidebar.inputReadinessAria", { percent: readiness })}
          />
          {isAnalyzing && (
            <Progress
              value={analyzeProgress}
              className="mt-1.5 h-1"
              aria-label={t("mameSidebar.analysisProgressAria", { percent: analyzeProgress })}
            />
          )}
          {!isAnalyzing && (
            <p className="mt-1.5 text-caption text-muted-foreground">
              {validationErrors.length > 0 ? t("mameSidebar.validationIssues", { count: validationErrors.length }) : t("mameSidebar.noValidationIssues")}
            </p>
          )}
        </div>

        {validationErrors.length > 0 && (
          <div
            className="flex items-start gap-2 rounded-control border border-error/40 bg-error/8 px-2.5 py-1.5"
            role="alert"
          >
            <AlertCircle size={12} className="mt-0.5 flex-shrink-0 text-error" aria-hidden="true" />
            <div className="min-w-0 space-y-1 text-caption text-error">
              <p className="font-medium">{t("mameSidebar.inputErrors", { count: validationErrors.length })}</p>
              <ul className="list-disc space-y-0.5 pl-4">
                {validationErrors.map((error, index) => (
                  <li key={`${index}-${error}`} className="break-words">
                    {error}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        )}

        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            className="h-control flex-1 min-w-0 gap-1.5 rounded-control text-caption"
            onClick={() => void validateInputs()}
            disabled={isValidating || isAnalyzing}
          >
            <ShieldCheck size={12} aria-hidden="true" />
            {isValidating ? t("mameSidebar.validatingBtn") : t("mameSidebar.validateBtn")}
          </Button>
          {isAnalyzing ? (
            <Button
              size="sm"
              variant="outline"
              className="h-control-primary flex-1 min-w-0 gap-1.5 rounded-control text-caption text-error border-error/40 hover:bg-error/8"
              onClick={() => void cancelAnalysis()}
            >
              <Square size={12} aria-hidden="true" />
              {t("mameSidebar.cancelBtn")}
            </Button>
          ) : (
            <Button
              size="sm"
              className="h-control-primary flex-1 min-w-0 gap-1.5 rounded-control text-caption"
              onClick={() => (onRunRequest ? onRunRequest() : void runAnalysis())}
              disabled={!canRun}
            >
              <Play size={12} aria-hidden="true" />
              {t("mameSidebar.runBtn")}
              <kbd className="ml-1 text-caption font-normal opacity-70">{RUN_HINT}</kbd>
            </Button>
          )}
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            className="h-control flex-1 min-w-0 gap-1.5 rounded-control text-caption"
            onClick={onClearRequest}
            disabled={!hasResults || isAnalyzing}
          >
            <Trash2 size={12} aria-hidden="true" />
            {t("mameSidebar.clearBtn")}
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="h-control flex-1 min-w-0 gap-1.5 rounded-control text-caption"
            onClick={openExport}
            disabled={!hasResults}
          >
            <Download size={12} aria-hidden="true" />
            {t("mameSidebar.exportBtn")}
          </Button>
        </div>
      </footer>
    </aside>
  );
}
