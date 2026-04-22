import { memo, useMemo, useState, useCallback, useRef, useEffect } from "react";
import { useShallow } from "zustand/react/shallow";
import { useAppStore } from "../../store/appStore";
import type { DomainInfo } from "../../types/models";

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

interface DensityTooltipState {
  x: number;
  y: number;
  count: number;
  startAa: number;
  endAa: number;
}

interface SequenceViewerMetrics {
  maxAa: number;
  hasData: boolean;
  hasTicks: boolean;
  successCount: number;
  failedCount: number;
}

interface SequenceViewerComputedMetrics extends SequenceViewerMetrics {
  ticks: MutationTick[];
}

// --- Density computation ---

function computeDensityBins(
  ticks: MutationTick[],
  maxAa: number,
  binCount: number,
): number[] {
  const bins = Array<number>(binCount).fill(0);
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

const DomainLayer = memo(function DomainLayer({
  domains,
  disabledDomainSet,
  domainStats,
  aaToX,
  cdsY,
  cdsHeight,
}: {
  domains: DomainInfo[];
  disabledDomainSet: Set<string>;
  domainStats: Record<string, { quota: number; selected: number }>;
  aaToX: (aa: number) => number;
  cdsY: number;
  cdsHeight: number;
}) {
  return (
    <>
      {domains.map((d, i) => {
        const colorSet = DOMAIN_COLORS[i % DOMAIN_COLORS.length];
        const isDomainDisabled = disabledDomainSet.has(`${d.name}-${d.start}`);
        const x1 = aaToX(d.start);
        const x2 = aaToX(d.end);
        const w = Math.max(2, x2 - x1);
        const stat = domainStats[d.name];
        return (
          <g key={`domain-${d.name}-${d.start}`} opacity={isDomainDisabled ? 0.25 : 1}>
            <rect
              x={x1}
              y={cdsY}
              width={w}
              height={cdsHeight}
              rx={2}
              fill={isDomainDisabled ? "#d1d5db" : colorSet.fill}
              stroke={isDomainDisabled ? "#9ca3af" : colorSet.stroke}
              strokeWidth={0.8}
              opacity={0.85}
            />
            {w > 40 && (
              <text
                x={x1 + w / 2}
                y={cdsY + cdsHeight / 2 + 1}
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
            {stat && (
              <text
                x={x1 + w / 2}
                y={cdsY - 4}
                textAnchor="middle"
                fontSize={7}
                fontWeight={500}
                fill={stat.selected < stat.quota ? "#dc2626" : "#6b7280"}
                className="pointer-events-none select-none"
              >
                {stat.selected}/{stat.quota}
                {stat.selected < stat.quota ? " \u26A0" : ""}
              </text>
            )}
          </g>
        );
      })}
    </>
  );
});

const ScaleLayer = memo(function ScaleLayer({
  scaleTicks,
  aaToX,
  scaleY,
  marginLeft,
}: {
  scaleTicks: number[];
  aaToX: (aa: number) => number;
  scaleY: number;
  marginLeft: number;
}) {
  return (
    <>
      {scaleTicks.map((aa) => {
        const x = aaToX(aa);
        return (
          <g key={`scale-${aa}`}>
            <line
              x1={x}
              y1={scaleY}
              x2={x}
              y2={scaleY + 3}
              stroke="#9ca3af"
              strokeWidth={0.5}
            />
            <text
              x={x}
              y={scaleY + 10}
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
      <text
        x={marginLeft}
        y={scaleY + 10}
        textAnchor="middle"
        fontSize={7}
        fill="#9ca3af"
        className="select-none"
      >
        1
      </text>
    </>
  );
});

const DensityLayer = memo(function DensityLayer({
  densityBins,
  maxDensity,
  barWidth,
  binCount,
  marginLeft,
  densityY,
  densityHeight,
  onDensityHover,
  onDensityLeave,
}: {
  densityBins: number[];
  maxDensity: number;
  barWidth: number;
  binCount: number;
  marginLeft: number;
  densityY: number;
  densityHeight: number;
  onDensityHover: (e: React.MouseEvent, binIndex: number, count: number, binCount: number) => void;
  onDensityLeave: () => void;
}) {
  return (
    <>
      {densityBins.map((count, i) => {
        if (count === 0) return null;
        const binW = barWidth / binCount;
        const x = marginLeft + i * binW;
        const h = (count / maxDensity) * densityHeight;
        const intensity = Math.min(1, count / maxDensity);
        const r = Math.round(220 - intensity * 170);
        const g = Math.round(220 - intensity * 100);
        const b = Math.round(220 - intensity * 40);
        return (
          <rect
            key={`density-${i}`}
            x={x}
            y={densityY + densityHeight - h}
            width={binW}
            height={h}
            fill={`rgb(${r},${g},${b})`}
            opacity={0.7}
            rx={0.5}
            style={{ cursor: "default" }}
            onMouseEnter={(e) => onDensityHover(e, i, count, binCount)}
            onMouseLeave={onDensityLeave}
          />
        );
      })}
    </>
  );
});

const TickLayer = memo(function TickLayer({
  ticks,
  aaToX,
  selectedMutation,
  tickTop,
  tickBottom,
  onTickHover,
  onTickLeave,
  onTickClick,
}: {
  ticks: MutationTick[];
  aaToX: (aa: number) => number;
  selectedMutation: string | null;
  tickTop: number;
  tickBottom: number;
  onTickHover: (e: React.MouseEvent, tick: MutationTick) => void;
  onTickLeave: () => void;
  onTickClick: (mutation: string) => void;
}) {
  return (
    <>
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
            y1={tickTop}
            x2={x}
            y2={tickBottom}
            stroke={color}
            strokeWidth={strokeW}
            strokeLinecap="round"
            className="cursor-pointer"
            opacity={isSelected ? 1 : 0.85}
            onMouseEnter={(e) => onTickHover(e, tick)}
            onMouseLeave={onTickLeave}
            onClick={() => onTickClick(tick.mutation)}
          />
        );
      })}
    </>
  );
});

// --- Component ---

export function SequenceViewer() {
  const {
    seqInfo,
    designResults,
    failedMutations,
    domains,
    domainStats,
    disabledDomains,
    parsedMutations,
    selectedGene,
  } = useAppStore(
    useShallow((s) => ({
      seqInfo: s.seqInfo,
      designResults: s.designResults,
      failedMutations: s.failedMutations,
      domains: s.domains,
      domainStats: s.domainStats,
      disabledDomains: s.disabledDomains,
      parsedMutations: s.parsedMutations,
      selectedGene: s.selectedGene,
    })),
  );

  const [collapsed, setCollapsed] = useState(false);
  const [selectedMutation, setSelectedMutation] = useState<string | null>(null);
  const [tooltip, setTooltip] = useState<TooltipState | null>(null);
  const [densityTooltip, setDensityTooltip] = useState<DensityTooltipState | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  // Determine max aa from seqInfo or parsedMutations
  const metrics = useMemo<SequenceViewerComputedMetrics>(() => {
    let maxAa = 0;
    if (seqInfo && seqInfo.genes.length > 0) {
      const gene = seqInfo.genes.find((g) => String(g.cds_start) === selectedGene);
      maxAa = gene
        ? gene.aa_length
        : Math.max(...seqInfo.genes.map((g) => g.aa_length));
    } else if (parsedMutations.length > 0) {
      maxAa = Math.max(...parsedMutations.map((m) => m.position));
    }

    let successCount = 0;
    let failedCount = 0;
    const ticks: MutationTick[] = [];
    const seen = new Set<string>();

    for (const r of designResults) {
      if (seen.has(r.mutation)) continue;
      seen.add(r.mutation);
      successCount++;
      ticks.push({
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
      failedCount++;
      const posMatch = f.mutation.match(/[A-Za-z*](\d+)[A-Za-z*]/);
      const pos = posMatch ? parseInt(posMatch[1], 10) : 0;
      ticks.push({
        mutation: f.mutation,
        aaPosition: pos,
        status: "failed",
        reason: f.reason,
      });
    }

    return {
      maxAa,
      hasData: maxAa > 0,
      hasTicks: ticks.length > 0,
      successCount,
      failedCount,
      ticks,
    };
  }, [designResults, failedMutations, parsedMutations, selectedGene, seqInfo]);
  const { maxAa, hasData, hasTicks, successCount, failedCount, ticks } = metrics;

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
  const disabledDomainSet = useMemo(() => new Set(disabledDomains), [disabledDomains]);

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

  const handleDensityHover = useCallback(
    (e: React.MouseEvent, binIndex: number, count: number, binCount: number) => {
      if (!svgRef.current) return;
      const rect = svgRef.current.getBoundingClientRect();
      const startAa = Math.floor((binIndex / binCount) * maxAa) + 1;
      const endAa = Math.floor(((binIndex + 1) / binCount) * maxAa);
      setDensityTooltip({
        x: e.clientX - rect.left,
        y: e.clientY - rect.top - 8,
        count,
        startAa,
        endAa,
      });
    },
    [maxAa],
  );

  const handleDensityLeave = useCallback(() => setDensityTooltip(null), []);

  const handleTickClick = useCallback((mutation: string) => {
    setSelectedMutation((prev) => (prev === mutation ? null : mutation));
  }, []);

  // Clear selection when results change
  useEffect(() => {
    setSelectedMutation(null);
  }, [designResults, failedMutations]);

  return (
    <div className="h-full overflow-hidden rounded-[22px] border border-slate-200 bg-[linear-gradient(180deg,rgba(255,253,248,0.96),rgba(248,251,255,0.98))] shadow-[inset_0_1px_0_rgba(255,255,255,0.65)]" role="region" aria-label="Sequence Map">
      {/* Header */}
      <button
        className="flex w-full items-center border-b border-slate-200 bg-white/70 px-4 py-2 text-xs font-semibold text-slate-700 transition-colors select-none hover:bg-slate-50"
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
        {hasTicks && (
          <span className="ml-2 font-normal text-slate-400">
            {successCount} designed
            {failedCount > 0 && ` / ${failedCount} failed`}
            {maxAa > 0 && ` — ${maxAa} aa`}
          </span>
        )}
      </button>

      {/* Content */}
      {!collapsed && (
        <div id="sequence-viewer-content" className="px-4 py-3" style={{ minHeight: 80 }}>
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

                <DomainLayer
                  domains={domains}
                  disabledDomainSet={disabledDomainSet}
                  domainStats={domainStats}
                  aaToX={aaToX}
                  cdsY={CDS_Y}
                  cdsHeight={CDS_HEIGHT}
                />

                <ScaleLayer
                  scaleTicks={scaleTicks}
                  aaToX={aaToX}
                  scaleY={SCALE_Y}
                  marginLeft={MARGIN_LEFT}
                />

                {hasTicks && (
                  <DensityLayer
                    densityBins={densityBins}
                    maxDensity={maxDensity}
                    barWidth={BAR_WIDTH}
                    binCount={BIN_COUNT}
                    marginLeft={MARGIN_LEFT}
                    densityY={DENSITY_Y}
                    densityHeight={DENSITY_HEIGHT}
                    onDensityHover={handleDensityHover}
                    onDensityLeave={handleDensityLeave}
                  />
                )}

                <TickLayer
                  ticks={ticks}
                  aaToX={aaToX}
                  selectedMutation={selectedMutation}
                  tickTop={TICK_TOP}
                  tickBottom={TICK_BOTTOM}
                  onTickHover={handleTickHover}
                  onTickLeave={handleTickLeave}
                  onTickClick={handleTickClick}
                />
              </svg>

              {/* Density tooltip */}
              {densityTooltip && (
                <div
                  className="absolute z-50 px-2 py-1.5 bg-gray-900 text-white text-[10px] rounded shadow-lg pointer-events-none whitespace-nowrap"
                  style={{
                    left: Math.min(densityTooltip.x, SVG_WIDTH - 120),
                    top: Math.max(0, densityTooltip.y - 36),
                    transform: "translateX(-50%)",
                  }}
                >
                  <div className="font-semibold">aa {densityTooltip.startAa}–{densityTooltip.endAa}</div>
                  <div className="text-gray-300">{densityTooltip.count} mutation{densityTooltip.count !== 1 ? "s" : ""}</div>
                </div>
              )}

              {/* Mutation tooltip */}
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
