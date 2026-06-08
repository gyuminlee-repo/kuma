/**
 * AdvisoryDecisionCard -- read-only display of the classify() advisory output.
 *
 * Scope (Fork D):
 *  - User imports per-round xlsx files (Variant + activity fold-change columns).
 *  - Calls strategy.classify_round RPC with RoundFileEntry list.
 *  - Shows label / reason / confidence from response.
 *  - Read-only: no Confirm button, no PI decision persistence.
 *  - anti-fallback: never fabricates a result; JSON-RPC errors are shown explicitly.
 *
 * Constraint (hard, non-negotiable):
 *  The classifier never emits switch_combinatorial confidently (WT replicate
 *  limit is 3 per round). Possible labels: continue_walking or deferred.
 *  The UI reflects this honestly.
 */

import { useState, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { open } from "@tauri-apps/plugin-dialog";
import { InfoIcon, FileSpreadsheet, X, PlayCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import { classifyRound } from "@/lib/ipc";
import { Button } from "@/components/ui/button";
import type {
  ClassifyDecisionResult,
  DecisionLabel,
  RoundFileEntry,
} from "@/types/mame/strategy";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Maps DecisionLabel to a Tailwind color pair (bg/text). */
function labelColorClass(label: DecisionLabel): string {
  switch (label) {
    case "continue_walking":
      return "bg-emerald-100 text-emerald-800 dark:bg-emerald-900 dark:text-emerald-200";
    case "switch_combinatorial":
      return "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200";
    case "stop":
      return "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200";
    case "deferred":
      return "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200";
    default:
      return "bg-muted text-muted-foreground";
  }
}

/** Extract filename from an absolute path for display. */
function basename(path: string): string {
  return path.split(/[\\/]/).pop() ?? path;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function DecisionDisplay({
  result,
}: {
  result: ClassifyDecisionResult;
}) {
  const { t } = useTranslation();
  const reason = mapReasonText(result.label, result.reason, t);

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <span
          className={cn(
            "rounded-full px-2.5 py-0.5 text-xs font-semibold",
            labelColorClass(result.label),
          )}
          aria-label={t("advisoryDecision.labelAriaLabel", {
            label: result.label,
          })}
        >
          {result.label}
        </span>
        {result.confidence != null && (
          <span className="text-[11px] text-muted-foreground">
            {t("advisoryDecision.confidence", {
              value: (result.confidence * 100).toFixed(0),
            })}
          </span>
        )}
      </div>
      <p className="text-xs text-muted-foreground">{reason}</p>
    </div>
  );
}

/**
 * Returns a user-friendly reason string for any label.
 * continue_walking prepends a recommendation line.
 * For deferred labels, maps known reason codes to explicit messages.
 * Falls back to the raw reason string for unknown codes.
 */
function mapReasonText(
  label: DecisionLabel,
  reason: string,
  t: (key: string) => string,
): string {
  if (label === "continue_walking") {
    return `${t("advisoryDecision.continueWalkingRecommendation")} ${reason}`.trim();
  }
  if (label !== "deferred") return reason;
  switch (reason) {
    case "bootstrap_inputs_missing":
      return t("advisoryDecision.deferredBootstrapInputsMissing");
    case "calibration_period":
      return t("advisoryDecision.deferredCalibrationPeriod");
    case "insufficient_data":
      return t("advisoryDecision.deferredInsufficientData");
    case "mixed_signals":
      return t("advisoryDecision.deferredMixedSignals");
    default:
      return reason;
  }
}

// ---------------------------------------------------------------------------
// File picker sub-component
// ---------------------------------------------------------------------------

interface FileRowProps {
  entry: RoundFileEntry;
  onRemove: (n: number) => void;
}

function FileRow({ entry, onRemove }: FileRowProps) {
  return (
    <li className="flex items-center justify-between gap-2 rounded border bg-muted/40 px-2 py-1 text-xs">
      <div className="flex items-center gap-1.5 min-w-0">
        <FileSpreadsheet
          size={12}
          aria-hidden="true"
          className="shrink-0 text-muted-foreground"
        />
        <span className="font-mono text-muted-foreground shrink-0">
          R{entry.n}
        </span>
        <span className="truncate" title={entry.path}>
          {basename(entry.path)}
        </span>
      </div>
      <button
        type="button"
        aria-label={`Remove round ${entry.n} file`}
        onClick={() => onRemove(entry.n)}
        className="shrink-0 rounded p-0.5 hover:bg-destructive/10 hover:text-destructive focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <X size={11} aria-hidden="true" />
      </button>
    </li>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export interface AdvisoryDecisionCardProps {
  className?: string;
}

/**
 * AdvisoryDecisionCard (Fork D)
 *
 * Self-contained file-picker + advisory classification card.
 * User adds per-round xlsx files; the component calls classifyRound() on demand.
 *
 * States: idle | loading | result | error
 * Read-only. No Confirm button, no PI decision persistence.
 */
export function AdvisoryDecisionCard({
  className,
}: AdvisoryDecisionCardProps) {
  const { t } = useTranslation();

  // File list state: entries are kept sorted by n; n is 1..N, re-assigned on every change.
  const [files, setFiles] = useState<RoundFileEntry[]>([]);
  const [result, setResult] = useState<ClassifyDecisionResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // -------------------------------------------------------------------------
  // File management
  // -------------------------------------------------------------------------

  /** Renumbers entries 1..N in current order (gap-free). */
  function reindex(entries: { path: string }[]): RoundFileEntry[] {
    return entries.map((e, i) => ({ n: i + 1, path: e.path }));
  }

  const handleAddFiles = useCallback(async () => {
    const selected = await open({
      directory: false,
      multiple: true,
      filters: [{ name: "Excel", extensions: ["xlsx"] }],
      title: t("advisoryDecision.filePickerTitle"),
    });
    if (!selected) return;
    const paths = Array.isArray(selected) ? selected : [selected];
    setFiles((prev) => {
      const existing = new Set(prev.map((e) => e.path));
      const newPaths = paths.filter((p) => !existing.has(p));
      return reindex([...prev, ...newPaths.map((p) => ({ path: p }))]);
    });
    // Reset result when file list changes
    setResult(null);
    setError(null);
  }, [t]);

  const handleRemove = useCallback((n: number) => {
    setFiles((prev) => reindex(prev.filter((e) => e.n !== n)));
    setResult(null);
    setError(null);
  }, []);

  // -------------------------------------------------------------------------
  // Classify
  // -------------------------------------------------------------------------

  const handleClassify = useCallback(async () => {
    if (files.length === 0 || loading) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await classifyRound(files);
      setResult(res);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [files, loading]);

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  return (
    <section
      aria-labelledby="advisory-decision-heading"
      className={cn("flex flex-col gap-3", className)}
    >
      {/* Heading */}
      <h4
        id="advisory-decision-heading"
        className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground"
      >
        {t("advisoryDecision.heading")}
        <span
          className="ml-1.5 rounded bg-blue-100 px-1 py-0.5 text-[9px] font-medium text-blue-700 dark:bg-blue-900 dark:text-blue-300"
          aria-label={t("advisoryDecision.readOnlyAriaLabel")}
        >
          {t("advisoryDecision.readOnlyBadge")}
        </span>
      </h4>

      {/* File list */}
      {files.length > 0 && (
        <ul
          aria-label={t("advisoryDecision.fileListAriaLabel")}
          className="flex flex-col gap-1"
        >
          {files.map((entry) => (
            <FileRow key={entry.path} entry={entry} onRemove={handleRemove} />
          ))}
        </ul>
      )}

      {/* File picker + run buttons */}
      <div className="flex items-center gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={handleAddFiles}
          disabled={loading}
          className="h-7 gap-1.5 text-xs"
          aria-label={t("advisoryDecision.addFilesAriaLabel")}
        >
          <FileSpreadsheet size={12} aria-hidden="true" />
          {t("advisoryDecision.addFiles")}
        </Button>
        <Button
          type="button"
          size="sm"
          onClick={handleClassify}
          disabled={files.length === 0 || loading}
          className="h-7 gap-1.5 text-xs"
          aria-label={t("advisoryDecision.classifyAriaLabel")}
        >
          <PlayCircle size={12} aria-hidden="true" />
          {t("advisoryDecision.classify")}
        </Button>
      </div>

      {/* States */}
      {loading && (
        <p className="text-xs text-muted-foreground" aria-live="polite">
          {t("advisoryDecision.loading")}
        </p>
      )}

      {error && (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-800 dark:border-red-800 dark:bg-red-950 dark:text-red-300"
        >
          <InfoIcon
            size={13}
            aria-hidden="true"
            className="mt-0.5 shrink-0 text-red-600 dark:text-red-400"
          />
          <span>{t("advisoryDecision.error", { message: error })}</span>
        </div>
      )}

      {result?.advisory === "decision" && <DecisionDisplay result={result} />}
    </section>
  );
}
