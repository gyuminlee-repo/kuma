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
import { VERDICT_FILL, VERDICT_LABEL } from "@/lib/mame/verdictColors";
import { nbLabel, nbOrderKey } from "@/lib/mame/nbLabel";
import { useMameAppStore } from "@/store/mame/mameAppStore";
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
  { key: "pass", label: VERDICT_LABEL.PASS, fill: VERDICT_FILL.PASS.bg },
  { key: "ambiguous", label: VERDICT_LABEL.AMBIGUOUS, fill: VERDICT_FILL.AMBIGUOUS.bg },
  { key: "mixed", label: VERDICT_LABEL.MIXED, fill: VERDICT_FILL.MIXED.bg },
  { key: "wrong_aa", label: VERDICT_LABEL.WRONG_AA, fill: VERDICT_FILL.WRONG_AA.bg },
  { key: "frameshift", label: VERDICT_LABEL.FRAMESHIFT, fill: VERDICT_FILL.FRAMESHIFT.bg },
  { key: "many", label: VERDICT_LABEL.MANY, fill: VERDICT_FILL.MANY.bg },
  { key: "lowdepth", label: VERDICT_LABEL.LOWDEPTH, fill: VERDICT_FILL.LOWDEPTH.bg },
  { key: "no_call", label: VERDICT_LABEL.NO_CALL, fill: VERDICT_FILL.NO_CALL.bg },
];

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
  const replicates = useMameAppStore((state) => state.replicates);
  const plates = Object.entries(perPlate).sort(
    ([a], [b]) => nbOrderKey(a) - nbOrderKey(b) || a.localeCompare(b),
  );

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

  // Per-mutant recovery distribution (pass / ambiguous / not recovered).
  // Denominator and the not-recovered count come from the same backend scalars
  // as the recovery header (designed mutants only), so the bar can never
  // contradict the header. The Pass/Ambiguous split is read from the selected
  // replicate verdicts, excluding the WT control and UNKNOWN_* fallback groups
  // (backend sentinel mutant ids) which are not designed mutants; designed
  // recovered mutants always carry a PASS/AMBIGUOUS selected verdict, so
  // passN + ambN == recoveredMutants.
  const mutantRecoveryBar = useMemo(() => {
    const total = totalMutants ?? 0;
    const recovered = recoveredMutants ?? 0;
    if (total === 0) return null;
    const isDesigned = (id: string) => id !== "WT" && !id.startsWith("UNKNOWN_");
    const selVerdict = (r: (typeof replicates)[number]) =>
      r.selected_plate !== null ? r.plate_verdicts[r.selected_plate]?.verdict : undefined;
    const passN = replicates.filter((r) => isDesigned(r.mutant_id) && selVerdict(r) === "PASS").length;
    const ambN = replicates.filter((r) => isDesigned(r.mutant_id) && selVerdict(r) === "AMBIGUOUS").length;
    const notRec = Math.max(0, total - recovered);
    const denom = passN + ambN + notRec;
    const pPct = denom > 0 ? (passN / denom) * 100 : 0;
    const aPct = denom > 0 ? (ambN / denom) * 100 : 0;
    const nPct = denom > 0 ? (notRec / denom) * 100 : 0;
    return (
      <div className="flex flex-col gap-1.5">
        <span className="text-caption font-semibold uppercase tracking-widest text-muted-foreground">
          {t("mame.runHealth.mutantRecoveryTitle")}
        </span>
        <div className="flex h-3 w-full overflow-hidden rounded-full">
          {pPct > 0 && (
            <div style={{ width: `${pPct}%`, backgroundColor: VERDICT_FILL.PASS.bg }} title={`${VERDICT_LABEL.PASS}: ${passN}`} />
          )}
          {aPct > 0 && (
            <div style={{ width: `${aPct}%`, backgroundColor: VERDICT_FILL.AMBIGUOUS.bg }} title={`${VERDICT_LABEL.AMBIGUOUS}: ${ambN}`} />
          )}
          {nPct > 0 && (
            <div style={{ width: `${nPct}%`, backgroundColor: VERDICT_FILL.NO_CALL.bg }} title={`${t("mame.runHealth.notRecovered")}: ${notRec}`} />
          )}
        </div>
        <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-caption text-muted-foreground">
          <span><span className="inline-block h-2 w-2 rounded-sm mr-1" style={{ backgroundColor: VERDICT_FILL.PASS.bg }} aria-hidden="true" />{t("mame.runHealth.recoveredViaPass")}: {passN}</span>
          <span><span className="inline-block h-2 w-2 rounded-sm mr-1" style={{ backgroundColor: VERDICT_FILL.AMBIGUOUS.bg }} aria-hidden="true" />{t("mame.runHealth.recoveredViaAmbiguous")}: {ambN}</span>
          <span><span className="inline-block h-2 w-2 rounded-sm mr-1" style={{ backgroundColor: VERDICT_FILL.NO_CALL.bg }} aria-hidden="true" />{t("mame.runHealth.notRecovered")}: {notRec}</span>
        </div>
      </div>
    );
  }, [replicates, totalMutants, t]);

  // AC10: run-level per-class counts summed across every plate.
  const classCounts = VERDICT_SEGMENTS.map(({ key, label, fill }) => ({
    key,
    label,
    fill,
    count: plates.reduce((acc, [, b]) => acc + (b[key] ?? 0), 0),
  }));

  if (plates.length === 0) return recoveryHeader;

  const barW = 44;
  const gap = 24;
  const chartH = 120;
  const headerH = 28; // pass-rate % + n= above each bar
  const labelH = 18; // plate label below each bar
  const chartTop = headerH;
  const chartBottom = headerH + chartH;
  const svgW = plates.length * (barW + gap) + gap;
  const svgH = headerH + chartH + labelH;

  return (
    <div className="flex flex-col gap-3">
      {recoveryHeader}
      {mutantRecoveryBar}
      <figure className="w-full overflow-x-auto" aria-label={t("mame.runHealth.verdictBreakdown")}>
        <svg
          viewBox={`0 0 ${svgW} ${svgH}`}
          width="100%"
          style={{ minWidth: svgW * 1.6 }}
          preserveAspectRatio="xMinYMin meet"
          role="img"
          aria-label={t("mame.runHealth.verdictBreakdown")}
        >
          <title>{t("mame.runHealth.verdictBreakdown")}</title>
          {plates.map(([plate, b], i) => {
            const x = gap + i * (barW + gap);
            const total = b.total || 0;
            // Detected block (pass + ambiguous) marks the boundary line; the
            // headline pass-rate counts strict PASS only.
            const detected = (b.pass ?? 0) + (b.ambiguous ?? 0);
            const passPct = total > 0 ? Math.round(((b.pass ?? 0) / total) * 100) : 0;
            const boundaryY = total > 0 ? chartBottom - (detected / total) * chartH : chartBottom;
            const showBoundary = total > 0 && detected > 0 && detected < total;
            let yOffset = chartBottom;
            return (
              <g key={plate}>
                {/* Headline: strict pass-rate then sample count. */}
                <text
                  x={x + barW / 2}
                  y={12}
                  textAnchor="middle"
                  style={{ fill: "hsl(var(--foreground))", fontSize: 13, fontWeight: 700 }}
                >
                  {total > 0 ? `${passPct}%` : "n/a"}
                </text>
                <text
                  x={x + barW / 2}
                  y={23}
                  textAnchor="middle"
                  style={{ fill: C.muted, fontSize: 8 }}
                >
                  {`n=${total}${b.fallback ? ` · fb ${b.fallback}` : ""}`}
                </text>
                {total === 0 ? (
                  <rect
                    x={x}
                    y={chartTop}
                    width={barW}
                    height={chartH}
                    rx={3}
                    style={{ fill: "hsl(var(--muted))" }}
                  />
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
                          <title>{`${nbLabel(plate)} · ${label}: ${value} (${pct}%)`}</title>
                        </rect>
                        {h >= 11 && (
                          <text
                            x={x + barW / 2}
                            y={segTop + h / 2}
                            textAnchor="middle"
                            dominantBaseline="central"
                            style={{
                              fill: "#fff",
                              stroke: "rgba(0,0,0,0.45)",
                              strokeWidth: 2,
                              paintOrder: "stroke",
                              fontSize: 9,
                              fontWeight: 600,
                            }}
                          >
                            {value}
                          </text>
                        )}
                      </g>
                    );
                  })
                )}
                {showBoundary && (
                  <line
                    x1={x}
                    x2={x + barW}
                    y1={boundaryY}
                    y2={boundaryY}
                    style={{ stroke: "hsl(var(--foreground))", strokeWidth: 1.5 }}
                  >
                    <title>
                      {`${nbLabel(plate)} · ${t("mame.runHealth.detectedShort")} ${detected}/${total}`}
                    </title>
                  </line>
                )}
                <text
                  x={x + barW / 2}
                  y={chartBottom + 13}
                  textAnchor="middle"
                  style={{ fill: C.muted, fontSize: 10 }}
                >
                  {nbLabel(plate)}
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
          {classCounts.map(({ key, label, fill, count }) => (
            <tr key={key}>
              <th scope="row" className="py-0.5 pr-2 font-normal text-foreground">
                <span className="flex items-center gap-1.5">
                  <span
                    aria-hidden="true"
                    className="inline-block h-2.5 w-2.5 shrink-0 rounded-[2px]"
                    style={{ backgroundColor: fill }}
                  />
                  {label}
                </span>
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
                <title>{t("mame.runHealth.percentileHelp")}</title>
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
            <th scope="col" className="py-1 pr-3 font-medium cursor-help" title={t("mame.runHealth.neighborAvgHelp")}>
              {t("mame.runHealth.colNeighborAvg")}
            </th>
            <th scope="col" className="py-1 pr-3 font-medium cursor-help" title={t("mame.runHealth.zScoreHelp")}>
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
  /** Hide per-section visual headings (kept for screen readers via aria) when
   *  the panel is embedded under a titled container. Default true. */
  showSectionHeadings?: boolean;
}

export function RunHealthPanel({ health, sections, className, showSectionHeadings = true }: RunHealthPanelProps) {
  const { t } = useTranslation();
  const hasMinKnow =
    health.pore_yield_pct !== null ||
    health.throughput_timeline !== null ||
    health.barcode_distribution !== null;

  const show = (s: RunHealthSection) => sections === undefined || sections.includes(s);
  // When embedded under a DataPanel that already supplies the title, hide the
  // redundant per-section visual heading but keep it for assistive tech.
  const headingCls = cn(
    "text-caption font-semibold uppercase tracking-widest text-muted-foreground",
    !showSectionHeadings && "sr-only",
  );

  return (
    <div
      className={cn(
        "grid gap-4 p-4",
        // Two columns only for the full dashboard or a multi-section subset; a
        // single embedded section (e.g. verdict-breakdown) spans full width so
        // the chart is not squeezed into half the panel and clipped.
        (sections === undefined || sections.length > 1) && "md:grid-cols-2",
        className,
      )}
      role="region"
      aria-label={t("mame.runHealth.panelAriaLabel")}
    >
      {/* Section 1: Verdict breakdown */}
      {show("verdict-breakdown") && (
        <section aria-labelledby="vh-verdict-heading" className="flex flex-col gap-2">
          <h3
            id="vh-verdict-heading"
            className={headingCls}
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
            className={headingCls}
          >
            {t("mame.runHealth.fileSizeDistribution")}
          </h3>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-caption text-muted-foreground">
            <span>
              {t("mame.runHealth.method")}:{" "}
              <span className="font-medium text-foreground cursor-help" title={t("mame.runHealth.methodHelp")}>{health.suggested_method}</span>
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
                className={headingCls}
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
                className={headingCls}
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
                  className={headingCls}
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
            className={headingCls}
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
