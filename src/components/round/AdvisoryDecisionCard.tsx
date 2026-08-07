/**
 * AdvisoryDecisionCard -- read-only display of the strategy.classify_round output.
 *
 * Scope (Fork D):
 *  - User imports per-round xlsx files (Variant + activity fold-change columns).
 *  - Calls strategy.classify_round RPC with RoundFileEntry list.
 *  - Read-only: no Confirm button, no PI decision persistence.
 *  - anti-fallback: never fabricates a result; JSON-RPC errors are shown explicitly.
 *
 * Two success states, drawn differently on purpose:
 *  - advisory "decision": the classifier answered. Coloured label badge, the
 *    reason behind it, and the confidence when the bootstrap gate produced one.
 *  - advisory "not_assessable": the classifier was never asked. Neutral outlined
 *    badge, no label, and a sentence naming the absent input together with the
 *    labels it puts out of reach. Drawing this as another "deferred" badge would
 *    claim a judgement was weighed and withheld.
 *
 * Why switch_combinatorial and stop are never seen today: the handler passes
 * wt_values=None (python-core/sidecar_mame/handlers/classify_round.py), because
 * the purified per-round xlsx carries no wild-type replicate column. Both labels
 * sit behind a bootstrap confidence gate that needs those values, so both are
 * unreachable and result.confidence is always null. That is a limit of the input
 * format, not of how many WT replicates a round happens to have.
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
  ClassifyNotAssessableResult,
  ClassifyRoundResult,
  DecisionLabel,
  MissingClassifierInput,
  RoundFileEntry,
} from "@/types/mame/strategy";

/** Narrowed shape of the i18next translator this file needs. */
type Translate = (key: string, options?: Record<string, unknown>) => string;

/**
 * Reason codes kuma_core/strategy/classify.py can emit, each with a phrase in
 * the locale files. bootstrap_inputs_missing is absent on purpose: the handler
 * converts that one into the not_assessable state before it reaches the UI.
 */
const REASON_CODES: ReadonlySet<string> = new Set([
  "calibration_period",
  "insufficient_data",
  "mixed_signals",
  "no_saturation_signal",
  "hysteresis_pending",
  "low_confidence",
  "stop_low_confidence",
  "saturated_with_throughput",
  "saturated_no_throughput",
]);

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

/** Last-resort rendering for a code with no phrase, so no snake_case reaches the user. */
function humanize(code: string): string {
  return code.replace(/_/g, " ");
}

function labelText(label: DecisionLabel, t: Translate): string {
  return t(`advisoryDecision.labels.${label}`);
}

function reasonText(reason: string, t: Translate): string {
  return REASON_CODES.has(reason)
    ? t(`advisoryDecision.reasons.${reason}`)
    : humanize(reason);
}

function missingInputsText(
  inputs: MissingClassifierInput[],
  t: Translate,
): string {
  return inputs.map((input) => t(`advisoryDecision.missingInputs.${input}`)).join(", ");
}

function blockedLabelsText(labels: DecisionLabel[], t: Translate): string {
  return labels.map((label) => labelText(label, t)).join(", ");
}

/** Extract filename from an absolute path for display. */
function basename(path: string): string {
  return path.split(/[\\/]/).pop() ?? path;
}

/**
 * Footnote carried by an answered decision.
 *
 * The classifier reached a verdict, but some of its signals were unavailable
 * the whole time, so the verdict rests on a narrower base than the full model.
 * Saying which inputs were absent keeps that visible without implying the
 * verdict is in doubt.
 */
function MissingInputsNote({
  missing,
}: {
  missing: MissingClassifierInput[];
}) {
  const { t } = useTranslation();
  if (missing.length === 0) return null;
  return (
    <p className="text-[11px] text-muted-foreground">
      {t("advisoryDecision.missingInputsNote", {
        missing: missingInputsText(missing, t),
      })}
    </p>
  );
}

function DecisionDisplay({ result }: { result: ClassifyDecisionResult }) {
  const { t } = useTranslation();

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <span
          className={cn(
            "rounded-full px-2.5 py-0.5 text-xs font-semibold",
            labelColorClass(result.label),
          )}
          aria-label={t("advisoryDecision.labelAriaLabel", {
            label: labelText(result.label, t),
          })}
        >
          {labelText(result.label, t)}
        </span>
        {/*
          Confidence only exists on the bootstrap-gated branches, all of which
          need wt_values. With the current xlsx input this never renders. It is
          kept because wiring WT replicates into the handler brings it back with
          no UI change; delete it only if that path is abandoned.
        */}
        {result.confidence != null && (
          <span className="text-[11px] text-muted-foreground">
            {t("advisoryDecision.confidence", {
              value: (result.confidence * 100).toFixed(0),
            })}
          </span>
        )}
      </div>
      <p className="text-xs text-muted-foreground">
        {reasonText(result.reason, t)}
      </p>
      <MissingInputsNote missing={result.missing_inputs} />
    </div>
  );
}

/**
 * The classifier was never asked.
 *
 * Reaching this state means the core decision tree did propose a transition,
 * which is the only way the bootstrap gate gets evaluated at all. The gate then
 * found nothing to test with. Both halves of that are stated: the signals point
 * somewhere, and the confirming question cannot be put.
 */
function NotAssessableDisplay({
  result,
}: {
  result: ClassifyNotAssessableResult;
}) {
  const { t } = useTranslation();
  const badge = t("advisoryDecision.notAssessableBadge");

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <span
          className="rounded-full border border-dashed border-muted-foreground/60 px-2.5 py-0.5 text-xs font-semibold text-muted-foreground"
          aria-label={t("advisoryDecision.labelAriaLabel", { label: badge })}
        >
          {badge}
        </span>
      </div>
      <p className="text-xs text-muted-foreground">
        {t("advisoryDecision.notAssessableSummary", {
          missing: missingInputsText(result.missing_inputs, t),
          blocked: blockedLabelsText(result.blocked_decisions, t),
        })}
      </p>
    </div>
  );
}

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

export interface AdvisoryDecisionCardProps {
  className?: string;
  /** Called with every answer the sidecar returns, including not_assessable. */
  onResult?: (result: ClassifyRoundResult) => void;
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
  onResult,
}: AdvisoryDecisionCardProps) {
  const { t } = useTranslation();

  const [files, setFiles] = useState<RoundFileEntry[]>([]);
  const [result, setResult] = useState<ClassifyRoundResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
    setResult(null);
    setError(null);
  }, [t]);

  const handleRemove = useCallback((n: number) => {
    setFiles((prev) => reindex(prev.filter((e) => e.n !== n)));
    setResult(null);
    setError(null);
  }, []);

  const handleClassify = useCallback(async () => {
    if (files.length === 0 || loading) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await classifyRound(files);
      setResult(res);
      onResult?.(res);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [files, loading, onResult]);

  return (
    <section
      aria-labelledby="advisory-decision-heading"
      className={cn("flex flex-col gap-3", className)}
    >
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
      {result?.advisory === "not_assessable" && (
        <NotAssessableDisplay result={result} />
      )}
    </section>
  );
}
