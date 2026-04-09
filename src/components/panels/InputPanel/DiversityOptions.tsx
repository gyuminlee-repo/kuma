import { useMemo, useState, type ChangeEvent, type KeyboardEvent } from "react";
import { useAppStore } from "../../../store/appStore";
import { UniprotSearch } from "./UniprotSearch";

/* ── σ-adaptive param lookup (mirrors Python sigma_adaptive_params) ────── */

function computeSigmaParams(round: number, size: number): { k: number; ew: number } {
  const cum = round * size;
  if (cum <= 96)  return { k: 0.50, ew: 0.30 };
  if (cum <= 192) return { k: 0.40, ew: 0.25 };
  if (cum <= 384) return { k: 0.30, ew: 0.20 };
  return { k: 0.25, ew: 0.15 };
}

/* ── Help tooltip ─────────────────────────────────────────── */

function HelpTip({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <span>
      <button
        type="button"
        className="inline-flex items-center justify-center w-3.5 h-3.5 rounded-full bg-gray-100 hover:bg-blue-100 text-gray-400 hover:text-blue-600 text-[9px] font-bold leading-none"
        onClick={(e) => { e.preventDefault(); setOpen((p) => !p); }}
        aria-label={open ? "Hide help" : "Show help"}
      >
        ?
      </button>
      {open && (
        <span className="block text-[10px] text-gray-600 bg-blue-50 border border-blue-100 rounded px-1.5 py-1 mt-0.5 leading-relaxed whitespace-pre-line">
          {children}
        </span>
      )}
    </span>
  );
}

/* ── Pipeline sub-components ──────────────────────────────── */

function PipelineStep({
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
    <div className={`relative transition-opacity ${enabled ? "opacity-100" : "opacity-50"}`}>
      <div
        className={`absolute -left-[calc(0.75rem+5px)] top-0.5 w-2 h-2 rounded-full border-2 ${
          enabled ? "bg-blue-500 border-blue-500" : "bg-white border-gray-300"
        }`}
      />
      <label className="flex items-center gap-1.5 cursor-pointer text-xs font-medium mb-1">
        <input
          type="checkbox"
          className="h-3 w-3 accent-blue-600"
          checked={enabled}
          onChange={(e) => onToggle(e.target.checked)}
        />
        <span className="text-gray-600">
          Step {step}: {label}
        </span>
      </label>
      {enabled && children && <div className="pl-4 space-y-1">{children}</div>}
    </div>
  );
}

function PipelineArrow({ active }: { active: boolean }) {
  return (
    <div
      className={`flex items-center -ml-0.5 text-[10px] transition-opacity ${
        active ? "opacity-60" : "opacity-20"
      }`}
    >
      <span className="text-gray-400 select-none leading-none">{"↓"}</span>
    </div>
  );
}

/* ── DiversityOptions ─────────────────────────────────────── */

export function DiversityOptions() {
  const positionDiversityEnabled = useAppStore((s) => s.positionDiversityEnabled);
  const setPositionDiversityEnabled = useAppStore((s) => s.setPositionDiversityEnabled);
  const maxPerPosition = useAppStore((s) => s.maxPerPosition);
  const setMaxPerPosition = useAppStore((s) => s.setMaxPerPosition);
  const domainDiversityEnabled = useAppStore((s) => s.domainDiversityEnabled);
  const setDomainDiversityEnabled = useAppStore((s) => s.setDomainDiversityEnabled);
  const domainStrategy = useAppStore((s) => s.domainStrategy);
  const setDomainStrategy = useAppStore((s) => s.setDomainStrategy);
  const domainOverlapPolicy = useAppStore((s) => s.domainOverlapPolicy);
  const setDomainOverlapPolicy = useAppStore((s) => s.setDomainOverlapPolicy);
  const linkerHandling = useAppStore((s) => s.linkerHandling);
  const setLinkerHandling = useAppStore((s) => s.setLinkerHandling);
  const domainQuotaMin = useAppStore((s) => s.domainQuotaMin);
  const setDomainQuotaMin = useAppStore((s) => s.setDomainQuotaMin);
  const domains = useAppStore((s) => s.domains);
  const setDomains = useAppStore((s) => s.setDomains);
  const toggleDomain = useAppStore((s) => s.toggleDomain);
  const disabledDomains = useAppStore((s) => s.disabledDomains);
  const domainStats = useAppStore((s) => s.domainStats);
  const paretoDiversityEnabled = useAppStore((s) => s.paretoDiversityEnabled);
  const setParetoDiversityEnabled = useAppStore((s) => s.setParetoDiversityEnabled);
  const entropyWeightEnabled = useAppStore((s) => s.entropyWeightEnabled);
  const entropyWeight = useAppStore((s) => s.entropyWeight);
  const setEntropyWeightEnabled = useAppStore((s) => s.setEntropyWeightEnabled);
  const setEntropyWeight = useAppStore((s) => s.setEntropyWeight);
  const paretoPoolMultiplier = useAppStore((s) => s.paretoPoolMultiplier);
  const setParetoPoolMultiplier = useAppStore((s) => s.setParetoPoolMultiplier);
  const distanceMode = useAppStore((s) => s.distanceMode);
  const setDistanceMode = useAppStore((s) => s.setDistanceMode);
  const evolveproRound = useAppStore((s) => s.evolveproRound);
  const setEvolveproRound = useAppStore((s) => s.setEvolveproRound);
  const roundSize = useAppStore((s) => s.roundSize);
  const setRoundSize = useAppStore((s) => s.setRoundSize);
  const benchmarkTopPercentile = useAppStore((s) => s.benchmarkTopPercentile);
  const setBenchmarkTopPercentile = useAppStore((s) => s.setBenchmarkTopPercentile);
  const benchmarkRandomTrials = useAppStore((s) => s.benchmarkRandomTrials);
  const setBenchmarkRandomTrials = useAppStore((s) => s.setBenchmarkRandomTrials);
  const benchmarkRandomSeed = useAppStore((s) => s.benchmarkRandomSeed);
  const setBenchmarkRandomSeed = useAppStore((s) => s.setBenchmarkRandomSeed);
  const benchmarkRunning = useAppStore((s) => s.benchmarkRunning);
  const runBenchmark = useAppStore((s) => s.runBenchmark);
  const yPredMap = useAppStore((s) => s.yPredMap);
  const structureLoaded = useAppStore((s) => s.structureLoaded);
  const structureLoading = useAppStore((s) => s.structureLoading);
  const autoRedesignOnLoad = useAppStore((s) => s.autoRedesignOnLoad);
  const setAutoRedesignOnLoad = useAppStore((s) => s.setAutoRedesignOnLoad);
  const saveCache = useAppStore((s) => s.saveCache);
  const setSaveCache = useAppStore((s) => s.setSaveCache);
  const mutationText = useAppStore((s) => s.mutationText);

  const selectedCount = useMemo(
    () => mutationText.split("\n").filter((l) => l.trim() && !l.trim().startsWith("#")).length,
    [mutationText],
  );

  // Advanced accordion
  const [showAdvanced, setShowAdvanced] = useState(false);

  // Local inputs for manual domain entry
  const [addingDomain, setAddingDomain] = useState(false);
  const [newDomainName, setNewDomainName] = useState("");
  const [newDomainStart, setNewDomainStart] = useState("");
  const [newDomainEnd, setNewDomainEnd] = useState("");

  // Local inputs for numeric fields
  const [maxPerPosStr, setMaxPerPosStr] = useState(String(maxPerPosition));
  const commitMaxPerPos = () => {
    const n = parseInt(maxPerPosStr);
    if (isFinite(n) && n >= 1) setMaxPerPosition(n);
  };

  const [roundStr, setRoundStr] = useState(String(evolveproRound));
  const commitRound = () => {
    const n = parseInt(roundStr);
    if (isFinite(n) && n >= 1) setEvolveproRound(n);
  };

  const [roundSizeStr, setRoundSizeStr] = useState(String(roundSize));
  const commitRoundSize = () => {
    const n = parseInt(roundSizeStr);
    if (isFinite(n) && n >= 1) setRoundSize(n);
  };

  const onEnterBlur = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") (e.target as HTMLInputElement).blur();
  };

  // Auto-computed σ-adaptive params
  const autoParams = computeSigmaParams(evolveproRound, roundSize);

  const distanceBadge = distanceMode === "1d"
    ? "position distance"
    : distanceMode === "3d"
      ? "AlphaFold 3D"
      : structureLoaded
        ? "AlphaFold 3D"
        : "position distance";

  return (
    <div className="relative ml-1">
      {/* Pipeline header */}
      <div className="text-[10px] font-semibold text-gray-500 uppercase tracking-wide mb-1.5">
        Pipeline
      </div>

      {/* Pipeline vertical connector */}
      <div className="border-l-2 border-gray-300 ml-2 pl-3 space-y-2">

        {/* Step 1: Pre-filter — toggle only */}
        <PipelineStep
          step={1}
          label="Pre-filter"
          enabled={positionDiversityEnabled}
          onToggle={setPositionDiversityEnabled}
        />

        <PipelineArrow active={positionDiversityEnabled} />

        {/* Step 2: Domain allocation */}
        <PipelineStep
          step={2}
          label="Domain allocation"
          enabled={domainDiversityEnabled}
          onToggle={setDomainDiversityEnabled}
        >
          <div className="space-y-1.5">
            {/* Linker handling */}
            <div className="flex items-center gap-2 flex-wrap text-[10px] text-gray-500">
              <span>Linker</span>
              {(["include", "separate-bin", "exclude"] as const).map((v) => (
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

            {/* UniProt lookup */}
            <UniprotSearch />

            {/* Domain list */}
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
                      <span className="text-gray-600 truncate">
                        {d.name} ({d.start}-{d.end})
                      </span>
                      {stat && !disabled && (
                        <span className={`ml-auto flex-shrink-0 tabular-nums ${stat.selected < stat.quota ? "text-amber-600" : "text-gray-400"}`}>
                          {stat.selected}/{stat.quota}
                          {stat.selected < stat.quota && " \u26A0"}
                        </span>
                      )}
                    </label>
                  );
                })}
              </div>
            )}

            {/* Add manually */}
            {!addingDomain ? (
              <button
                className="text-[10px] text-blue-500 hover:text-blue-700"
                onClick={() => setAddingDomain(true)}
              >
                + Add manually
              </button>
            ) : (
              <div className="flex gap-1 items-center text-[10px]">
                <input
                  type="text"
                  placeholder="Name"
                  className="w-16 h-4 border border-gray-300 rounded px-1 text-[10px]"
                  value={newDomainName}
                  onChange={(e) => setNewDomainName(e.target.value)}
                />
                <input
                  type="number"
                  placeholder="Start"
                  className="w-10 h-4 border border-gray-300 rounded px-0.5 text-[10px] text-center"
                  value={newDomainStart}
                  onChange={(e) => setNewDomainStart(e.target.value)}
                />
                <span className="text-gray-400">-</span>
                <input
                  type="number"
                  placeholder="End"
                  className="w-10 h-4 border border-gray-300 rounded px-0.5 text-[10px] text-center"
                  value={newDomainEnd}
                  onChange={(e) => setNewDomainEnd(e.target.value)}
                />
                <button
                  className="text-green-600 hover:text-green-800 font-bold"
                  onClick={() => {
                    const s = parseInt(newDomainStart);
                    const e = parseInt(newDomainEnd);
                    if (newDomainName && isFinite(s) && isFinite(e) && s < e) {
                      setDomains([...domains, { name: newDomainName, id: "manual", start: s, end: e, db: "manual" }]);
                      setNewDomainName(""); setNewDomainStart(""); setNewDomainEnd("");
                      setAddingDomain(false);
                    }
                  }}
                >
                  &#10003;
                </button>
                <button className="text-gray-400 hover:text-gray-600" onClick={() => setAddingDomain(false)}>
                  &times;
                </button>
              </div>
            )}
          </div>
        </PipelineStep>

        <PipelineArrow active={domainDiversityEnabled} />

        {/* Step 3: Optimization — toggle + status badge only */}
        <PipelineStep
          step={3}
          label="Optimization"
          enabled={paretoDiversityEnabled}
          onToggle={setParetoDiversityEnabled}
        >
          <div className="flex items-center gap-1.5 flex-wrap text-[10px] text-gray-500">
            <span>{distanceBadge}</span>
            {structureLoading && <span className="text-amber-600">(loading AlphaFold...)</span>}
            {structureLoaded && (
              <span className="inline-flex items-center rounded bg-indigo-100 px-1 py-0.5 text-[10px] font-medium text-indigo-700">
                AlphaFold
              </span>
            )}
            <HelpTip>
              {(distanceMode === "3d" || (distanceMode === "auto" && structureLoaded))
                ? "Selects variants spread apart in 3D space using AlphaFold Cα coordinates."
                : "Greedy Pareto selection that maximises minimum sequence-distance between chosen positions."}
            </HelpTip>
          </div>
        </PipelineStep>
      </div>

      {/* Round section */}
      <div className="ml-2 pl-3 mt-3 space-y-1.5 text-[10px] text-gray-500 border-l-2 border-transparent">
        <div className="font-semibold uppercase tracking-wide text-gray-400">Round</div>
        <div className="flex items-center gap-2 flex-wrap">
          <span>EVOLVEpro Round</span>
          <input
            type="number"
            min={1}
            className="w-10 h-5 border border-gray-300 rounded px-1 text-center text-[10px]"
            value={roundStr}
            onChange={(e: ChangeEvent<HTMLInputElement>) => setRoundStr(e.target.value)}
            onBlur={commitRound}
            onKeyDown={onEnterBlur}
          />
          <span className="text-gray-400">Size</span>
          <input
            type="number"
            min={1}
            max={960}
            className="w-12 h-5 border border-gray-300 rounded px-1 text-center text-[10px]"
            value={roundSizeStr}
            onChange={(e: ChangeEvent<HTMLInputElement>) => setRoundSizeStr(e.target.value)}
            onBlur={commitRoundSize}
            onKeyDown={onEnterBlur}
          />
          <HelpTip>{"Round × size = cumulative data points used to estimate model quality (ρ).\nLower ρ → wider pool and higher entropy weight for exploration."}</HelpTip>
        </div>
        {/* Auto-computed display */}
        <div className="flex items-center gap-2 text-[10px] text-indigo-600 font-mono">
          <span className="inline-flex items-center rounded bg-indigo-50 px-1 py-0.5 text-[9px] font-medium text-indigo-600 border border-indigo-100">
            Auto
          </span>
          <span>K = {autoParams.k.toFixed(2)}</span>
          <span className="text-gray-400">/</span>
          <span>entropy = {autoParams.ew.toFixed(2)}</span>
        </div>
      </div>

      {/* Advanced accordion */}
      <div className="ml-2 pl-3 mt-2 border-l-2 border-transparent">
        <button
          type="button"
          className="flex items-center gap-1 text-[10px] text-gray-400 hover:text-gray-600"
          onClick={() => setShowAdvanced((p) => !p)}
        >
          <span>{showAdvanced ? "▾" : "▸"}</span>
          <span>Advanced</span>
        </button>
        {showAdvanced && (
          <div className="mt-1.5 space-y-2 text-[10px] text-gray-500 pl-2">

            {/* Step 1: position cap */}
            <div>
              <div className="text-[9px] uppercase tracking-wide text-gray-400 mb-0.5">Step 1</div>
              <div className="flex items-center gap-1 flex-wrap">
                <span>Position cap</span>
                <input
                  type="number"
                  min={1}
                  max={20}
                  className="w-10 h-5 border border-gray-300 rounded px-1 text-center text-[10px]"
                  value={maxPerPosStr}
                  onChange={(e: ChangeEvent<HTMLInputElement>) => setMaxPerPosStr(e.target.value)}
                  onBlur={commitMaxPerPos}
                  onKeyDown={onEnterBlur}
                />
                <span>/position</span>
                <HelpTip>Max substitutions per residue. Cap=1 keeps one best variant per position. Uses Grantham-distance tie-break when scores are within 2%.</HelpTip>
              </div>
            </div>

            {/* Step 2: strategy / overlap / quota */}
            <div>
              <div className="text-[9px] uppercase tracking-wide text-gray-400 mb-0.5">Step 2</div>
              <div className="space-y-1">
                <div className="flex items-center gap-2 flex-wrap" role="radiogroup" aria-label="Domain strategy">
                  <span>Strategy</span>
                  {(["proportional", "equal"] as const).map((v) => (
                    <label key={v} className="flex items-center gap-0.5 cursor-pointer">
                      <input type="radio" name="domainStrategy" className="w-2.5 h-2.5"
                        checked={domainStrategy === v} onChange={() => setDomainStrategy(v)} />
                      {v.charAt(0).toUpperCase() + v.slice(1)}
                    </label>
                  ))}
                  <HelpTip>Proportional: quota proportional to domain length. Equal: same quota per domain.</HelpTip>
                </div>
                <div className="flex items-center gap-2 flex-wrap">
                  <span>Overlap</span>
                  {(["first", "largest"] as const).map((v) => (
                    <label key={v} className="flex items-center gap-0.5 cursor-pointer">
                      <input type="radio" name="domainOverlapPolicy" className="w-2.5 h-2.5"
                        checked={domainOverlapPolicy === v} onChange={() => setDomainOverlapPolicy(v)} />
                      {v.charAt(0).toUpperCase() + v.slice(1)}
                    </label>
                  ))}
                </div>
                <div className="flex items-center gap-2">
                  <span>Min quota</span>
                  <input
                    type="number" min={0} max={20}
                    className="w-10 h-5 border border-gray-300 rounded px-1 text-center text-[10px]"
                    value={domainQuotaMin}
                    onChange={(e) => setDomainQuotaMin(Number(e.target.value))}
                  />
                </div>
              </div>
            </div>

            {/* Step 3: distance / pool / entropy overrides */}
            <div>
              <div className="text-[9px] uppercase tracking-wide text-gray-400 mb-0.5">Step 3</div>
              <div className="space-y-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <span>Distance</span>
                  {(["auto", "1d", "3d"] as const).map((v) => (
                    <label key={v} className="flex items-center gap-1 cursor-pointer">
                      <input type="radio" name="distanceMode" className="w-2.5 h-2.5"
                        checked={distanceMode === v} onChange={() => setDistanceMode(v)} />
                      {v.toUpperCase()}
                    </label>
                  ))}
                  <HelpTip>Auto uses AlphaFold Cα when structure is loaded. Force 1D/3D for controlled comparisons.</HelpTip>
                </div>
                <div className="flex items-center gap-2">
                  <span className="w-16">Pool K</span>
                  <input
                    type="range" min="1" max="5" step="0.25"
                    value={paretoPoolMultiplier}
                    onChange={(e) => setParetoPoolMultiplier(Number(e.target.value))}
                    className="w-20 accent-indigo-600"
                    title="Manual pool size override (ignored when Round > 0)"
                  />
                  <span className="font-mono text-gray-700">{paretoPoolMultiplier.toFixed(2)}x</span>
                  <HelpTip>{"Manual pool multiplier. Ignored when EVOLVEpro Round ≥ 1 (σ-adaptive mode).\nAuto K = " + autoParams.k.toFixed(2) + " based on current round."}</HelpTip>
                </div>
                <div className="flex items-center gap-1">
                  <label className="flex items-center gap-1.5 cursor-pointer">
                    <input
                      type="checkbox" className="h-2.5 w-2.5 accent-purple-600"
                      checked={entropyWeightEnabled}
                      onChange={(e) => setEntropyWeightEnabled(e.target.checked)}
                    />
                    <span>Entropy-guided</span>
                    <span className="inline-flex items-center rounded bg-purple-100 px-1 py-0.5 text-[9px] font-medium text-purple-700">β</span>
                  </label>
                  <HelpTip>Positions where EVOLVEpro scores multiple substitutions similarly get an uncertainty bonus. Auto weight = {autoParams.ew.toFixed(2)} based on current round.</HelpTip>
                </div>
                {entropyWeightEnabled && (
                  <div className="flex items-center gap-2 pl-4">
                    <span>Weight</span>
                    <input
                      type="range" min="0" max="1" step="0.05"
                      value={entropyWeight}
                      onChange={(e) => setEntropyWeight(Number(e.target.value))}
                      className="w-20 accent-purple-600"
                      title="Manual entropy weight override (ignored when Round > 0)"
                    />
                    <span className="font-mono text-gray-700">{entropyWeight.toFixed(2)}</span>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Final count */}
      <div className="ml-2 pl-3 mt-2 text-xs font-medium text-gray-700 border-l-2 border-transparent">
        <span className="inline-block w-1.5 h-1.5 rounded-full bg-green-500 mr-1.5 -translate-y-px" />
        {selectedCount} variants selected
      </div>

      {/* Workspace settings */}
      <div className="ml-2 pl-3 mt-2 space-y-1 text-[10px] text-gray-500 border-l-2 border-transparent">
        <div className="font-semibold uppercase tracking-wide text-gray-400">Workspace</div>
        <label className="flex items-center gap-1.5 cursor-pointer">
          <input type="checkbox" className="h-2.5 w-2.5 accent-blue-600"
            checked={autoRedesignOnLoad} onChange={(e) => setAutoRedesignOnLoad(e.target.checked)} />
          Auto re-design on load
        </label>
        <label className="flex items-center gap-1.5 cursor-pointer">
          <input type="checkbox" className="h-2.5 w-2.5 accent-blue-600"
            checked={saveCache} onChange={(e) => setSaveCache(e.target.checked)} />
          Save pipeline cache
        </label>
      </div>

      {/* Benchmark settings */}
      <div className="ml-2 pl-3 mt-2 space-y-1 text-[10px] text-gray-500 border-l-2 border-transparent">
        <div className="font-semibold uppercase tracking-wide text-gray-400">Benchmark</div>
        <div className="flex items-center gap-2">
          <span className="w-20">Top percentile</span>
          <input
            type="number" min={1} max={100} step={1}
            className="w-12 h-5 border border-gray-300 rounded px-1 text-center text-[10px]"
            value={benchmarkTopPercentile}
            onChange={(e) => setBenchmarkTopPercentile(Number(e.target.value))}
          />
          <span>%</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-20">Random trials</span>
          <input
            type="number" min={1} max={1000} step={1}
            className="w-14 h-5 border border-gray-300 rounded px-1 text-center text-[10px]"
            value={benchmarkRandomTrials}
            onChange={(e) => setBenchmarkRandomTrials(Number(e.target.value))}
          />
        </div>
        <div className="flex items-center gap-2">
          <span className="w-20">Random seed</span>
          <input
            type="number"
            className="w-16 h-5 border border-gray-300 rounded px-1 text-center text-[10px]"
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
          className="mt-1 inline-flex items-center rounded border border-gray-300 px-2 py-1 text-[10px] font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
          onClick={() => { void runBenchmark(); }}
          disabled={benchmarkRunning || Object.keys(yPredMap).length === 0}
        >
          {benchmarkRunning ? "Running..." : "Run Benchmark"}
        </button>
      </div>
    </div>
  );
}
