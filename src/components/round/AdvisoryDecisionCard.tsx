/**
 * AdvisoryDecisionCard -- read-only display of the classify() advisory output.
 *
 * Scope (v0.3 partial slice):
 *  - Shows label / reason / confidence from strategy.classify_round RPC.
 *  - Shows a "plumbing pending" notice when advisory === "unavailable".
 *  - Read-only: no Confirm button, no PI decision persistence, no activation_status.
 *  - Calls classifyRound() on mount when round_id is provided.
 *  - Never fabricates data: missing scalars -> renders the unavailable branch.
 *
 * Plumbing fields that must be wired before real data reaches classify():
 *   cumulative_beneficial, K_throughput, delta_best_ema,
 *   unused_beneficial_count, hit_rates, top_k_positions_n,
 *   top_k_positions_n1, top_k_positions, active_residues
 */

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { InfoIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { classifyRound } from "@/lib/ipc";
import type {
  ClassifyRoundResult,
  DecisionLabel,
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

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function DecisionDisplay({
  result,
}: {
  result: Extract<ClassifyRoundResult, { advisory: "decision" }>;
}) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <span
          className={cn(
            "rounded-full px-2.5 py-0.5 text-xs font-semibold",
            labelColorClass(result.label),
          )}
          aria-label={t("advisoryDecision.labelAriaLabel", { label: result.label })}
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
      <p className="text-xs text-muted-foreground">{result.reason}</p>
    </div>
  );
}

function UnavailableDisplay({
  missing,
}: {
  missing: string[];
}) {
  const { t } = useTranslation();
  return (
    <div
      role="status"
      aria-live="polite"
      className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-300"
    >
      <InfoIcon
        size={13}
        aria-hidden="true"
        className="mt-0.5 shrink-0 text-amber-600 dark:text-amber-400"
      />
      <div className="flex flex-col gap-1">
        <span>{t("advisoryDecision.unavailableBody")}</span>
        <span className="font-mono text-[10px] text-amber-700 dark:text-amber-400">
          {t("advisoryDecision.missingFields", { fields: missing.join(", ") })}
        </span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export interface AdvisoryDecisionCardProps {
  /** Round ID to query. If undefined, the card renders nothing. */
  roundId: string | undefined;
  className?: string;
}

/**
 * AdvisoryDecisionCard
 *
 * Fetches and displays the advisory classify() output for one round.
 * Renders in three states:
 *   - Loading: spinner placeholder
 *   - Decision: label badge + confidence + reason
 *   - Unavailable: amber notice listing missing plumbing fields
 *
 * Read-only. No Confirm button, no PI decision persistence.
 */
export function AdvisoryDecisionCard({
  roundId,
  className,
}: AdvisoryDecisionCardProps) {
  const { t } = useTranslation();
  const [result, setResult] = useState<ClassifyRoundResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!roundId) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setResult(null);
    classifyRound(roundId)
      .then((res) => {
        if (!cancelled) setResult(res);
      })
      .catch((err: unknown) => {
        if (!cancelled)
          setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [roundId]);

  if (!roundId) return null;

  return (
    <section
      aria-labelledby="advisory-decision-heading"
      className={cn("flex flex-col gap-2", className)}
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

      {loading && (
        <p className="text-xs text-muted-foreground" aria-live="polite">
          {t("advisoryDecision.loading")}
        </p>
      )}

      {error && (
        <p className="text-xs text-red-600 dark:text-red-400" role="alert">
          {t("advisoryDecision.error", { message: error })}
        </p>
      )}

      {result?.advisory === "decision" && <DecisionDisplay result={result} />}

      {result?.advisory === "unavailable" && (
        <UnavailableDisplay missing={result.missing} />
      )}
    </section>
  );
}
