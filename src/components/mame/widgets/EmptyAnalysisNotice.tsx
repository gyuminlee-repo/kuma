/**
 * EmptyAnalysisNotice, "the run finished, and it produced nothing" empty state.
 *
 * A verdict-free result used to render as a blank 2.2 view identical to the
 * pre-run view, so a misconfigured run (a wrong reference drops every read at
 * the alignment stage, leaving the Final sheet with 0 data rows) looked like a
 * success. This states the outcome and lists what to check.
 *
 * Not an error boundary and not role="alert": the run itself completed, so the
 * pre-run empty-state convention still applies (AGENTS.md: MAME result tables
 * render an empty state rather than surfacing an error boundary).
 *
 * Every number shown is read straight off the analyze response as stored:
 *   summary.total             , backend `_summarize(verdicts)`
 *   distributionStats.n_files , backend `distribution_stats.n_files`
 *   analyzeYield.*            , backend `wells_with_reads` / `assigned_reads`
 *                                (raw-run mode only; omitted, not defaulted,
 *                                when the response did not carry them)
 * A metric whose field is absent is not rendered at all.
 */

import { AlertTriangle } from "lucide-react";
import { useId } from "react";
import { useTranslation } from "react-i18next";
import { useMameAppStore } from "@/store/mame/mameAppStore";

interface Metric {
  id: string;
  label: string;
  value: number;
}

export function EmptyAnalysisNotice() {
  const { t } = useTranslation();
  const summary = useMameAppStore((s) => s.summary);
  const distributionStats = useMameAppStore((s) => s.distributionStats);
  const analyzeYield = useMameAppStore((s) => s.analyzeYield);
  const titleId = useId();

  const metrics: Metric[] = [];
  if (summary !== null) {
    metrics.push({
      id: "verdicts",
      label: t("mame.analyze.zeroResult.metricVerdicts"),
      value: summary.total,
    });
  }
  if (distributionStats !== null) {
    metrics.push({
      id: "inputFiles",
      label: t("mame.analyze.zeroResult.metricInputFiles"),
      value: distributionStats.n_files,
    });
  }
  const wellsWithReads = analyzeYield?.wells_with_reads;
  if (wellsWithReads !== undefined) {
    metrics.push({
      id: "wellsWithReads",
      label: t("mame.analyze.zeroResult.metricWellsWithReads"),
      value: wellsWithReads,
    });
  }
  const assignedReads = analyzeYield?.assigned_reads;
  if (assignedReads !== undefined) {
    metrics.push({
      id: "assignedReads",
      label: t("mame.analyze.zeroResult.metricAssignedReads"),
      value: assignedReads,
    });
  }

  const nextSteps = [
    { id: "reference", text: t("mame.analyze.zeroResult.nextStepReference") },
    { id: "expected", text: t("mame.analyze.zeroResult.nextStepExpected") },
    { id: "inputFolder", text: t("mame.analyze.zeroResult.nextStepInputFolder") },
  ];

  return (
    <section
      data-testid="empty-analysis-notice"
      aria-labelledby={titleId}
      role="status"
      aria-live="polite"
      className="flex items-start gap-2.5 rounded-control border border-warning/40 bg-warning/8 px-3 py-2.5"
    >
      <AlertTriangle size={14} className="mt-0.5 flex-shrink-0 text-warning" aria-hidden="true" />
      <div className="min-w-0 flex-1 space-y-2.5">
        <div className="space-y-1">
          <h3 id={titleId} className="text-body font-medium text-foreground">
            {t("mame.analyze.zeroResult.title")}
          </h3>
          <p className="text-caption text-muted-foreground">
            {t("mame.analyze.zeroResult.description")}
          </p>
        </div>

        {metrics.length > 0 && (
          <div className="space-y-1">
            <p className="text-caption font-medium text-foreground">
              {t("mame.analyze.zeroResult.metricsHeading")}
            </p>
            <dl className="grid grid-cols-1 gap-x-4 gap-y-0.5 sm:grid-cols-2">
              {metrics.map((metric) => (
                <div key={metric.id} className="flex min-w-0 items-baseline justify-between gap-2">
                  <dt className="truncate text-caption text-muted-foreground">{metric.label}</dt>
                  <dd className="flex-shrink-0 text-caption font-medium tabular-nums text-foreground">
                    {metric.value.toLocaleString()}
                  </dd>
                </div>
              ))}
            </dl>
          </div>
        )}

        <div className="space-y-1">
          <p className="text-caption font-medium text-foreground">
            {t("mame.analyze.zeroResult.nextStepsHeading")}
          </p>
          <ul className="list-disc space-y-0.5 pl-4 text-caption text-muted-foreground">
            {nextSteps.map((step) => (
              <li key={step.id} className="break-words">
                {step.text}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}
