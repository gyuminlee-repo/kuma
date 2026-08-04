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
 *   analyzeYield.*            , backend `wells_with_reads` / `assigned_reads` /
 *                                `total_reads` / `passed_mapq` /
 *                                `passed_coverage`
 *                                (raw-run mode only; omitted, not defaulted,
 *                                when the response did not carry them)
 * A metric whose field is absent is not rendered at all.
 *
 * The demux gate counters also name a likely cause, but only where the counts
 * themselves carry the evidence (`diagnoseZeroResult`). Where they do not, the
 * notice states no cause and falls back to the checklist: asserting a cause
 * with nothing behind it is worse than asking the user to look.
 */

import { AlertTriangle } from "lucide-react";
import { useId } from "react";
import { useTranslation } from "react-i18next";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import type { AnalyzeYield } from "@/types/mame/models";

interface Metric {
  id: string;
  label: string;
  value: number;
}

/**
 * Which of the two demux gates, if either, the counts pin the failure on.
 *
 *   "noAlignment"  reads existed and none cleared MAPQ, so nothing aligned to
 *                  the reference at all: a reference from a different sequence.
 *   "noCoverage"   reads aligned but none cleared the coverage gate: what a
 *                  whole-construct reference looks like against amplicon reads,
 *                  where the alignment covers only a fraction of the reference.
 *   null           any other combination, including a missing counter. No cause
 *                  is claimed.
 */
type ZeroResultCause = "noAlignment" | "noCoverage";

export function diagnoseZeroResult(analyzeYield: AnalyzeYield | null): ZeroResultCause | null {
  if (analyzeYield === null) return null;
  const { total_reads, passed_mapq, passed_coverage } = analyzeYield;
  if (total_reads !== undefined && passed_mapq !== undefined) {
    if (total_reads > 0 && passed_mapq === 0) return "noAlignment";
  }
  if (passed_mapq !== undefined && passed_coverage !== undefined) {
    if (passed_mapq > 0 && passed_coverage === 0) return "noCoverage";
  }
  return null;
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
  const totalReads = analyzeYield?.total_reads;
  if (totalReads !== undefined) {
    metrics.push({
      id: "totalReads",
      label: t("mame.analyze.zeroResult.metricTotalReads"),
      value: totalReads,
    });
  }
  const passedMapq = analyzeYield?.passed_mapq;
  if (passedMapq !== undefined) {
    metrics.push({
      id: "passedMapq",
      label: t("mame.analyze.zeroResult.metricPassedMapq"),
      value: passedMapq,
    });
  }
  const passedCoverage = analyzeYield?.passed_coverage;
  if (passedCoverage !== undefined) {
    metrics.push({
      id: "passedCoverage",
      label: t("mame.analyze.zeroResult.metricPassedCoverage"),
      value: passedCoverage,
    });
  }

  // Counts interpolated into the cause text are the response fields themselves,
  // so the sentence can never disagree with the metric rows above it.
  const cause = diagnoseZeroResult(analyzeYield);
  const causeText =
    cause === "noAlignment"
      ? t("mame.analyze.zeroResult.causeNoAlignment", {
          totalReads: (totalReads ?? 0).toLocaleString(),
        })
      : cause === "noCoverage"
        ? t("mame.analyze.zeroResult.causeNoCoverage", {
            passedMapq: (passedMapq ?? 0).toLocaleString(),
          })
        : null;

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

        {causeText !== null && (
          <div className="space-y-1" data-testid="zero-result-cause" data-cause={cause ?? ""}>
            <p className="text-caption font-medium text-foreground">
              {t("mame.analyze.zeroResult.causeHeading")}
            </p>
            <p className="break-words text-caption text-muted-foreground">{causeText}</p>
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
