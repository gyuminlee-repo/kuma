/**
 * RoundSummaryPanel — Calibration-mode round signal display.
 *
 * 5/12 scope (spec §12-A.6):
 *  - Shows 6 signals (T1–T_unused) per spec §12-A.1.
 *  - Displays signal booleans + raw input values for each signal.
 *  - Shows "calibration period — classification inactive" banner.
 *  - Does NOT show classification decision labels
 *    (continue_walking / switch_combinatorial / stop / deferred).
 *    Classification is v0.3+ (advisory mode, §12-A.5).
 *
 * Props:
 *  metrics — RoundMetrics object from strategy computation, or null when no
 *            round has been processed yet. Never renders dummy numbers.
 */

import { InfoIcon } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { RoundMetrics } from "@/types/round-metrics";
import type { MergeStats, MergeReplicatesStats, SwapWarning } from "@/types/mame/activity";
import { AdvisoryDecisionCard } from "@/components/round/AdvisoryDecisionCard";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Formats a numeric value for display, falling back to "—" for null/undefined. */
function fmt(value: number | null | undefined, decimals = 3): string {
  if (value == null) return "—";
  return value.toFixed(decimals);
}

/** Computes Jaccard similarity for display from two position arrays. */
function jaccardDisplay(a: number[], b: number[]): string {
  const setA = new Set(a);
  const setB = new Set(b);
  const intersection = [...setA].filter((x) => setB.has(x)).length;
  const union = new Set([...setA, ...setB]).size;
  if (union === 0) return "0/0";
  return `${intersection}/${union}`;
}

/** Computes T2 threshold string (1.96·σ·√(2/r)) for display. */
function t2ThresholdDisplay(sigma_assay: number | null, r: number, t: (key: string, opts?: Record<string, string | number>) => string): string {
  if (sigma_assay == null) return t("roundSummarySignals.t2Unavailable");
  const threshold = 1.96 * sigma_assay * Math.sqrt(2 / r);
  return t("roundSummarySignals.t2Threshold", { value: threshold.toFixed(4) });
}

/** Computes hit rate slope label from the most recent 2 rounds (spec L617 window=2). */
function hitRateSlopeDisplay(hit_rates: number[], t: (key: string, opts?: Record<string, string | number>) => string): string {
  if (hit_rates.length < 2) return t("roundSummarySignals.slopeUnavailable");
  // Use only the last 2 data points per spec L617 "recent 2 rounds window"
  const window = hit_rates.slice(-2);
  const slope = window[1] - window[0];
  return t("roundSummarySignals.slopeValue", { slope: slope.toFixed(4), rates: window.map((v) => (v * 100).toFixed(1) + "%").join(", ") });
}

// ---------------------------------------------------------------------------
// Signal row spec
// ---------------------------------------------------------------------------

interface SignalRowData {
  id: string;
  label: string;
  /** null = NA (insufficient data): renders as neutral "NA" badge, distinct from false */
  met: boolean | null;
  inputValue: string;
  /**
   * Short rationale shown in tooltip.
   * Drawn from spec §12-A.1 "추론 근거" column + §12-A.8 anchor labels.
   */
  rationale: string;
  /** True for T1 and T_active which have direct literature anchors. */
  literatureAnchor: boolean;
}

function buildSignalRows(m: RoundMetrics, t: (key: string, opts?: Record<string, string | number>) => string): SignalRowData[] {
  return [
    {
      id: "T1",
      label: t("roundSummarySignals.labelT1"),
      met: m.T1,
      inputValue: `${m.cumulative_beneficial} / K=${m.K_throughput}`,
      rationale:
        "C(K,2) ≤ C_next. Enough beneficial building blocks to fill pairwise combinations in next plate. (Tran 2025, Science; Emelianov 2026, Trends Biotechnol)",
      literatureAnchor: true,
    },
    {
      id: "T2",
      label: t("roundSummarySignals.labelT2"),
      met: m.T2,
      inputValue:
        m.sigma_assay != null
          ? t("roundSummarySignals.t2DeltaBest", { value: fmt(m.delta_best_ema, 4), threshold: t2ThresholdDisplay(m.sigma_assay, m.r, t) })
          : t2ThresholdDisplay(null, m.r, t),
      rationale:
        "Statistical 95% MDE. If Δ_best_EMA < 1.96·σ·√(2/r), no statistically meaningful improvement detected. Reasoning-based signal (not directly formalised in MLDE literature). Note: best-of-N order-statistic null is the formal criterion; displayed value is legacy 1.96·σ·√(2/r).",
      literatureAnchor: false,
    },
    {
      id: "T3",
      label: t("roundSummarySignals.labelT3"),
      met: m.T3,
      inputValue: hitRateSlopeDisplay(m.hit_rates, t),
      rationale:
        "Hit rate slope ≤ 0 indicates active-learning convergence / local saturation. Reasoning-based signal (general active-learning principle).",
      literatureAnchor: false,
    },
    {
      id: "T4",
      label: t("roundSummarySignals.labelT4"),
      met: m.T4,
      inputValue: t("roundSummarySignals.t4Jaccard", { value: jaccardDisplay(m.top_k_positions_n, m.top_k_positions_n1) }),
      rationale:
        "Top-K mutation positions converging across rounds → exploration stalling. Reasoning-based signal (post-hoc justification from Lind 2024 active-site convergence).",
      literatureAnchor: false,
    },
    {
      id: "T_active",
      label: t("roundSummarySignals.labelTActive"),
      met: m.T_active,
      inputValue:
        m.top_k_positions.length > 0 && m.active_residues.length > 0
          ? t("roundSummarySignals.tActiveInSite", { count: String(m.top_k_positions.filter((p) => m.active_residues.includes(p)).length), total: String(m.top_k_positions.length) })
          : t("roundSummarySignals.tActiveEmpty"),
      rationale:
        "active-site spatial proximity = pairwise interaction information value (sign is unpredictable from single data, justifying all-pairwise measurement). Structure prior: Lind 2024 PNAS; Wu 2019 PNAS. Not a prediction of additive stacking success.",
      literatureAnchor: true,
    },
    {
      id: "T_unused",
      label: t("roundSummarySignals.labelTUnused"),
      met: m.T_unused,
      inputValue: t("roundSummarySignals.tUnusedCount", { count: String(m.unused_beneficial_count) }),
      rationale:
        "Baseline-walking uses only the single best variant as next baseline, leaving other beneficial epistatic interactions unexplored. T_unused signals this opportunity. Reasoning-based signal (baseline-walking specific).",
      literatureAnchor: false,
    },
    {
      id: "T_model",
      label: t("roundSummarySignals.labelTModel"),
      met: m.T_model,
      inputValue: Object.keys(m.signal_magnitudes).length > 0
        ? Object.entries(m.signal_magnitudes).map(([k, v]) => `${k}=${v.toFixed(3)}`).join(", ")
        : "surrogate prediction",
      rationale:
        "Surrogate predicts best-single gain within noise of measured best = single-mutant space exhausted. EVOLVEpro Jiang 2024: 10.1126/science.adr6006",
      literatureAnchor: false,
    },
  ];
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// SwapWarningBanner
// ---------------------------------------------------------------------------

/**
 * severity별 배지 카운트를 표시하고 각 경고 항목을 title 속성으로 노출.
 * error count > 0 이면 aria-live="assertive" 알림 포함.
 */
export function SwapWarningBanner({ warnings }: { warnings: SwapWarning[] }) {
  const { t } = useTranslation();
  if (warnings.length === 0) return null;

  const errorCount = warnings.filter((w) => w.severity === "error").length;
  const warnCount = warnings.filter((w) => w.severity === "warning").length;

  return (
    <div className="flex flex-col gap-1.5">
      {errorCount > 0 && (
        <div
          role="alert"
          aria-live="assertive"
          className="flex items-start gap-2 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-800 dark:border-red-800 dark:bg-red-950 dark:text-red-300"
        >
          <span className="mt-0.5 shrink-0 font-bold" aria-hidden="true">🚫</span>
          <span>
            <strong>{t("roundSummary.exportBlocked", { count: errorCount })}</strong>
          </span>
        </div>
      )}
      <div className="flex flex-wrap gap-1.5" aria-label={t("roundSummary.warningsListAria")}>
        {errorCount > 0 && (
          <span className="inline-flex items-center rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-800 dark:bg-red-900 dark:text-red-200">
            {t("roundSummary.errorBadge", { count: errorCount })}
          </span>
        )}
        {warnCount > 0 && (
          <span className="inline-flex items-center rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800 dark:bg-amber-900 dark:text-amber-200">
            {t("roundSummary.warnBadge", { count: warnCount })}
          </span>
        )}
      </div>
      <ul className="space-y-1" aria-label={t("roundSummary.warningDetailAria")}>
        {warnings.map((w, idx) => (
          <li
            key={idx}
            title={t("roundSummary.warningTooltip", { message: w.message, variants: w.variants.join(", "), wells: w.wells.join(", ") })}
            className={cn(
              "cursor-help rounded px-2 py-1 text-xs",
              w.severity === "error"
                ? "bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-300"
                : "bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-300"
            )}
          >
            <span className="font-medium">[{w.code}]</span> {w.message}
          </li>
        ))}
      </ul>
    </div>
  );
}

// ---------------------------------------------------------------------------
// ReplicateMergeStats
// ---------------------------------------------------------------------------

/**
 * replicate merge 통계 4항목을 표시.
 * replicateStats가 null이면 렌더하지 않음 (5/12 demo 경로 회귀 안전).
 * mismatched > 0이면 amber accent + tooltip에 변이 목록.
 */
export function ReplicateMergeStats({ replicateStats }: { replicateStats: MergeReplicatesStats }) {
  const { t } = useTranslation();
  const hasMismatched = replicateStats.mismatched.length > 0;

  return (
    <div
      className="rounded-md border border-border bg-muted/30 px-3 py-2"
      aria-label={t("roundSummary.replicateStatsAria")}
    >
      <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
        {t("roundSummary.replicateMergeTitle")}
      </p>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs sm:grid-cols-4">
        <div className="flex flex-col">
          <dt className="text-muted-foreground">{t("roundSummary.labelRemeasure")}</dt>
          <dd className="font-mono font-medium">{replicateStats.authoritative_count}</dd>
        </div>
        <div className="flex flex-col">
          <dt className="text-muted-foreground">{t("roundSummary.labelPrimary")}</dt>
          <dd className="font-mono font-medium">{replicateStats.fallback_count}</dd>
        </div>
        <div className="flex flex-col">
          <dt className="text-muted-foreground">{t("roundSummary.labelMerged")}</dt>
          <dd className="font-mono font-medium">{replicateStats.merged_count}</dd>
        </div>
        <div className="flex flex-col">
          <dt className="text-muted-foreground">{t("roundSummary.labelMismatched")}</dt>
          <dd
            className={cn(
              "font-mono font-medium",
              hasMismatched
                ? "text-amber-700 dark:text-amber-300"
                : undefined
            )}
            title={
              hasMismatched
                ? t("roundSummary.mismatchedVariantsTooltip", { list: replicateStats.mismatched.join(", ") })
                : undefined
            }
          >
            {replicateStats.mismatched.length}
            {hasMismatched && (
              <span
                className="ml-1 inline-flex items-center rounded-full bg-amber-100 px-1 py-0.5 text-[9px] text-amber-800 dark:bg-amber-900 dark:text-amber-200"
                aria-label={t("roundSummary.mismatchedVariantsAria", { list: replicateStats.mismatched.join(", ") })}
              >
                !
              </span>
            )}
          </dd>
        </div>
      </dl>
    </div>
  );
}

function CalibrationBanner() {
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
      <span>
        <strong>{t("roundSummarySignals.calibrationBannerHeading")}</strong>{" "}
        {t("roundSummarySignals.calibrationBannerBody")}
      </span>
    </div>
  );
}

function SignalBadge({ met }: { met: boolean | null }) {
  const { t } = useTranslation();
  if (met === null) {
    return (
      <Badge
        variant="outline"
        className="min-w-[2rem] justify-center font-mono text-xs text-slate-400 dark:text-slate-500"
        aria-label={t("roundSummarySignals.signalNAAriaLabel")}
      >
        {t("roundSummarySignals.signalNA")}
      </Badge>
    );
  }
  return (
    <Badge
      variant={met ? "default" : "outline"}
      className={cn(
        "min-w-[2rem] justify-center font-mono text-xs",
        met
          ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-900 dark:text-emerald-200"
          : "text-muted-foreground"
      )}
      aria-label={met ? t("roundSummarySignals.signalMetAriaLabel") : t("roundSummarySignals.signalNotMetAriaLabel")}
    >
      {met ? "✓" : "—"}
    </Badge>
  );
}

function RationaleTooltip({
  rationale,
  literatureAnchor,
}: {
  rationale: string;
  literatureAnchor: boolean;
}) {
  const { t } = useTranslation();
  const anchor = literatureAnchor
    ? t("roundSummarySignals.rationaleAnchorLit")
    : t("roundSummarySignals.rationaleAnchorInfer");
  const fullText = `${anchor}\n\n${rationale}`;

  return (
    <span
      role="img"
      aria-label={t("roundSummarySignals.rationaleAriaLabel", { text: fullText })}
      title={fullText}
      className={cn(
        "inline-flex cursor-help items-center rounded-full px-1 py-0.5 text-[10px] font-medium",
        literatureAnchor
          ? "bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300"
          : "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400"
      )}
    >
      {literatureAnchor ? t("roundSummarySignals.rationaleTagLit") : t("roundSummarySignals.rationaleTagInfer")}
    </span>
  );
}

function SignalsTable({ metrics }: { metrics: RoundMetrics }) {
  const { t } = useTranslation();
  const rows = buildSignalRows(metrics, (key, opts) => t(key, opts as Record<string, string>));
  return (
    <Table aria-label={t("roundSummarySignals.signalsTableAriaLabel")}>
      <TableHeader>
        <TableRow>
          <TableHead scope="col" className="w-36 text-xs">
            {t("roundSummarySignals.signalCol")}
          </TableHead>
          <TableHead scope="col" className="w-12 text-center text-xs">
            {t("roundSummarySignals.metCol")}
          </TableHead>
          <TableHead scope="col" className="text-xs">
            {t("roundSummarySignals.inputValueCol")}
          </TableHead>
          <TableHead scope="col" className="w-14 text-center text-xs">
            {t("roundSummarySignals.basisCol")}
          </TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((row) => (
          <TableRow key={row.id}>
            <TableCell className="py-1.5 font-mono text-xs font-medium">
              {row.label}
            </TableCell>
            <TableCell className="py-1.5 text-center">
              <SignalBadge met={row.met} />
            </TableCell>
            <TableCell className="py-1.5 text-xs text-muted-foreground">
              {row.inputValue}
            </TableCell>
            <TableCell className="py-1.5 text-center">
              <RationaleTooltip
                rationale={row.rationale}
                literatureAnchor={row.literatureAnchor}
              />
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export interface RoundSummaryPanelProps {
  /**
   * Computed round metrics from the strategy signal functions.
   * Pass null when no round has been processed — renders an explicit
   * "no data yet" placeholder (no dummy numbers).
   */
  metrics: RoundMetrics | null;
  /**
   * When true, a "(demo)" badge is shown next to the heading to indicate
   * that metrics are derived from a local synthetic fixture rather than a
   * live backend RPC call. Use for 5/12 demo only (Option B, Task 8.5).
   */
  demoMode?: boolean;
  /**
   * Phase C: merge_for_evolvepro RPC 응답의 stats 필드.
   * warnings 배열이 비어있지 않으면 SwapWarningBanner를 렌더.
   * 기존 호출 회귀 방지를 위해 optional.
   */
  mergeStats?: MergeStats | null;
  /**
   * Phase C: merge_for_evolvepro RPC 응답의 replicate_stats 필드.
   * null이면 ReplicateMergeStats를 렌더하지 않음.
   * 기존 호출 회귀 방지를 위해 optional.
   */
  replicateStats?: MergeReplicatesStats | null;
  /**
   * v0.3 advisory: round_id to pass to AdvisoryDecisionCard.
   * When provided, renders the read-only classify() advisory below CalibrationBanner.
   * Optional for backward compatibility with existing callers.
   */
  advisoryRoundId?: string;
  className?: string;
}

/**
 * RoundSummaryPanel
 *
 * Displays per-round strategy signal metrics in calibration mode.
 * Shows signal values (T1–T_unused) + raw inputs + "calibration period" banner.
 * Does NOT display classification decisions (continue_walking / switch_combinatorial / stop).
 * Classification is deferred to v0.3 advisory mode.
 *
 * Spec: §12-A.1 (signals), §12-A.5 (calibration mode), §12-A.6 (5/12 scope).
 */
export function RoundSummaryPanel({
  metrics,
  demoMode = false,
  mergeStats,
  replicateStats,
  advisoryRoundId,
  className,
}: RoundSummaryPanelProps) {
  const { t } = useTranslation();
  const warnings = mergeStats?.warnings ?? [];
  const errorCount = warnings.filter((w) => w.severity === "error").length;
  const hasErrors = errorCount > 0;

  return (
    <section
      aria-labelledby="round-summary-heading"
      className={cn("flex flex-col gap-3", className)}
    >
      <div className="flex items-center justify-between">
        <h3
          id="round-summary-heading"
          className="flex items-center gap-1.5 text-sm font-semibold text-foreground"
        >
          {t("roundSummarySignals.roundSignalsHeading")}
          {demoMode && (
            <span
              className="rounded bg-amber-100 px-1 py-0.5 text-[9px] font-medium uppercase tracking-wide text-amber-700 dark:bg-amber-900 dark:text-amber-300"
              aria-label={t("roundSummarySignals.demoModeAriaLabel")}
            >
              demo
            </span>
          )}
          {hasErrors && (
            <span
              aria-live="assertive"
              className="rounded bg-red-100 px-1 py-0.5 text-[9px] font-medium text-red-700 dark:bg-red-900 dark:text-red-300"
            >
              {t("roundSummary.exportBlockedShort", { count: errorCount })}
            </span>
          )}
        </h3>
        {metrics != null && (
          <span className="text-[10px] text-muted-foreground">
            {metrics.round_id} · computed{" "}
            {new Date(metrics.computed_at).toLocaleString()}
          </span>
        )}
      </div>

      <CalibrationBanner />

      <AdvisoryDecisionCard roundId={advisoryRoundId} />

      {warnings.length > 0 && (
        <SwapWarningBanner warnings={warnings} />
      )}

      {replicateStats != null && (
        <ReplicateMergeStats replicateStats={replicateStats} />
      )}

      {metrics == null ? (
        <p
          className="py-6 text-center text-xs text-muted-foreground"
          aria-live="polite"
        >
          {t("roundSummarySignals.noMetricsYet")}
        </p>
      ) : (
        <div className="overflow-x-auto rounded-md border">
          <SignalsTable metrics={metrics} />
        </div>
      )}
    </section>
  );
}
