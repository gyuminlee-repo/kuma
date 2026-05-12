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
function t2ThresholdDisplay(sigma_assay: number | null, r: number): string {
  if (sigma_assay == null) return "WT replicates < 4, T2 unavailable";
  const threshold = 1.96 * sigma_assay * Math.sqrt(2 / r);
  return `threshold = ${threshold.toFixed(4)}`;
}

/** Computes hit rate slope label from array of rates. */
function hitRateSlopeDisplay(hit_rates: number[]): string {
  if (hit_rates.length < 2) return "< 2 rounds, slope unavailable";
  const n = hit_rates.length;
  const x = Array.from({ length: n }, (_, i) => i);
  const xMean = x.reduce((a, b) => a + b, 0) / n;
  const yMean = hit_rates.reduce((a, b) => a + b, 0) / n;
  const num = x.reduce((sum, xi, i) => sum + (xi - xMean) * (hit_rates[i] - yMean), 0);
  const den = x.reduce((sum, xi) => sum + (xi - xMean) ** 2, 0);
  const slope = den === 0 ? 0 : num / den;
  return `slope = ${slope.toFixed(4)} (${hit_rates.map((v) => (v * 100).toFixed(1) + "%").join(", ")})`;
}

// ---------------------------------------------------------------------------
// Signal row spec
// ---------------------------------------------------------------------------

interface SignalRowData {
  id: string;
  label: string;
  met: boolean;
  inputValue: string;
  /**
   * Short rationale shown in tooltip.
   * Drawn from spec §12-A.1 "추론 근거" column + §12-A.8 anchor labels.
   */
  rationale: string;
  /** True for T1 and T_active which have direct literature anchors. */
  literatureAnchor: boolean;
}

function buildSignalRows(m: RoundMetrics): SignalRowData[] {
  return [
    {
      id: "T1",
      label: "T1 — Throughput",
      met: m.T1,
      inputValue: `${m.cumulative_beneficial} / K=${m.K_throughput}`,
      rationale:
        "C(K,2) ≤ C_next. Enough beneficial building blocks to fill pairwise combinations in next plate. (Tran 2025, Science; Emelianov 2026, Trends Biotechnol)",
      literatureAnchor: true,
    },
    {
      id: "T2",
      label: "T2 — Plateau",
      met: m.T2,
      inputValue:
        m.sigma_assay != null
          ? `Δ_best = ${fmt(m.delta_best_ema, 4)} | ${t2ThresholdDisplay(m.sigma_assay, m.r)}`
          : t2ThresholdDisplay(null, m.r),
      rationale:
        "Statistical 95% MDE. If Δ_best_EMA < 1.96·σ·√(2/r), no statistically meaningful improvement detected. Reasoning-based signal (not directly formalised in MLDE literature).",
      literatureAnchor: false,
    },
    {
      id: "T3",
      label: "T3 — Hit rate",
      met: m.T3,
      inputValue: hitRateSlopeDisplay(m.hit_rates),
      rationale:
        "Hit rate slope ≤ 0 indicates active-learning convergence / local saturation. Reasoning-based signal (general active-learning principle).",
      literatureAnchor: false,
    },
    {
      id: "T4",
      label: "T4 — Position convergence",
      met: m.T4,
      inputValue: `Jaccard = ${jaccardDisplay(m.top_k_positions_n, m.top_k_positions_n1)} (threshold ≥ 0.5)`,
      rationale:
        "Top-K mutation positions converging across rounds → exploration stalling. Reasoning-based signal (post-hoc justification from Lind 2024 active-site convergence).",
      literatureAnchor: false,
    },
    {
      id: "T_active",
      label: "T_active — Active site",
      met: m.T_active,
      inputValue:
        m.top_k_positions.length > 0 && m.active_residues.length > 0
          ? `${m.top_k_positions.filter((p) => m.active_residues.includes(p)).length} / ${m.top_k_positions.length} in active site`
          : "active-residue list or top-K empty",
      rationale:
        "Fraction of top-K positions in active site ≥ 0.4. Direct literature anchor: Lind 2024 PNAS sign epistasis; Wu 2019 PNAS epistatic sites.",
      literatureAnchor: true,
    },
    {
      id: "T_unused",
      label: "T_unused — Unused beneficial",
      met: m.T_unused,
      inputValue: `${m.unused_beneficial_count} unused (M_min = 5)`,
      rationale:
        "Baseline-walking uses only the single best variant as next baseline, leaving other beneficial epistatic interactions unexplored. T_unused signals this opportunity. Reasoning-based signal (baseline-walking specific).",
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
        <strong>Calibration period — classification inactive.</strong> Signal
        values are displayed for monitoring only. Automated classification
        decisions are not shown until advisory mode is enabled (Round 3+,
        v0.3).
      </span>
    </div>
  );
}

function SignalBadge({ met }: { met: boolean }) {
  return (
    <Badge
      variant={met ? "default" : "outline"}
      className={cn(
        "min-w-[2rem] justify-center font-mono text-xs",
        met
          ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-900 dark:text-emerald-200"
          : "text-muted-foreground"
      )}
      aria-label={met ? "Signal met" : "Signal not met"}
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
  const anchor = literatureAnchor
    ? "Literature-anchored signal."
    : "Reasoning-based signal (not directly formalised in MLDE literature).";
  const fullText = `${anchor}\n\n${rationale}`;

  return (
    <span
      role="img"
      aria-label={`Rationale: ${fullText}`}
      title={fullText}
      className={cn(
        "inline-flex cursor-help items-center rounded-full px-1 py-0.5 text-[10px] font-medium",
        literatureAnchor
          ? "bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300"
          : "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400"
      )}
    >
      {literatureAnchor ? "lit" : "infer"}
    </span>
  );
}

function SignalsTable({ rows }: { rows: SignalRowData[] }) {
  return (
    <Table aria-label="Round strategy signals">
      <TableHeader>
        <TableRow>
          <TableHead scope="col" className="w-36 text-xs">
            Signal
          </TableHead>
          <TableHead scope="col" className="w-12 text-center text-xs">
            Met
          </TableHead>
          <TableHead scope="col" className="text-xs">
            Input value
          </TableHead>
          <TableHead scope="col" className="w-14 text-center text-xs">
            Basis
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
          Round Signals
          {demoMode && (
            <span
              className="rounded bg-amber-100 px-1 py-0.5 text-[9px] font-medium uppercase tracking-wide text-amber-700 dark:bg-amber-900 dark:text-amber-300"
              aria-label="Demo mode: metrics are synthesised from local merge stats, not a live backend RPC"
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
          No round metrics yet — complete an ALE round to compute signals.
        </p>
      ) : (
        <div className="overflow-x-auto rounded-md border">
          <SignalsTable rows={buildSignalRows(metrics)} />
        </div>
      )}
    </section>
  );
}
