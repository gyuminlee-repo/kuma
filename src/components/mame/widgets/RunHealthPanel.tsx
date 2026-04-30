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
import { cn } from "@/lib/utils";
import type {
  RunHealthBreakdown,
  RunHealthData,
  RunHealthThroughputPoint,
} from "@/types/mame/models";

// ── Colour palette — CSS variable references only ────────────────────────────

const C = {
  pass: "hsl(var(--success))",
  ambiguous: "hsl(var(--warning))",
  fail: "hsl(var(--destructive))",
  fallback: "hsl(var(--muted-foreground))",
  primary: "hsl(var(--primary))",
  muted: "hsl(var(--muted-foreground))",
  border: "hsl(var(--border))",
  cutoff: "hsl(var(--warning))",
  line: "hsl(var(--primary))",
  area: "hsl(var(--primary) / 0.12)",
} as const;

// ── Tiny helpers ─────────────────────────────────────────────────────────────

function safeMax(arr: number[]): number {
  return arr.length === 0 ? 1 : Math.max(...arr);
}

// ── Section 1: Verdict breakdown stacked bar ─────────────────────────────────

interface VerdictBreakdownProps {
  perPlate: Record<string, RunHealthBreakdown>;
}

function VerdictBreakdown({ perPlate }: VerdictBreakdownProps) {
  const plates = Object.entries(perPlate);
  if (plates.length === 0) return null;

  const barW = 48;
  const gap = 20;
  const chartH = 100;
  const labelH = 18;
  const svgW = plates.length * (barW + gap) + gap;
  const svgH = chartH + labelH + 4;

  const maxTotal = safeMax(plates.map(([, v]) => v.total));

  return (
    <figure className="w-full overflow-x-auto" aria-label="Verdict breakdown by plate">
      <svg
        viewBox={`0 0 ${svgW} ${svgH}`}
        width="100%"
        preserveAspectRatio="xMinYMin meet"
        role="img"
        aria-label="Stacked bar chart: verdict counts per plate"
      >
        <title>Verdict breakdown per plate</title>
        {plates.map(([plate, breakdown], i) => {
          const x = gap + i * (barW + gap);
          const scale = maxTotal > 0 ? chartH / maxTotal : 0;

          const segments = [
            { key: "pass", value: breakdown.pass, fill: C.pass },
            { key: "ambiguous", value: breakdown.ambiguous, fill: C.ambiguous },
            { key: "fail", value: breakdown.fail, fill: C.fail },
            { key: "fallback", value: breakdown.fallback, fill: C.fallback },
          ];

          let yOffset = chartH;
          return (
            <g key={plate}>
              {segments.map(({ key, value, fill }) => {
                if (value === 0) return null;
                const h = value * scale;
                yOffset -= h;
                const y = yOffset;
                return (
                  <rect
                    key={key}
                    x={x}
                    y={y}
                    width={barW}
                    height={h}
                    style={{ fill }}
                    rx={key === "pass" ? 3 : 0}
                  >
                    <title>{`${plate} ${key}: ${value}`}</title>
                  </rect>
                );
              })}
              <text
                x={x + barW / 2}
                y={chartH + labelH}
                textAnchor="middle"
                style={{ fill: C.muted, fontSize: 9 }}
              >
                {plate}
              </text>
              <text
                x={x + barW / 2}
                y={chartH - 4}
                textAnchor="middle"
                style={{ fill: "hsl(var(--foreground))", fontSize: 8 }}
              >
                {breakdown.total}
              </text>
            </g>
          );
        })}
      </svg>
      <figcaption className="sr-only">
        Stacked bar showing PASS, Ambiguous, Fail, and Fallback counts per plate.
      </figcaption>
    </figure>
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
      aria-label={`File size distribution histogram. Suggested cutoff: ${cutoffKb.toFixed(1)} KB (${method})${bimodal ? ", bimodal distribution detected" : ""}`}
    >
      <svg
        viewBox={`0 0 ${svgW} ${svgH}`}
        width="100%"
        preserveAspectRatio="xMinYMin meet"
        role="img"
        aria-label="File size distribution histogram with cutoff marker"
      >
        <title>File size distribution</title>
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
        {`7-bucket file size histogram. Suggested cutoff at ${cutoffKb.toFixed(1)} KB using ${method} method.${bimodal ? " Bimodal distribution detected." : ""}`}
      </figcaption>
    </figure>
  );
}

// ── Section 3: Barcode distribution ──────────────────────────────────────────

interface BarcodeDistributionProps {
  distribution: Record<string, number>;
}

function BarcodeDistribution({ distribution }: BarcodeDistributionProps) {
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
    <figure className="w-full max-h-72 overflow-y-auto" aria-label="Barcode read count distribution">
      <svg
        viewBox={`0 0 ${svgW} ${svgH}`}
        width="100%"
        preserveAspectRatio="xMinYMin meet"
        role="img"
        aria-label="Horizontal bar chart: read counts per barcode"
      >
        <title>Barcode read distribution</title>
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
        Horizontal bar chart showing read counts for each detected barcode.
      </figcaption>
    </figure>
  );
}

// ── Section 4: Throughput timeline ───────────────────────────────────────────

interface ThroughputTimelineProps {
  points: RunHealthThroughputPoint[];
}

function ThroughputTimeline({ points }: ThroughputTimelineProps) {
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
      aria-label={`Throughput timeline over ${maxTime.toFixed(1)} hours`}
    >
      <svg
        viewBox={`0 0 ${svgW} ${totalH}`}
        width="100%"
        preserveAspectRatio="xMinYMin meet"
        role="img"
        aria-label="Line chart: reads per second over experiment time"
      >
        <title>Throughput timeline</title>
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
        {`Line chart showing reads per second from experiment start to ${maxTime.toFixed(1)} hours.`}
      </figcaption>
    </figure>
  );
}

// ── Section 5: Pore yield indicator ──────────────────────────────────────────

interface PoreYieldProps {
  pct: number;
}

function PoreYield({ pct }: PoreYieldProps) {
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
      aria-label={`Final pore yield: ${pct.toFixed(1)}%`}
    >
      <span className={cn("font-display text-4xl font-bold tabular-nums", toneClass)}>
        {pct.toFixed(1)}%
      </span>
      <span className="text-caption text-muted-foreground">
        Final active pore yield
      </span>
    </div>
  );
}

// ── Legend ────────────────────────────────────────────────────────────────────

function Legend() {
  const items = [
    { label: "PASS", color: C.pass },
    { label: "Ambiguous", color: C.ambiguous },
    { label: "Fail", color: C.fail },
    { label: "Fallback", color: C.fallback },
  ];
  return (
    <div className="flex flex-wrap gap-3" aria-label="Chart legend" role="list">
      {items.map(({ label, color }) => (
        <div key={label} className="flex items-center gap-1.5" role="listitem">
          <span
            className="h-2.5 w-2.5 flex-shrink-0 rounded-sm"
            style={{ backgroundColor: color }}
            aria-hidden="true"
          />
          <span className="text-caption text-muted-foreground">{label}</span>
        </div>
      ))}
    </div>
  );
}

// ── Main panel component ──────────────────────────────────────────────────────

interface RunHealthPanelProps {
  health: RunHealthData;
  className?: string;
}

export function RunHealthPanel({ health, className }: RunHealthPanelProps) {
  const hasMinKnow =
    health.pore_yield_pct !== null ||
    health.throughput_timeline !== null ||
    health.barcode_distribution !== null;

  return (
    <div
      className={cn("grid gap-4 p-4 md:grid-cols-2", className)}
      role="region"
      aria-label="Run health panel"
    >
      {/* Section 1: Verdict breakdown */}
      <section aria-labelledby="vh-verdict-heading" className="flex flex-col gap-2">
        <h3
          id="vh-verdict-heading"
          className="text-caption font-semibold uppercase tracking-widest text-muted-foreground"
        >
          Verdict breakdown
        </h3>
        <Legend />
        <VerdictBreakdown perPlate={health.per_plate_summary} />
      </section>

      {/* Section 2: File size distribution */}
      <section aria-labelledby="vh-dist-heading" className="flex flex-col gap-2">
        <h3
          id="vh-dist-heading"
          className="text-caption font-semibold uppercase tracking-widest text-muted-foreground"
        >
          File size distribution
        </h3>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-caption text-muted-foreground">
          <span>
            Method:{" "}
            <span className="font-medium text-foreground">{health.suggested_method}</span>
          </span>
          {health.bimodal && (
            <span className="rounded-control border border-warning/40 px-1.5 py-0.5 text-warning">
              Bimodal
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
          <p className="text-caption text-muted-foreground">No distribution data.</p>
        )}
      </section>

      {/* MinKNOW sections: rendered only when raw run data is available */}
      {hasMinKnow && (
        <>
          {/* Section 5: Pore yield */}
          {health.pore_yield_pct !== null && (
            <section aria-labelledby="vh-pore-heading" className="flex flex-col gap-2">
              <h3
                id="vh-pore-heading"
                className="text-caption font-semibold uppercase tracking-widest text-muted-foreground"
              >
                Pore yield
              </h3>
              <PoreYield pct={health.pore_yield_pct} />
            </section>
          )}

          {/* Section 4: Throughput timeline */}
          {health.throughput_timeline !== null && health.throughput_timeline.length >= 2 && (
            <section aria-labelledby="vh-throughput-heading" className="flex flex-col gap-2">
              <h3
                id="vh-throughput-heading"
                className="text-caption font-semibold uppercase tracking-widest text-muted-foreground"
              >
                Throughput timeline
              </h3>
              <ThroughputTimeline points={health.throughput_timeline} />
            </section>
          )}

          {/* Section 3: Barcode distribution */}
          {health.barcode_distribution !== null &&
            Object.keys(health.barcode_distribution).length > 0 && (
              <section
                aria-labelledby="vh-barcode-heading"
                className="col-span-full flex flex-col gap-2 md:col-span-2"
              >
                <h3
                  id="vh-barcode-heading"
                  className="text-caption font-semibold uppercase tracking-widest text-muted-foreground"
                >
                  Barcode distribution
                </h3>
                <BarcodeDistribution distribution={health.barcode_distribution} />
              </section>
            )}
        </>
      )}

      {!hasMinKnow && (
        <div className="col-span-full">
          <p className="text-caption text-muted-foreground">
            MinKNOW raw run directory not detected — pore yield, throughput, and
            barcode charts are unavailable.
          </p>
        </div>
      )}
    </div>
  );
}
