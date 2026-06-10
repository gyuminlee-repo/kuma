/**
 * RunHealthPanel — A8 milestone
 *
 * 5-section run-health visualisation. No external chart library.
 * All charts rendered with inline SVG; coordinates computed from data.
 *
 * Sections:
 *  1. Verdict breakdown  — per-plate stacked bar (PASS/AMB/FAIL/Fallback)
 *  2. File size distribution — 7-bucket histogram + cutoff line
 *  3. Barcode distribution — horizontal bar chart (MinKNOW raw, optional)
 *  4. Throughput timeline — line chart (MinKNOW raw, optional)
 *  5. Pore yield indicator — large % + descriptor (MinKNOW raw, optional)
 *
 * Colour rules:
 *  - semantic CSS-variable tokens only (text-success, text-warning, text-error,
 *    text-muted-foreground, text-foreground, bg-muted, etc.)
 *  - SVG fill/stroke via style={{ fill: "hsl(var(--...))" }} — not Tailwind
 *    arbitrary colour classes.
 *  - Zero hardcoded px in Tailwind classes; SVG intrinsic coords are fine.
 */

import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import type {
  CrossTalkCandidate,
  RunHealthBreakdown,
  RunHealthData,
  RunHealthThroughputPoint,
} from "@/types/mame/models";

// ── Colour palette — CSS variable references only ────────────────────────────

const C = {
  pass: "var(--color-success)",
  ambiguous: "var(--color-warning)",
  fail: "hsl(var(--destructive))",
  fallback: "hsl(var(--muted-foreground))",
  primary: "hsl(var(--primary))",
  muted: "hsl(var(--muted-foreground))",
  border: "hsl(var(--border))",
  cutoff: "var(--color-warning)",
  line: "hsl(var(--primary))",
  area: "hsl(var(--primary) / 0.12)",
} as const;

// Verdict-class stacked-bar segments (bottom→top). Each plate bar is normalised
// to 100% height so the verdict MIX is comparable across plates; the absolute
// count is labelled below. "fallback" is a replicate-level overlay (shown as a
// caption), not a verdict class, so it is not a stack segment.
const VERDICT_SEGMENTS: {
  key: "pass" | "ambiguous" | "mixed" | "wrong_aa" | "frameshift" | "many" | "lowdepth" | "no_call";
  label: string;
  fill: string;
}[] = [
  { key: "pass", label: "Pass", fill: "var(--color-success)" },
  { key: "ambiguous", label: "Ambiguous", fill: "var(--color-warning)" },
  { key: "mixed", label: "Mixed", fill: "#fb923c" },
  { key: "wrong_aa", label: "Wrong AA", fill: "hsl(var(--destructive))" },
  { key: "frameshift", label: "Frameshift", fill: "#b91c1c" },
  { key: "many", label: "Many", fill: "#a855f7" },
  { key: "lowdepth", label: "Low depth", fill: "#94a3b8" },
  { key: "no_call", label: "No call", fill: "#475569" },
];

/** Friendly plate label: "sort_barcode06" → "NB06"; non-numeric names stay as-is. */
function plateLabel(plate: string): string {
  const m = plate.match(/(\d+)/);
  return m ? `NB${m[1]}` : plate;
}

// ── Tiny helpers ─────────────────────────────────────────────────────────────

function safeMax(arr: number[]): number {
  return arr.length === 0 ? 1 : Math.max(...arr);
}

// ── Section 1: Verdict breakdown stacked bar ─────────────────────────────────

interface VerdictBreakdownProps {
  perPlate: Record<string, RunHealthBreakdown>;
  recoveredMutants: number | null;
  totalMutants: number | null;
  recoveryRate: number | null;
}

function VerdictBreakdown({
  perPlate,
  recoveredMutants,
  totalMutants,
  recoveryRate,
}: VerdictBreakdownProps) {
  const { t } = useTranslation();
  const plates = Object.entries(perPlate).sort(([a], [b]) => {
    const na = a.match(/(\d+)/);
    const nb = b.match(/(\d+)/);
    const ka = na ? parseInt(na[1], 10) : Number.MAX_SAFE_INTEGER;
    const kb = nb ? parseInt(nb[1], 10) : Number.MAX_SAFE_INTEGER;
    return ka - kb || a.localeCompare(b);
  });

  // AC8: recovery (재현율) header — non-null shows "R/T (Z%)", null shows n/a.
  const recoveryAvailable = recoveredMutants !== null && totalMutants !== null;
  const recoveryPct = recoveryRate !== null ? Math.round(recoveryRate * 100) : 0;
  const recoveryHeader = (
    <div className="flex flex-wrap items-baseline gap-x-2 text-sm" data-testid="run-health-recovery">
      <span className="font-semibold uppercase tracking-widest text-muted-foreground">
        {t("mame.runHealth.recovery")}
      </span>
      <span className="text-base font-semibold tabular-nums text-foreground">
        {recoveryAvailable
          ? t("mame.runHealth.recoveryValue", {
              recovered: recoveredMutants,
              total: totalMutants,
              pct: recoveryPct,
            })
          : t("mame.runHealth.recoveryNa")}
      </span>
    </div>
  );

  // AC10: run-level per-class counts summed across every plate.
  const classCounts = VERDICT_SEGMENTS.map(({ key, label }) => ({
    key,
    label,
    count: plates.reduce((acc, [, b]) => acc + (b[key] ?? 0), 0),
  }));

  if (plates.length === 0) return recoveryHeader;

  const barW = 44;
  const gap = 24;
  const chartH = 120;
  const labelH = 30;
  const svgW = plates.length * (barW + gap) + gap;
  const svgH = chartH + labelH;

  return (
    <div className="flex flex-col gap-3">
      {recoveryHeader}
      <figure className="w-full overflow-x-auto" aria-label={t("mame.runHealth.verdictBreakdown")}>
        <svg
          viewBox={`0 0 ${svgW} ${svgH}`}
          width="100%"
          style={{ maxWidth: svgW * 1.6 }}
          preserveAspectRatio="xMinYMin meet"
          role="img"
          aria-label={t("mame.runHealth.verdictBreakdown")}
        >
          <title>{t("mame.runHealth.verdictBreakdown")}</title>
          {plates.map(([plate, b], i) => {
            const x = gap + i * (barW + gap);
            const total = b.total || 0;
            let yOffset = chartH;
            return (
              <g key={plate}>
                {total === 0 ? (
                  <rect x={x} y={0} width={barW} height={chartH} rx={3} style={{ fill: "hsl(var(--muted))" }} />
                ) : (
                  VERDICT_SEGMENTS.map(({ key, label, fill }) => {
                    const value = b[key] ?? 0;
                    if (value === 0) return null;
                    const h = (value / total) * chartH;
                    yOffset -= h;
                    const pct = Math.round((value / total) * 100);
                    const segTop = yOffset;
                    return (
                      <g key={key}>
                        <rect x={x} y={segTop} width={barW} height={h} style={{ fill }}>
                          <title>{`${plateLabel(plate)} · ${label}: ${value} (${pct}%)`}</title>
                        </rect>
                        {h >= 11 && (
                          <text
                            x={x + barW / 2}
                            y={segTop + h / 2}
                            textAnchor="middle"
                            dominantBaseline="central"
                            data-testid="seg-count"
                            style={{
                              fill: "#fff",
                              fontSize: 9,
                              fontWeight: 600,
                              stroke: "rgba(0,0,0,0.45)",
                              strokeWidth: 2,
                              paintOrder: "stroke",
                              pointerEvents: "none",
                            }}
                          >
                            {value}
                          </text>
                        )}
                      </g>
                    );
                  })
                )}
                <text
                  x={x + barW / 2}
                  y={chartH + 13}
                  textAnchor="middle"
                  style={{ fill: C.muted, fontSize: 10 }}
                >
                  {plateLabel(plate)}
                </text>
                <text
                  x={x + barW / 2}
                  y={chartH + 25}
                  textAnchor="middle"
                  style={{ fill: C.muted, fontSize: 8 }}
                >
                  {`n=${total}${b.fallback ? ` · fb ${b.fallback}` : ""}`}
                </text>
              </g>
            );
          })}
        </svg>
        <figcaption className="sr-only">
          {t("mame.runHealth.figureVerdictBreakdownCaption")}
        </figcaption>
      </figure>
      <table className="w-full text-caption" data-testid="run-health-class-counts">
        <caption className="sr-only">{t("mame.runHealth.classCountTableCaption")}</caption>
        <thead>
          <tr className="text-left text-muted-foreground">
            <th scope="col" className="py-0.5 pr-2 font-medium">
              {t("mame.runHealth.classCountColClass")}
            </th>
            <th scope="col" className="py-0.5 text-right font-medium">
              {t("mame.runHealth.classCountColCount")}
            </th>
          </tr>
        </thead>
        <tbody>
          {classCounts.map(({ key, label, count }) => (
            <tr key={key}>
              <th scope="row" className="py-0.5 pr-2 font-normal text-foreground">
                {label}
              </th>
              <td className="py-0.5 text-right tabular-nums text-foreground">{count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Section 2: File size histogram ───────────────────────────────────────────

interface FileSizeHistogramProps {
  distribution: Record<string, number>;
  cutoffKb: number;
  bimodal: boolean;
  method: string;
}

const HIST_KEYS = ["min", "p05", "p25", "median", "p75", "p95", "max"] as const;

function FileSizeHistogram({ distribution, cutoffKb, bimodal, method }: FileSizeHistogramProps) {
  const { t } = useTranslation();
  const values = HIST_KEYS.map((k) => distribution[k] ?? 0);
  const maxVal = safeMax(values);

  const chartH = 80;
  const barW = 28;
  const gap = 8;
  const leftPad = 8;
  const svgW = leftPad + HIST_KEYS.length * (barW + gap) + gap;
  const labelH = 28;
  const svgH = chartH + labelH;

  // Cutoff line x position (proportional within max)
  const cutoffRatio = maxVal > 0 ? Math.min(cutoffKb / maxVal, 1) : 0;
  const cutoffX = leftPad + cutoffRatio * (svgW - leftPad - gap);

  return (
    <figure
      className="w-full overflow-x-auto"
      aria-label={
        bimodal
          ? t("mame.runHealth.fileSizeAriaLabelBimodal", { cutoffKb: cutoffKb.toFixed(1), method })
          : t("mame.runHealth.fileSizeAriaLabel", { cutoffKb: cutoffKb.toFixed(1), method })
      }
    >
      <svg
        viewBox={`0 0 ${svgW} ${svgH}`}
        width="100%"
        preserveAspectRatio="xMinYMin meet"
        role="img"
        aria-label={t("mame.runHealth.fileSizeDistribution")}
      >
        <title>{t("mame.runHealth.fileSizeDistribution")}</title>
        {HIST_KEYS.map((key, i) => {
          const val = distribution[key] ?? 0;
          const h = maxVal > 0 ? (val / maxVal) * chartH : 0;
          const x = leftPad + i * (barW + gap);
          const y = chartH - h;
          return (
            <g key={key}>
              <rect
                x={x}
                y={y}
                width={barW}
                height={h}
                style={{ fill: C.primary, opacity: 0.75 }}
                rx={2}
              >
                <title>{`${key}: ${val.toFixed(1)} KB`}</title>
              </rect>
              <text
                x={x + barW / 2}
                y={chartH + 12}
                textAnchor="middle"
                style={{ fill: C.muted, fontSize: 8 }}
              >
                {key}
              </text>
              <text
                x={x + barW / 2}
                y={chartH + 22}
                textAnchor="middle"
                style={{ fill: C.muted, fontSize: 7 }}
              >
                {val.toFixed(0)}
              </text>
            </g>
          );
        })}
        {/* Cutoff vertical line */}
        <line
          x1={cutoffX}
          y1={0}
          x2={cutoffX}
          y2={chartH}
          style={{ stroke: C.cutoff, strokeWidth: 1.5, strokeDasharray: "4 2" }}
        />
        <text
          x={cutoffX + 3}
          y={10}
          style={{ fill: C.cutoff, fontSize: 8 }}
        >
          {`${cutoffKb.toFixed(0)} KB`}
        </text>
      </svg>
      <figcaption className="sr-only">
        {bimodal
          ? t("mame.runHealth.figureFileSizeCaptionBimodal", { cutoffKb: cutoffKb.toFixed(1), method })
          : t("mame.runHealth.figureFileSizeCaptionBase", { cutoffKb: cutoffKb.toFixed(1), method })}
      </figcaption>
    </figure>
  );
}

// ── Section 3: Barcode distribution ──────────────────────────────────────────

interface BarcodeDistributionProps {
  distribution: Record<string, number>;
}

function BarcodeDistribution({ distribution }: BarcodeDistributionProps) {
  const { t } = useTranslation();
  const entries = useMemo(
    () => Object.entries(distribution).sort((a, b) => b[1] - a[1]),
    [distribution],
  );
  if (entries.length === 0) return null;

  const rowH = 16;
  const labelW = 70;
  const chartW = 180;
  const gap = 4;
  const svgH = entries.length * (rowH + gap);
  const svgW = labelW + chartW + 8;
  const maxCount = safeMax(entries.map(([, v]) => v));

  return (
    <figure className="w-full max-h-72 overflow-y-auto" aria-label={t("mame.runHealth.barcodeDistribution")}>
      <svg
        viewBox={`0 0 ${svgW} ${svgH}`}
        width="100%"
        preserveAspectRatio="xMinYMin meet"
        role="img"
        aria-label={t("mame.runHealth.barcodeDistribution")}
      >
        <title>{t("mame.runHealth.barcodeDistribution")}</title>
        {entries.map(([barcode, count], i) => {
          const y = i * (rowH + gap);
          const barLen = maxCount > 0 ? (count / maxCount) * chartW : 0;
          return (
            <g key={barcode}>
              <text
                x={labelW - 4}
                y={y + rowH * 0.75}
                textAnchor="end"
                style={{ fill: C.muted, fontSize: 8 }}
              >
                {barcode.length > 11 ? `${barcode.slice(0, 11)}…` : barcode}
              </text>
              <rect
                x={labelW}
                y={y + 2}
                width={barLen}
                height={rowH - 4}
                style={{ fill: C.primary, opacity: 0.8 }}
                rx={2}
              >
                <title>{`${barcode}: ${count.toLocaleString()} reads`}</title>
              </rect>
              <text
                x={labelW + barLen + 3}
                y={y + rowH * 0.75}
                style={{ fill: C.muted, fontSize: 7 }}
              >
                {count >= 1000 ? `${(count / 1000).toFixed(1)}k` : count}
              </text>
            </g>
          );
        })}
      </svg>
      <figcaption className="sr-only">
        {t("mame.runHealth.figureBarcodeCaption")}
      </figcaption>
    </figure>
  );
}

// ── Section 4: Throughput timeline ───────────────────────────────────────────

interface ThroughputTimelineProps {
  points: RunHealthThroughputPoint[];
}

function ThroughputTimeline({ points }: ThroughputTimelineProps) {
  const { t } = useTranslation();
  if (points.length < 2) return null;

  const chartW = 240;
  const chartH = 72;
  const padL = 8;
  const padR = 8;
  const padT = 6;
  const padB = 18;
  const innerW = chartW - padL - padR;
  const innerH = chartH - padT - padB;

  const maxTime = safeMax(points.map((p) => p.time_h));
  const maxRps = safeMax(points.map((p) => p.reads_per_sec));

  function tx(time_h: number): number {
    return padL + (maxTime > 0 ? (time_h / maxTime) * innerW : 0);
  }
  function ty(rps: number): number {
    return padT + (maxRps > 0 ? (1 - rps / maxRps) * innerH : innerH);
  }

  const polyline = points.map((p) => `${tx(p.time_h)},${ty(p.reads_per_sec)}`).join(" ");
  const areaPath = [
    `M ${tx(points[0].time_h)} ${ty(0)}`,
    ...points.map((p) => `L ${tx(p.time_h)} ${ty(p.reads_per_sec)}`),
    `L ${tx(points[points.length - 1].time_h)} ${ty(0)}`,
    "Z",
  ].join(" ");

  const totalH = chartH;
  const svgW = chartW;

  return (
    <figure
      className="w-full overflow-x-auto"
      aria-label={t("mame.runHealth.throughputAriaLabel", { maxTime: maxTime.toFixed(1) })}
    >
      <svg
        viewBox={`0 0 ${svgW} ${totalH}`}
        width="100%"
        preserveAspectRatio="xMinYMin meet"
        role="img"
        aria-label={t("mame.runHealth.throughputTimeline")}
      >
        <title>{t("mame.runHealth.throughputTimeline")}</title>
        {/* Area fill */}
        <path d={areaPath} style={{ fill: C.area }} />
        {/* Line */}
        <polyline
          points={polyline}
          style={{ fill: "none", stroke: C.line, strokeWidth: 1.5, strokeLinecap: "round" }}
        />
        {/* Axis labels */}
        <text x={padL} y={totalH} style={{ fill: C.muted, fontSize: 7 }}>
          0h
        </text>
        <text
          x={svgW - padR}
          y={totalH}
          textAnchor="end"
          style={{ fill: C.muted, fontSize: 7 }}
        >
          {`${maxTime.toFixed(1)}h`}
        </text>
        <text x={padL} y={padT + 6} style={{ fill: C.muted, fontSize: 7 }}>
          {maxRps >= 1000 ? `${(maxRps / 1000).toFixed(1)}k r/s` : `${maxRps.toFixed(0)} r/s`}
        </text>
      </svg>
      <figcaption className="sr-only">
        {t("mame.runHealth.figureThroughputCaption", { maxTime: maxTime.toFixed(1) })}
      </figcaption>
    </figure>
  );
}

// ── Section 5: Pore yield indicator ──────────────────────────────────────────

interface PoreYieldProps {
  pct: number;
}

function PoreYield({ pct }: PoreYieldProps) {
  const { t } = useTranslation();
  const toneClass =
    pct >= 75
      ? "text-success"
      : pct >= 50
        ? "text-warning"
        : "text-destructive";

  return (
    <div
      className="flex flex-col items-center gap-1 py-2"
      role="status"
      aria-label={t("mame.runHealth.poreYieldAriaLabel", { pct: pct.toFixed(1) })}
    >
      <span className={cn("font-display text-4xl font-bold tabular-nums", toneClass)}>
        {pct.toFixed(1)}%
      </span>
      <span className="text-caption text-muted-foreground">
        {t("mame.runHealth.finalActivePoreYield")}
      </span>
    </div>
  );
}

// ── Legend ────────────────────────────────────────────────────────────────────

function Legend() {
  const { t } = useTranslation();
  return (
    <div
      className="flex flex-wrap gap-x-3 gap-y-1"
      aria-label={t("mame.runHealth.legendAriaLabel")}
      role="list"
    >
      {VERDICT_SEGMENTS.map(({ key, label, fill }) => (
        <div key={key} className="flex items-center gap-1.5" role="listitem">
          <span
            className="h-2.5 w-2.5 flex-shrink-0 rounded-sm"
            style={{ backgroundColor: fill }}
            aria-hidden="true"
          />
          <span className="text-caption text-muted-foreground">{label}</span>
        </div>
      ))}
    </div>
  );
}

// ── Section 6: Cross-talk candidates ─────────────────────────────────────────

interface CrossTalkAlertsProps {
  candidates: CrossTalkCandidate[];
}

const SEVERITY_CLASS: Record<CrossTalkCandidate["severity"], string> = {
  high: "text-destructive",
  medium: "text-warning",
  low: "text-info",
};

const SEVERITY_BORDER: Record<CrossTalkCandidate["severity"], string> = {
  high: "border-destructive/40",
  medium: "border-warning/40",
  low: "border-info/40",
};

function CrossTalkAlerts({ candidates }: CrossTalkAlertsProps) {
  const { t } = useTranslation();
  // Sort by z_score descending (defensive: backend already sorts, but guard here too)
  const sorted = [...candidates].sort((a, b) => b.z_score - a.z_score);

  if (sorted.length === 0) {
    return (
      <p className="text-caption text-muted-foreground" role="status">
        {t("mame.runHealth.noCrossTalk")}
      </p>
    );
  }

  return (
    <div className="overflow-x-auto" role="region" aria-label={t("mame.runHealth.crossTalkAriaLabel")}>
      <table className="w-full text-caption" aria-label={t("mame.runHealth.crossTalkTableAriaLabel")}>
        <thead>
          <tr className="border-b border-border text-left text-muted-foreground">
            <th scope="col" className="py-1 pr-3 font-medium">
              {t("mame.runHealth.colWell")}
            </th>
            <th scope="col" className="py-1 pr-3 font-medium">
              {t("mame.runHealth.colReads")}
            </th>
            <th scope="col" className="py-1 pr-3 font-medium">
              {t("mame.runHealth.colNeighborAvg")}
            </th>
            <th scope="col" className="py-1 pr-3 font-medium">
              {t("mame.runHealth.colZScore")}
            </th>
            <th scope="col" className="py-1 font-medium">
              {t("mame.runHealth.colSeverity")}
            </th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((c) => (
            <tr
              key={`${c.well}-${c.z_score}`}
              className="border-b border-border/50 last:border-0"
              title={c.note}
            >
              <td className="py-1 pr-3 font-mono tabular-nums">{c.well}</td>
              <td className="py-1 pr-3 tabular-nums">
                {c.read_count.toLocaleString()}
              </td>
              <td className="py-1 pr-3 tabular-nums">
                {c.neighbor_avg.toLocaleString(undefined, { maximumFractionDigits: 0 })}
              </td>
              <td className="py-1 pr-3 tabular-nums">{c.z_score.toFixed(2)}</td>
              <td className="py-1">
                <span
                  className={cn(
                    "rounded-control border px-1.5 py-0.5",
                    SEVERITY_CLASS[c.severity],
                    SEVERITY_BORDER[c.severity],
                  )}
                  aria-label={t("mame.runHealth.severityAriaLabel", { severity: c.severity })}
                >
                  {c.severity}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Main panel component ──────────────────────────────────────────────────────

export type RunHealthSection =
  | "verdict-breakdown"
  | "file-size"
  | "throughput"
  | "pore-yield"
  | "barcode"
  | "cross-talk";

/** Sub-set presets for embedding inside other sub-steps. */
export const RUN_HEALTH_VERDICT_SECTIONS: readonly RunHealthSection[] = [
  "file-size",
  "throughput",
  "pore-yield",
];
export const RUN_HEALTH_PLATE_SECTIONS: readonly RunHealthSection[] = [
  "verdict-breakdown",
  "barcode",
  "cross-talk",
];

interface RunHealthPanelProps {
  health: RunHealthData;
  /** Filter which sections to render. Renders all sections when omitted. */
  sections?: readonly RunHealthSection[];
  className?: string;
}

export function RunHealthPanel({ health, sections, className }: RunHealthPanelProps) {
  const { t } = useTranslation();
  const hasMinKnow =
    health.pore_yield_pct !== null ||
    health.throughput_timeline !== null ||
    health.barcode_distribution !== null;

  const show = (s: RunHealthSection) => sections === undefined || sections.includes(s);

  return (
    <div
      className={cn("grid gap-4 p-4 md:grid-cols-2", className)}
      role="region"
      aria-label={t("mame.runHealth.panelAriaLabel")}
    >
      {/* Section 1: Verdict breakdown */}
      {show("verdict-breakdown") && (
        <section aria-labelledby="vh-verdict-heading" className="flex flex-col gap-2">
          <h3
            id="vh-verdict-heading"
            className="text-caption font-semibold uppercase tracking-widest text-muted-foreground"
          >
            {t("mame.runHealth.verdictBreakdown")}
          </h3>
          <Legend />
          <VerdictBreakdown
            perPlate={health.per_plate_summary}
            recoveredMutants={health.recovered_mutants}
            totalMutants={health.total_mutants}
            recoveryRate={health.recovery_rate}
          />
        </section>
      )}

      {/* Section 2: File size distribution */}
      {show("file-size") && (
        <section aria-labelledby="vh-dist-heading" className="flex flex-col gap-2">
          <h3
            id="vh-dist-heading"
            className="text-caption font-semibold uppercase tracking-widest text-muted-foreground"
          >
            {t("mame.runHealth.fileSizeDistribution")}
          </h3>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-caption text-muted-foreground">
            <span>
              {t("mame.runHealth.method")}:{" "}
              <span className="font-medium text-foreground">{health.suggested_method}</span>
            </span>
            {health.bimodal && (
              <span className="rounded-control border border-warning/40 px-1.5 py-0.5 text-warning">
                {t("mame.runHealth.bimodalBadge")}
              </span>
            )}
          </div>
          {Object.keys(health.file_size_distribution).length > 0 ? (
            <FileSizeHistogram
              distribution={health.file_size_distribution}
              cutoffKb={health.suggested_cutoff_kb}
              bimodal={health.bimodal}
              method={health.suggested_method}
            />
          ) : (
            <p className="text-caption text-muted-foreground">{t("mame.runHealth.noDistributionData")}</p>
          )}
        </section>
      )}

      {/* MinKNOW sections: rendered only when raw run data is available */}
      {hasMinKnow && (
        <>
          {/* Section 5: Pore yield */}
          {show("pore-yield") && health.pore_yield_pct !== null && (
            <section aria-labelledby="vh-pore-heading" className="flex flex-col gap-2">
              <h3
                id="vh-pore-heading"
                className="text-caption font-semibold uppercase tracking-widest text-muted-foreground"
              >
                {t("mame.runHealth.poreYield")}
              </h3>
              <PoreYield pct={health.pore_yield_pct} />
            </section>
          )}

          {/* Section 4: Throughput timeline */}
          {show("throughput") && health.throughput_timeline !== null && health.throughput_timeline.length >= 2 && (
            <section aria-labelledby="vh-throughput-heading" className="flex flex-col gap-2">
              <h3
                id="vh-throughput-heading"
                className="text-caption font-semibold uppercase tracking-widest text-muted-foreground"
              >
                {t("mame.runHealth.throughputTimeline")}
              </h3>
              <ThroughputTimeline points={health.throughput_timeline} />
            </section>
          )}

          {/* Section 3: Barcode distribution */}
          {show("barcode") && health.barcode_distribution !== null &&
            Object.keys(health.barcode_distribution).length > 0 && (
              <section
                aria-labelledby="vh-barcode-heading"
                className="col-span-full flex flex-col gap-2 md:col-span-2"
              >
                <h3
                  id="vh-barcode-heading"
                  className="text-caption font-semibold uppercase tracking-widest text-muted-foreground"
                >
                  {t("mame.runHealth.barcodeDistribution")}
                </h3>
                <BarcodeDistribution distribution={health.barcode_distribution} />
              </section>
            )}
        </>
      )}

      {/* Section 6: Cross-talk detection (A9) */}
      {show("cross-talk") && (
        <section
          aria-labelledby="vh-crosstalk-heading"
          className="col-span-full flex flex-col gap-2"
        >
          <h3
            id="vh-crosstalk-heading"
            className="text-caption font-semibold uppercase tracking-widest text-muted-foreground"
          >
            {t("mame.runHealth.crossTalkCandidates")}
          </h3>
          <CrossTalkAlerts candidates={health.cross_talk_candidates} />
        </section>
      )}

      {!hasMinKnow && sections === undefined && (
        <div className="col-span-full">
          <p className="text-caption text-muted-foreground">
            {t("mame.runHealth.noMinKnow")}
          </p>
        </div>
      )}
    </div>
  );
}
