import { useMemo, useState, useCallback, useRef, useEffect } from "react";
import { useAppStore } from "../../store/appStore";

// --- Constants ---

const DOMAIN_COLORS = [
  { fill: "#93c5fd", stroke: "#3b82f6", text: "#1e3a5f" }, // blue
  { fill: "#86efac", stroke: "#22c55e", text: "#14532d" }, // green
  { fill: "#c4b5fd", stroke: "#8b5cf6", text: "#3b0764" }, // purple
  { fill: "#fcd34d", stroke: "#f59e0b", text: "#78350f" }, // amber
  { fill: "#fda4af", stroke: "#f43f5e", text: "#881337" }, // rose
];

const TICK_SUCCESS = "#10b981"; // emerald-500
const TICK_FAILED = "#ef4444"; // red-500
const TICK_SELECTED = "#eab308"; // yellow-500
const CDS_FILL = "#e5e7eb"; // gray-200
const CDS_STROKE = "#9ca3af"; // gray-400

interface MutationTick {
  mutation: string;
  aaPosition: number;
  status: "success" | "failed";
  tm?: number;
  tmOverlap?: number;
  reason?: string;
}

interface TooltipState {
  x: number;
  y: number;
  tick: MutationTick;
}

// --- Density computation ---

function computeDensityBins(
  ticks: MutationTick[],
  maxAa: number,
  binCount: number,
): number[] {
  const bins = new Array(binCount).fill(0) as number[];
  if (maxAa <= 0) return bins;
  for (const t of ticks) {
    const idx = Math.min(Math.floor((t.aaPosition / maxAa) * binCount), binCount - 1);
    bins[idx]++;
  }
  return bins;
}

// --- Scale tick generation ---

function generateScaleTicks(maxAa: number): number[] {
  if (maxAa <= 0) return [];
  let interval: number;
  if (maxAa <= 100) interval = 10;
  else if (maxAa <= 300) interval = 50;
  else if (maxAa <= 1000) interval = 100;
  else if (maxAa <= 3000) interval = 500;
  else interval = 1000;

  const ticks: number[] = [];
  for (let i = interval; i < maxAa; i += interval) {
    ticks.push(i);
  }
  ticks.push(maxAa);
  return ticks;
}

// --- Component ---

export function SequenceViewer() {
  const seqInfo = useAppStore((s) => s.seqInfo);
  const designResults = useAppStore((s) => s.designResults);
  const failedMutations = useAppStore((s) => s.failedMutations);
  const domains = useAppStore((s) => s.domains);
  const domainStats = useAppStore((s) => s.domainStats);
  const disabledDomains = useAppStore((s) => s.disabledDomains);
  const parsedMutations = useAppStore((s) => s.parsedMutations);

  const [collapsed, setCollapsed] = useState(false);
  const [selectedMutation, setSelectedMutation] = useState<string | null>(null);
  const [tooltip, setTooltip] = useState<TooltipState | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  const selectedGene = useAppStore((s) => s.selectedGene);

  // Determine max aa from seqInfo or parsedMutations
  const maxAa = useMemo(() => {
    if (seqInfo && seqInfo.genes.length > 0) {
      const gene = seqInfo.genes.find((g) => String(g.cds_start) === selectedGene);
      if (gene) return gene.aa_length;
      return Math.max(...seqInfo.genes.map((g) => g.aa_length));
    }
    if (parsedMutations.length > 0) {
      return Math.max(...parsedMutations.map((m) => m.position));
    }
    return 0;
  }, [seqInfo, parsedMutations, selectedGene]);

  // Build tick list from design + failed mutations
  const ticks = useMemo(() => {
    const result: MutationTick[] = [];
    const seen = new Set<string>();

    for (const r of designResults) {
      if (seen.has(r.mutation)) continue;
      seen.add(r.mutation);
      result.push({
        mutation: r.mutation,
        aaPosition: r.aa_position,
        status: "success",
        tm: r.tm_no_fwd,
        tmOverlap: r.tm_overlap,
      });
    }

    for (const f of failedMutations) {
      if (seen.has(f.mutation)) continue;
      seen.add(f.mutation);
      const posMatch = f.mutation.match(/[A-Za-z*](\d+)[A-Za-z*]/);
      const pos = posMatch ? parseInt(posMatch[1], 10) : 0;
      result.push({
        mutation: f.mutation,
        aaPosition: pos,
        status: "failed",
        reason: f.reason,
      });
    }

    return result;
  }, [designResults, failedMutations]);

  // SVG layout
  const SVG_WIDTH = 900;
  const SVG_HEIGHT = 88;
  const MARGIN_LEFT = 10;
  const MARGIN_RIGHT = 10;
  const BAR_WIDTH = SVG_WIDTH - MARGIN_LEFT - MARGIN_RIGHT;
  const CDS_Y = 32;
  const CDS_HEIGHT = 18;
  const TICK_TOP = CDS_Y - 8;
  const TICK_BOTTOM = CDS_Y + CDS_HEIGHT + 8;
  const DENSITY_Y = CDS_Y + CDS_HEIGHT + 14;
  const DENSITY_HEIGHT = 16;
  const SCALE_Y = CDS_Y + CDS_HEIGHT + 2;

  const aaToX = useCallback(
    (aa: number) => {
      if (maxAa <= 0) return MARGIN_LEFT;
      return MARGIN_LEFT + (aa / maxAa) * BAR_WIDTH;
    },
    [maxAa, BAR_WIDTH],
  );

  // Scale ticks
  const scaleTicks = useMemo(() => generateScaleTicks(maxAa), [maxAa]);

  // Density bins
  const BIN_COUNT = 60;
  const densityBins = useMemo(
    () => computeDensityBins(ticks, maxAa, BIN_COUNT),
    [ticks, maxAa],
  );
  const maxDensity = Math.max(1, ...densityBins);

  // Tooltip positioning
  const handleTickHover = useCallback(
    (e: React.MouseEvent, tick: MutationTick) => {
      if (!svgRef.current) return;
      const rect = svgRef.current.getBoundingClientRect();
      setTooltip({
        x: e.clientX - rect.left,
        y: e.clientY - rect.top - 8,
        tick,
      });
    },
    [],
  );

  const handleTickLeave = useCallback(() => {
    setTooltip(null);
  }, []);

  const handleTickClick = useCallback((mutation: string) => {
    setSelectedMutation((prev) => (prev === mutation ? null : mutation));
  }, []);

  // Clear selection when results change
  useEffect(() => {
    setSelectedMutation(null);
  }, [designResults, failedMutations]);

  const hasData = maxAa > 0;
  const hasTicks = ticks.length > 0;

  return (
    <div className="border-b border-gray-200 bg-white" role="region" aria-label="Sequence Map">
      {/* Header */}
      <button
        className="flex items-center w-full px-3 py-1.5 text-xs font-semibold text-gray-700 bg-gray-50 hover:bg-gray-100 transition-colors select-none"
        onClick={() => setCollapsed((c) => !c)}
        aria-expanded={!collapsed}
        aria-controls={collapsed ? undefined : "sequence-viewer-content"}
      >
        <svg
          className={`w-3.5 h-3.5 mr-1.5 transition-transform ${collapsed ? "" : "rotate-90"}`}
          viewBox="0 0 20 20"
          fill="currentColor"
          aria-hidden="true"
        >
          <path
            fillRule="evenodd"
            d="M7.21 14.77a.75.75 0 01.02-1.06L11.168 10 7.23 6.29a.75.75 0 111.04-1.08l4.5 4.25a.75.75 0 010 1.08l-4.5 4.25a.75.75 0 01-1.06-.02z"
            clipRule="evenodd"
          />
        </svg>
        <span title="Linear CDS map showing mutation positions. Green=designed, Red=failed. Density histogram below shows clustering — spread-out mutations are better for library diversity">Sequence Map</span>
        {hasTicks && (() => {
          const successCount = ticks.filter((t) => t.status === "success").length;
          const failedCount = ticks.filter((t) => t.status === "failed").length;
          return (
            <span className="ml-2 text-gray-400 font-normal">
              {successCount} designed
              {failedCount > 0 && ` / ${failedCount} failed`}
              {maxAa > 0 && ` — ${maxAa} aa`}
            </span>
          );
        })()}
      </button>

      {/* Content */}
      {!collapsed && (
        <div id="sequence-viewer-content" className="px-3 py-2" style={{ minHeight: 80 }}>
          {!hasData ? (
            <div className="flex items-center justify-center h-16 text-gray-400 text-xs">
              Load a sequence and design primers to view the map
            </div>
          ) : (
            <div className="relative">
              <svg
                ref={svgRef}
                viewBox={`0 0 ${SVG_WIDTH} ${SVG_HEIGHT}`}
                className="w-full"
                style={{ maxHeight: 100 }}
                role="img"
                aria-label={`Linear sequence map: ${maxAa} amino acids, ${ticks.length} mutations`}
              >
                {/* CDS bar background */}
                <rect
                  x={MARGIN_LEFT}
                  y={CDS_Y}
                  width={BAR_WIDTH}
                  height={CDS_HEIGHT}
                  rx={3}
                  fill={CDS_FILL}
                  stroke={CDS_STROKE}
                  strokeWidth={1}
                />

                {/* Domain regions */}
                {domains.map((d, i) => {
                  const colorSet = DOMAIN_COLORS[i % DOMAIN_COLORS.length];
                  const isDomainDisabled = disabledDomains.has(`${d.name}-${d.start}`);
                  const x1 = aaToX(d.start);
                  const x2 = aaToX(d.end);
                  const w = Math.max(2, x2 - x1);
                  return (
                    <g key={`domain-${d.name}-${d.start}`} opacity={isDomainDisabled ? 0.25 : 1}>
                      <rect
                        x={x1}
                        y={CDS_Y}
                        width={w}
                        height={CDS_HEIGHT}
                        rx={2}
                        fill={isDomainDisabled ? "#d1d5db" : colorSet.fill}
                        stroke={isDomainDisabled ? "#9ca3af" : colorSet.stroke}
                        strokeWidth={0.8}
                        opacity={0.85}
                      />
                      {w > 40 && (
                        <text
                          x={x1 + w / 2}
                          y={CDS_Y + CDS_HEIGHT / 2 + 1}
                          textAnchor="middle"
                          dominantBaseline="middle"
                          fontSize={8}
                          fontWeight={600}
                          fill={colorSet.text}
                          className="pointer-events-none select-none"
                        >
                          {d.name.length > Math.floor(w / 5) ? d.name.slice(0, Math.floor(w / 5)) + ".." : d.name}
                        </text>
                      )}
                      {domainStats[d.name] && (
                        <text
                          x={x1 + w / 2}
                          y={CDS_Y - 4}
                          textAnchor="middle"
                          fontSize={7}
                          fontWeight={500}
                          fill={domainStats[d.name].selected < domainStats[d.name].quota ? "#dc2626" : "#6b7280"}
                          className="pointer-events-none select-none"
                        >
                          {domainStats[d.name].selected}/{domainStats[d.name].quota}
                          {domainStats[d.name].selected < domainStats[d.name].quota ? " \u26A0" : ""}
                        </text>
                      )}
                    </g>
                  );
                })}

                {/* Scale ticks */}
                {scaleTicks.map((aa) => {
                  const x = aaToX(aa);
                  return (
                    <g key={`scale-${aa}`}>
                      <line
                        x1={x}
                        y1={SCALE_Y}
                        x2={x}
                        y2={SCALE_Y + 3}
                        stroke="#9ca3af"
                        strokeWidth={0.5}
                      />
                      <text
                        x={x}
                        y={SCALE_Y + 10}
                        textAnchor="middle"
                        fontSize={7}
                        fill="#9ca3af"
                        className="select-none"
                      >
                        {aa}
                      </text>
                    </g>
                  );
                })}

                {/* Position 1 label */}
                <text
                  x={MARGIN_LEFT}
                  y={SCALE_Y + 10}
                  textAnchor="middle"
                  fontSize={7}
                  fill="#9ca3af"
                  className="select-none"
                >
                  1
                </text>

                {/* Density histogram (below scale) */}
                {hasTicks &&
                  densityBins.map((count, i) => {
                    if (count === 0) return null;
                    const binW = BAR_WIDTH / BIN_COUNT;
                    const x = MARGIN_LEFT + i * binW;
                    const h = (count / maxDensity) * DENSITY_HEIGHT;
                    const intensity = Math.min(1, count / maxDensity);
                    const r = Math.round(220 - intensity * 170);
                    const g = Math.round(220 - intensity * 100);
                    const b = Math.round(220 - intensity * 40);
                    return (
                      <rect
                        key={`density-${i}`}
                        x={x}
                        y={DENSITY_Y + DENSITY_HEIGHT - h}
                        width={binW}
                        height={h}
                        fill={`rgb(${r},${g},${b})`}
                        opacity={0.7}
                        rx={0.5}
                      />
                    );
                  })}

                {/* Mutation ticks */}
                {ticks.map((tick) => {
                  const x = aaToX(tick.aaPosition);
                  const isSelected = selectedMutation === tick.mutation;
                  const color =
                    isSelected
                      ? TICK_SELECTED
                      : tick.status === "success"
                        ? TICK_SUCCESS
                        : TICK_FAILED;
                  const strokeW = isSelected ? 2.5 : 1.5;
                  return (
                    <line
                      key={`tick-${tick.mutation}`}
                      x1={x}
                      y1={TICK_TOP}
                      x2={x}
                      y2={TICK_BOTTOM}
                      stroke={color}
                      strokeWidth={strokeW}
                      strokeLinecap="round"
                      className="cursor-pointer"
                      opacity={isSelected ? 1 : 0.85}
                      onMouseEnter={(e) => handleTickHover(e, tick)}
                      onMouseLeave={handleTickLeave}
                      onClick={() => handleTickClick(tick.mutation)}
                    />
                  );
                })}
              </svg>

              {/* Tooltip */}
              {tooltip && (
                <div
                  className="absolute z-50 px-2 py-1.5 bg-gray-900 text-white text-[10px] rounded shadow-lg pointer-events-none whitespace-nowrap"
                  style={{
                    left: Math.min(tooltip.x, SVG_WIDTH - 120),
                    top: Math.max(0, tooltip.y - 36),
                    transform: "translateX(-50%)",
                  }}
                >
                  <div className="font-semibold">{tooltip.tick.mutation}</div>
                  <div className="text-gray-300">
                    pos: {tooltip.tick.aaPosition}
                    {tooltip.tick.status === "success" && tooltip.tick.tm != null && (
                      <> | Tm: {tooltip.tick.tm.toFixed(1)}&deg;C</>
                    )}
                    {tooltip.tick.status === "success" && tooltip.tick.tmOverlap != null && (
                      <> | Ov: {tooltip.tick.tmOverlap.toFixed(1)}&deg;C</>
                    )}
                  </div>
                  <div
                    className={
                      tooltip.tick.status === "success" ? "text-emerald-400" : "text-red-400"
                    }
                  >
                    {tooltip.tick.status === "success" ? "Designed" : `Failed: ${tooltip.tick.reason ?? "unknown"}`}
                  </div>
                </div>
              )}

              {/* Legend */}
              <div className="flex items-center gap-3 mt-1 text-[10px] text-gray-400">
                <span className="flex items-center gap-1">
                  <span className="w-2.5 h-2.5 rounded-sm" style={{ backgroundColor: TICK_SUCCESS }} />
                  success
                </span>
                <span className="flex items-center gap-1">
                  <span className="w-2.5 h-2.5 rounded-sm" style={{ backgroundColor: TICK_FAILED }} />
                  failed
                </span>
                {selectedMutation && (
                  <span className="flex items-center gap-1">
                    <span className="w-2.5 h-2.5 rounded-sm" style={{ backgroundColor: TICK_SELECTED }} />
                    selected
                  </span>
                )}
                {domains.length > 0 && (
                  <span className="flex items-center gap-1 ml-1 border-l border-gray-200 pl-3">
                    {domains.map((d, i) => (
                      <span key={d.name} className="flex items-center gap-0.5">
                        <span
                          className="w-2.5 h-2.5 rounded-sm"
                          style={{ backgroundColor: DOMAIN_COLORS[i % DOMAIN_COLORS.length].fill }}
                        />
                        {d.name}
                      </span>
                    ))}
                  </span>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
