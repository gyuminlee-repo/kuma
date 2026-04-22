import type { ChangeEvent, KeyboardEvent } from "react";
import { useState } from "react";
import { UniprotSearch } from "./UniprotSearch";

const LINKER_HANDLING_OPTIONS: Array<"include" | "separate-bin" | "exclude"> = [
  "include",
  "separate-bin",
  "exclude",
];

const DOMAIN_STRATEGY_OPTIONS: Array<"proportional" | "equal"> = [
  "proportional",
  "equal",
];

const DOMAIN_OVERLAP_OPTIONS: Array<"first" | "largest"> = [
  "first",
  "largest",
];

const DISTANCE_MODE_OPTIONS: Array<"auto" | "1d" | "3d"> = [
  "auto",
  "1d",
  "3d",
];

export function HelpTip({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <span>
      <button
        type="button"
        className="inline-flex h-3.5 w-3.5 items-center justify-center rounded-full bg-slate-100 text-[9px] font-bold leading-none text-slate-400 hover:bg-amber-100 hover:text-amber-700"
        onClick={(e) => {
          e.preventDefault();
          setOpen((p) => !p);
        }}
        aria-label={open ? "Hide help" : "Show help"}
      >
        ?
      </button>
      {open && (
        <span className="mt-0.5 block rounded-xl border border-amber-200 bg-amber-50 px-1.5 py-1 text-[10px] leading-relaxed text-slate-600 whitespace-pre-line">
          {children}
        </span>
      )}
    </span>
  );
}

export function PipelineStep({
  step,
  label,
  enabled,
  onToggle,
  children,
}: {
  step: number;
  label: string;
  enabled: boolean;
  onToggle: (v: boolean) => void;
  children?: React.ReactNode;
}) {
  return (
    <div className={`relative rounded-2xl border px-3 py-3 transition-opacity ${enabled ? "border-slate-200 bg-white/80 opacity-100" : "border-slate-200 bg-slate-50/70 opacity-60"}`}>
      <div
        className={`absolute -left-[calc(0.75rem+5px)] top-3 h-2 w-2 rounded-full border-2 ${
          enabled ? "border-amber-500 bg-amber-500" : "border-slate-300 bg-white"
        }`}
      />
      <label className="mb-1 flex items-center gap-1.5 cursor-pointer text-xs font-medium">
        <input
          type="checkbox"
          className="h-3 w-3 accent-amber-600"
          checked={enabled}
          onChange={(e) => onToggle(e.target.checked)}
        />
        <span className="text-slate-700">
          Step {step}: {label}
        </span>
      </label>
      {enabled && children && <div className="pl-4 space-y-1">{children}</div>}
    </div>
  );
}

export function PipelineArrow({ active }: { active: boolean }) {
  return (
    <div
      className={`flex items-center -ml-0.5 text-[10px] transition-opacity ${
        active ? "opacity-60" : "opacity-20"
      }`}
    >
      <span className="text-slate-400 select-none leading-none">{"↓"}</span>
    </div>
  );
}

export function DomainAllocationSection(props: {
  linkerHandling: "include" | "separate-bin" | "exclude";
  setLinkerHandling: (v: "include" | "separate-bin" | "exclude") => void;
  domains: Array<{ name: string; id: string; start: number; end: number; db: string }>;
  disabledDomains: string[];
  domainStats: Record<string, { quota: number; selected: number }>;
  toggleDomain: (key: string) => void;
  addingDomain: boolean;
  setAddingDomain: (v: boolean) => void;
  newDomainName: string;
  setNewDomainName: (v: string) => void;
  newDomainStart: string;
  setNewDomainStart: (v: string) => void;
  newDomainEnd: string;
  setNewDomainEnd: (v: string) => void;
  setDomains: (domains: Array<{ name: string; id: string; start: number; end: number; db: string }>) => void;
}) {
  const {
    linkerHandling,
    setLinkerHandling,
    domains,
    disabledDomains,
    domainStats,
    toggleDomain,
    addingDomain,
    setAddingDomain,
    newDomainName,
    setNewDomainName,
    newDomainStart,
    setNewDomainStart,
    newDomainEnd,
    setNewDomainEnd,
    setDomains,
  } = props;

  return (
    <div className="space-y-1.5">
      <div className="flex flex-wrap items-center gap-2 text-[10px] text-slate-500">
        <span>Linker</span>
        {LINKER_HANDLING_OPTIONS.map((v) => (
          <label key={v} className="flex items-center gap-0.5 cursor-pointer">
            <input
              type="radio"
              name="linkerHandling"
              className="w-2.5 h-2.5"
              checked={linkerHandling === v}
              onChange={() => setLinkerHandling(v)}
            />
            {v === "include" ? "Fill only" : v === "separate-bin" ? "Separate" : "Exclude"}
          </label>
        ))}
        <HelpTip>Choose whether non-domain residues only backfill spare slots, get their own quota bin, or are excluded from Step 2 entirely.</HelpTip>
      </div>

      <UniprotSearch />

      {domains.length > 0 && (
        <div className="space-y-0.5">
          {domains.map((d) => {
            const key = `${d.name}-${d.start}`;
            const disabled = disabledDomains.includes(key);
            const stat = domainStats[d.name];
            return (
              <label
                key={key}
                className={`flex items-center gap-1 text-[10px] cursor-pointer ${disabled ? "opacity-40" : ""}`}
                title={`${d.id} (${d.db})`}
              >
                <input
                  type="checkbox"
                  className="w-2.5 h-2.5"
                  checked={!disabled}
                  onChange={() => toggleDomain(key)}
                />
                <span className="w-2 h-2 rounded-sm bg-blue-400 inline-block flex-shrink-0" />
                <span className="truncate text-slate-600">
                  {d.name} ({d.start}-{d.end})
                </span>
                {stat && !disabled && (
                  <span className={`ml-auto flex-shrink-0 tabular-nums ${stat.selected < stat.quota ? "text-amber-600" : "text-slate-400"}`}>
                    {stat.selected}/{stat.quota}
                    {stat.selected < stat.quota && " \u26A0"}
                  </span>
                )}
              </label>
            );
          })}
        </div>
      )}

      {!addingDomain ? (
        <button
          className="text-[10px] text-amber-700 hover:text-amber-900"
          onClick={() => setAddingDomain(true)}
        >
          + Add manually
        </button>
      ) : (
        <div className="flex items-center gap-1 text-[10px]">
          <input
            type="text"
            placeholder="Name"
            className="h-6 w-16 rounded-lg border border-slate-300 px-1 text-[10px]"
            value={newDomainName}
            onChange={(e) => setNewDomainName(e.target.value)}
          />
          <input
            type="number"
            placeholder="Start"
            className="h-6 w-10 rounded-lg border border-slate-300 px-0.5 text-[10px] text-center"
            value={newDomainStart}
            onChange={(e) => setNewDomainStart(e.target.value)}
          />
          <span className="text-slate-400">-</span>
          <input
            type="number"
            placeholder="End"
            className="h-6 w-10 rounded-lg border border-slate-300 px-0.5 text-[10px] text-center"
            value={newDomainEnd}
            onChange={(e) => setNewDomainEnd(e.target.value)}
          />
          <button
            className="font-bold text-emerald-600 hover:text-emerald-800"
            onClick={() => {
              const s = parseInt(newDomainStart, 10);
              const e = parseInt(newDomainEnd, 10);
              if (newDomainName && isFinite(s) && isFinite(e) && s < e) {
                setDomains([...domains, { name: newDomainName, id: "manual", start: s, end: e, db: "manual" }]);
                setNewDomainName("");
                setNewDomainStart("");
                setNewDomainEnd("");
                setAddingDomain(false);
              }
            }}
          >
            &#10003;
          </button>
          <button className="text-slate-400 hover:text-slate-600" onClick={() => setAddingDomain(false)}>
            &times;
          </button>
        </div>
      )}
    </div>
  );
}

export function OptimizationSummarySection(props: {
  distanceBadge: string;
  structureLoading: boolean;
  structureLoaded: boolean;
  distanceMode: "auto" | "1d" | "3d";
}) {
  const { distanceBadge, structureLoading, structureLoaded, distanceMode } = props;
  return (
    <div className="flex flex-wrap items-center gap-1.5 text-[10px] text-slate-500">
      <span>{distanceBadge}</span>
      {structureLoading && <span className="text-amber-600">(loading AlphaFold...)</span>}
      {structureLoaded && (
        <span className="inline-flex items-center rounded-full bg-indigo-100 px-2 py-0.5 text-[10px] font-medium text-indigo-700">
          AlphaFold
        </span>
      )}
      <HelpTip>
        {(distanceMode === "3d" || (distanceMode === "auto" && structureLoaded))
          ? "Selects variants spread apart in 3D space using AlphaFold C\u03B1 coordinates."
          : "Greedy Pareto selection that maximises minimum sequence-distance between chosen positions."}
      </HelpTip>
    </div>
  );
}

export function RoundSettingsSection(props: {
  roundStr: string;
  setRoundStr: (v: string) => void;
  roundSizeStr: string;
  setRoundSizeStr: (v: string) => void;
  commitRound: () => void;
  commitRoundSize: () => void;
  onEnterBlur: (e: KeyboardEvent<HTMLInputElement>) => void;
  autoK: number;
  autoEntropy: number;
}) {
  const {
    roundStr,
    setRoundStr,
    roundSizeStr,
    setRoundSizeStr,
    commitRound,
    commitRoundSize,
    onEnterBlur,
    autoK,
    autoEntropy,
  } = props;

  return (
    <div className="ml-2 mt-3 space-y-1.5 border-l-2 border-transparent pl-3 text-[10px] text-slate-500">
      <div className="font-semibold uppercase tracking-wide text-slate-400">Round</div>
      <div className="flex items-center gap-2 flex-wrap">
        <span>EVOLVEpro Round</span>
        <input
          type="number"
          min={1}
          className="h-6 w-10 rounded-lg border border-slate-300 bg-white px-1 text-center text-[10px]"
          value={roundStr}
          onChange={(e: ChangeEvent<HTMLInputElement>) => setRoundStr(e.target.value)}
          onBlur={commitRound}
          onKeyDown={onEnterBlur}
        />
        <span className="text-slate-400">Size</span>
        <input
          type="number"
          min={1}
          max={960}
          className="h-6 w-12 rounded-lg border border-slate-300 bg-white px-1 text-center text-[10px]"
          value={roundSizeStr}
          onChange={(e: ChangeEvent<HTMLInputElement>) => setRoundSizeStr(e.target.value)}
          onBlur={commitRoundSize}
          onKeyDown={onEnterBlur}
        />
        <HelpTip>{"Round × size = cumulative data points used to estimate model quality (ρ).\nLower ρ → wider pool and higher entropy weight for exploration."}</HelpTip>
      </div>
      <div className="flex items-center gap-2 font-mono text-[10px] text-indigo-600">
        <span className="inline-flex items-center rounded-full border border-indigo-100 bg-indigo-50 px-2 py-0.5 text-[9px] font-medium text-indigo-600">
          Auto
        </span>
        <span>K = {autoK.toFixed(2)}</span>
        <span className="text-slate-400">/</span>
        <span>entropy = {autoEntropy.toFixed(2)}</span>
      </div>
    </div>
  );
}

export function AdvancedSettingsSection(props: {
  showAdvanced: boolean;
  setShowAdvanced: (v: boolean | ((p: boolean) => boolean)) => void;
  maxPerPosStr: string;
  setMaxPerPosStr: (v: string) => void;
  commitMaxPerPos: () => void;
  onEnterBlur: (e: KeyboardEvent<HTMLInputElement>) => void;
  domainStrategy: "proportional" | "equal";
  setDomainStrategy: (v: "proportional" | "equal") => void;
  domainOverlapPolicy: "first" | "largest";
  setDomainOverlapPolicy: (v: "first" | "largest") => void;
  domainQuotaMin: number;
  setDomainQuotaMin: (v: number) => void;
  distanceMode: "auto" | "1d" | "3d";
  setDistanceMode: (v: "auto" | "1d" | "3d") => void;
  paretoPoolMultiplier: number;
  setParetoPoolMultiplier: (v: number) => void;
  autoK: number;
  entropyWeightEnabled: boolean;
  setEntropyWeightEnabled: (v: boolean) => void;
  autoEntropy: number;
  entropyWeight: number;
  setEntropyWeight: (v: number) => void;
}) {
  const {
    showAdvanced,
    setShowAdvanced,
    maxPerPosStr,
    setMaxPerPosStr,
    commitMaxPerPos,
    onEnterBlur,
    domainStrategy,
    setDomainStrategy,
    domainOverlapPolicy,
    setDomainOverlapPolicy,
    domainQuotaMin,
    setDomainQuotaMin,
    distanceMode,
    setDistanceMode,
    paretoPoolMultiplier,
    setParetoPoolMultiplier,
    autoK,
    entropyWeightEnabled,
    setEntropyWeightEnabled,
    autoEntropy,
    entropyWeight,
    setEntropyWeight,
  } = props;

  return (
    <div className="ml-2 mt-2 border-l-2 border-transparent pl-3">
      <button
        type="button"
        className="flex items-center gap-1 text-[10px] text-slate-500 hover:text-slate-700"
        onClick={() => setShowAdvanced((p) => !p)}
      >
        <span>{showAdvanced ? "▾" : "▸"}</span>
        <span>Advanced</span>
      </button>
      {showAdvanced && (
        <div className="mt-1.5 space-y-2 rounded-2xl border border-slate-200 bg-white/80 p-3 text-[10px] text-slate-500">
          <div>
            <div className="mb-0.5 text-[9px] uppercase tracking-wide text-slate-400">Step 1</div>
            <div className="flex items-center gap-1 flex-wrap">
              <span>Position cap</span>
              <input
                type="number"
                min={1}
                max={20}
                className="h-6 w-10 rounded-lg border border-slate-300 bg-white px-1 text-center text-[10px]"
                value={maxPerPosStr}
                onChange={(e: ChangeEvent<HTMLInputElement>) => setMaxPerPosStr(e.target.value)}
                onBlur={commitMaxPerPos}
                onKeyDown={onEnterBlur}
              />
              <span>/position</span>
              <HelpTip>Max substitutions per residue. Cap=1 keeps one best variant per position. Uses Grantham-distance tie-break when scores are within 2%.</HelpTip>
            </div>
          </div>

          <div>
            <div className="mb-0.5 text-[9px] uppercase tracking-wide text-slate-400">Step 2</div>
            <div className="space-y-1">
              <div className="flex items-center gap-2 flex-wrap" role="radiogroup" aria-label="Domain strategy">
                <span>Strategy</span>
                {DOMAIN_STRATEGY_OPTIONS.map((v) => (
                  <label key={v} className="flex items-center gap-0.5 cursor-pointer">
                    <input type="radio" name="domainStrategy" className="w-2.5 h-2.5" checked={domainStrategy === v} onChange={() => setDomainStrategy(v)} />
                    {v.charAt(0).toUpperCase() + v.slice(1)}
                  </label>
                ))}
                <HelpTip>Proportional: quota proportional to domain length. Equal: same quota per domain.</HelpTip>
              </div>
              <div className="flex items-center gap-2 flex-wrap">
                <span>Overlap</span>
                {DOMAIN_OVERLAP_OPTIONS.map((v) => (
                  <label key={v} className="flex items-center gap-0.5 cursor-pointer">
                    <input type="radio" name="domainOverlapPolicy" className="w-2.5 h-2.5" checked={domainOverlapPolicy === v} onChange={() => setDomainOverlapPolicy(v)} />
                    {v.charAt(0).toUpperCase() + v.slice(1)}
                  </label>
                ))}
              </div>
              <div className="flex items-center gap-2">
                <span>Min quota</span>
                <input
                  type="number"
                  min={0}
                  max={20}
                  className="h-6 w-10 rounded-lg border border-slate-300 bg-white px-1 text-center text-[10px]"
                  value={domainQuotaMin}
                  onChange={(e) => setDomainQuotaMin(Number(e.target.value))}
                />
              </div>
            </div>
          </div>

          <div>
            <div className="mb-0.5 text-[9px] uppercase tracking-wide text-slate-400">Step 3</div>
            <div className="space-y-1">
              <div className="flex items-center gap-2 flex-wrap">
                <span>Distance</span>
                {DISTANCE_MODE_OPTIONS.map((v) => (
                  <label key={v} className="flex items-center gap-1 cursor-pointer">
                    <input type="radio" name="distanceMode" className="w-2.5 h-2.5" checked={distanceMode === v} onChange={() => setDistanceMode(v)} />
                    {v.toUpperCase()}
                  </label>
                ))}
                <HelpTip>Auto uses AlphaFold Cα when structure is loaded. Force 1D/3D for controlled comparisons.</HelpTip>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-16">Pool K</span>
                <input
                  type="range"
                  min="1"
                  max="5"
                  step="0.25"
                  value={paretoPoolMultiplier}
                  onChange={(e) => setParetoPoolMultiplier(Number(e.target.value))}
                  className="w-20 accent-indigo-600"
                  title="Manual pool size override (ignored when Round > 0)"
                />
                <span className="font-mono text-slate-700">{paretoPoolMultiplier.toFixed(2)}x</span>
                <HelpTip>{"Manual pool multiplier. Ignored when EVOLVEpro Round ≥ 1 (σ-adaptive mode).\nAuto K = " + autoK.toFixed(2) + " based on current round."}</HelpTip>
              </div>
              <div className="flex items-center gap-1">
                <label className="flex items-center gap-1.5 cursor-pointer">
                  <input
                    type="checkbox"
                    className="h-2.5 w-2.5 accent-amber-600"
                    checked={entropyWeightEnabled}
                    onChange={(e) => setEntropyWeightEnabled(e.target.checked)}
                  />
                  <span>Entropy-guided</span>
                  <span className="inline-flex items-center rounded-full bg-purple-100 px-2 py-0.5 text-[9px] font-medium text-purple-700">β</span>
                </label>
                <HelpTip>Positions where EVOLVEpro scores multiple substitutions similarly get an uncertainty bonus. Auto weight = {autoEntropy.toFixed(2)} based on current round.</HelpTip>
              </div>
              {entropyWeightEnabled && (
                <div className="flex items-center gap-2 pl-4">
                  <span>Weight</span>
                  <input
                    type="range"
                    min="0"
                    max="1"
                    step="0.05"
                    value={entropyWeight}
                    onChange={(e) => setEntropyWeight(Number(e.target.value))}
                    className="w-20 accent-purple-600"
                    title="Manual entropy weight override (ignored when Round > 0)"
                  />
                  <span className="font-mono text-slate-700">{entropyWeight.toFixed(2)}</span>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export function WorkspaceSection(props: {
  autoRedesignOnLoad: boolean;
  setAutoRedesignOnLoad: (v: boolean) => void;
  saveCache: boolean;
  setSaveCache: (v: boolean) => void;
}) {
  const { autoRedesignOnLoad, setAutoRedesignOnLoad, saveCache, setSaveCache } = props;
  return (
    <div className="ml-2 mt-2 space-y-1 border-l-2 border-transparent pl-3 text-[10px] text-slate-500">
      <div className="font-semibold uppercase tracking-wide text-slate-400">Workspace</div>
      <label className="flex items-center gap-1.5 cursor-pointer">
        <input type="checkbox" className="h-2.5 w-2.5 accent-amber-600" checked={autoRedesignOnLoad} onChange={(e) => setAutoRedesignOnLoad(e.target.checked)} />
        Auto re-design on load
      </label>
      <label className="flex items-center gap-1.5 cursor-pointer">
        <input type="checkbox" className="h-2.5 w-2.5 accent-amber-600" checked={saveCache} onChange={(e) => setSaveCache(e.target.checked)} />
        Save pipeline cache
      </label>
    </div>
  );
}

export function BenchmarkSection(props: {
  benchmarkTopPercentile: number;
  setBenchmarkTopPercentile: (v: number) => void;
  benchmarkRandomTrials: number;
  setBenchmarkRandomTrials: (v: number) => void;
  benchmarkRandomSeed: number | null;
  setBenchmarkRandomSeed: (v: number | null) => void;
  benchmarkRunning: boolean;
  runBenchmark: () => Promise<void>;
  hasBenchmarkData: boolean;
}) {
  const {
    benchmarkTopPercentile,
    setBenchmarkTopPercentile,
    benchmarkRandomTrials,
    setBenchmarkRandomTrials,
    benchmarkRandomSeed,
    setBenchmarkRandomSeed,
    benchmarkRunning,
    runBenchmark,
    hasBenchmarkData,
  } = props;

  return (
    <div className="ml-2 mt-2 space-y-1 border-l-2 border-transparent pl-3 text-[10px] text-slate-500">
      <div className="font-semibold uppercase tracking-wide text-slate-400">Benchmark</div>
      <div className="flex items-center gap-2">
        <span className="w-20">Top percentile</span>
        <input
          type="number"
          min={1}
          max={100}
          step={1}
          className="h-6 w-12 rounded-lg border border-slate-300 bg-white px-1 text-center text-[10px]"
          value={benchmarkTopPercentile}
          onChange={(e) => setBenchmarkTopPercentile(Number(e.target.value))}
        />
        <span>%</span>
      </div>
      <div className="flex items-center gap-2">
        <span className="w-20">Random trials</span>
        <input
          type="number"
          min={1}
          max={1000}
          step={1}
          className="h-6 w-14 rounded-lg border border-slate-300 bg-white px-1 text-center text-[10px]"
          value={benchmarkRandomTrials}
          onChange={(e) => setBenchmarkRandomTrials(Number(e.target.value))}
        />
      </div>
      <div className="flex items-center gap-2">
        <span className="w-20">Random seed</span>
        <input
          type="number"
          className="h-6 w-16 rounded-lg border border-slate-300 bg-white px-1 text-center text-[10px]"
          value={benchmarkRandomSeed ?? ""}
          placeholder="auto"
          onChange={(e) => {
            const raw = e.target.value.trim();
            setBenchmarkRandomSeed(raw === "" ? null : Number(raw));
          }}
        />
        <HelpTip>Leave blank for fresh randomness. Set a seed to reproduce random baseline comparisons exactly.</HelpTip>
      </div>
      <button
        type="button"
        className="mt-1 inline-flex items-center rounded-full border border-slate-300 bg-white px-3 py-1 text-[10px] font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
        onClick={() => {
          void runBenchmark();
        }}
        disabled={benchmarkRunning || !hasBenchmarkData}
      >
        {benchmarkRunning ? "Running..." : "Run Benchmark"}
      </button>
    </div>
  );
}
