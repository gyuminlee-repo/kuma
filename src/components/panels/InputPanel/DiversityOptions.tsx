import { useMemo, useState, type ChangeEvent, type KeyboardEvent } from "react";
import { useAppStore } from "../../../store/appStore";
import { UniprotSearch } from "./UniprotSearch";

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
  children: React.ReactNode;
}) {
  return (
    <div className={`relative transition-opacity ${enabled ? "opacity-100" : "opacity-50"}`}>
      {/* Step dot on the vertical line */}
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
      {enabled && <div className="pl-4 space-y-1">{children}</div>}
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
      <span className="text-gray-400 select-none leading-none">{"\u25BC"}</span>
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
  const domains = useAppStore((s) => s.domains);
  const setDomains = useAppStore((s) => s.setDomains);
  const toggleDomain = useAppStore((s) => s.toggleDomain);
  const disabledDomains = useAppStore((s) => s.disabledDomains);
  const domainStats = useAppStore((s) => s.domainStats);
  const paretoDiversityEnabled = useAppStore((s) => s.paretoDiversityEnabled);
  const setParetoDiversityEnabled = useAppStore((s) => s.setParetoDiversityEnabled);
  const entropyWeightEnabled = useAppStore((s) => s.entropyWeightEnabled);
  const setEntropyWeightEnabled = useAppStore((s) => s.setEntropyWeightEnabled);
  const esmEmbeddingLoaded = useAppStore((s) => s.esmEmbeddingLoaded);
  const esmEmbeddingLoading = useAppStore((s) => s.esmEmbeddingLoading);
  const mutationText = useAppStore((s) => s.mutationText);

  const selectedCount = useMemo(
    () =>
      mutationText
        .split("\n")
        .filter((l) => l.trim() && !l.trim().startsWith("#")).length,
    [mutationText],
  );

  // Local state for maxPerPosition string input
  const [maxPerPosStr, setMaxPerPosStr] = useState(String(maxPerPosition));
  const commitMaxPerPos = () => {
    const n = parseInt(maxPerPosStr);
    if (isFinite(n) && n >= 1) setMaxPerPosition(n);
  };
  const onMaxPerPosKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") (e.target as HTMLInputElement).blur();
  };

  // Local state for manual domain entry
  const [addingDomain, setAddingDomain] = useState(false);
  const [newDomainName, setNewDomainName] = useState("");
  const [newDomainStart, setNewDomainStart] = useState("");
  const [newDomainEnd, setNewDomainEnd] = useState("");

  return (
    <div className="relative ml-1">
      {/* Pipeline header */}
      <div className="text-[10px] font-semibold text-gray-500 uppercase tracking-wide mb-1.5">
        Pipeline
      </div>

      {/* Pipeline vertical connector */}
      <div className="border-l-2 border-gray-300 ml-2 pl-3 space-y-2">

        {/* Step 1: Pre-filter */}
        <PipelineStep
          step={1}
          label="Pre-filter"
          enabled={positionDiversityEnabled}
          onToggle={setPositionDiversityEnabled}
        >
          <div className="flex items-center gap-1 text-xs">
            <span className="text-gray-500">Position cap: max</span>
            <input
              type="number"
              min={1}
              max={20}
              className="w-10 h-5 text-xs border border-gray-300 rounded px-1 text-center focus:outline-none focus:ring-1 focus:ring-green-500"
              value={maxPerPosStr}
              onChange={(e: ChangeEvent<HTMLInputElement>) => setMaxPerPosStr(e.target.value)}
              onBlur={commitMaxPerPos}
              onKeyDown={onMaxPerPosKeyDown}
            />
            <span className="text-gray-500">/position</span>
          </div>
        </PipelineStep>

        {/* Step connector arrow */}
        <PipelineArrow active={positionDiversityEnabled} />

        {/* Step 2: Domain allocation */}
        <PipelineStep
          step={2}
          label="Domain allocation"
          enabled={domainDiversityEnabled}
          onToggle={setDomainDiversityEnabled}
        >
          <div className="space-y-1.5">
            {/* Domain strategy radio */}
            <div className="flex gap-2 text-[10px] text-gray-500">
              <label className="flex items-center gap-0.5 cursor-pointer">
                <input
                  type="radio"
                  name="domainStrategy"
                  className="w-2.5 h-2.5"
                  checked={domainStrategy === "proportional"}
                  onChange={() => setDomainStrategy("proportional")}
                />
                Proportional
              </label>
              <label className="flex items-center gap-0.5 cursor-pointer">
                <input
                  type="radio"
                  name="domainStrategy"
                  className="w-2.5 h-2.5"
                  checked={domainStrategy === "equal"}
                  onChange={() => setDomainStrategy("equal")}
                />
                Equal
              </label>
            </div>

            {/* UniProt lookup */}
            <UniprotSearch />

            {/* Domain list */}
            {domains.length > 0 && (
              <div className="space-y-0.5">
                {domains.map((d) => {
                  const key = `${d.name}-${d.start}`;
                  const disabled = disabledDomains.has(key);
                  const stat = domainStats[d.name];
                  return (
                    <label
                      key={key}
                      className={`flex items-center gap-1 text-[10px] cursor-pointer ${
                        disabled ? "opacity-40" : ""
                      }`}
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
                        <span
                          className={`ml-auto flex-shrink-0 tabular-nums ${
                            stat.selected < stat.quota ? "text-amber-600" : "text-gray-400"
                          }`}
                        >
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
                      setDomains([
                        ...domains,
                        { name: newDomainName, id: "manual", start: s, end: e, db: "manual" },
                      ]);
                      setNewDomainName("");
                      setNewDomainStart("");
                      setNewDomainEnd("");
                      setAddingDomain(false);
                    }
                  }}
                >
                  &#10003;
                </button>
                <button
                  className="text-gray-400 hover:text-gray-600"
                  onClick={() => setAddingDomain(false)}
                >
                  &times;
                </button>
              </div>
            )}
          </div>
        </PipelineStep>

        {/* Step connector arrow */}
        <PipelineArrow active={domainDiversityEnabled} />

        {/* Step 3: Optimization */}
        <PipelineStep
          step={3}
          label="Optimization"
          enabled={paretoDiversityEnabled}
          onToggle={setParetoDiversityEnabled}
        >
          <div className="space-y-1.5">
            <div className="text-xs text-gray-500">
              {esmEmbeddingLoaded
                ? "ESM-2 structural distance"
                : "Pareto spread (maximize position distance)"}
              {esmEmbeddingLoading && (
                <span className="ml-1.5 text-amber-600">(loading ESM-2...)</span>
              )}
              {esmEmbeddingLoaded && (
                <span className="ml-1.5 inline-flex items-center rounded bg-indigo-100 px-1 py-0.5 text-[10px] font-medium text-indigo-700">
                  ESM-2
                </span>
              )}
            </div>
            <label
              className="flex items-center gap-1.5 cursor-pointer text-[10px] text-gray-500"
              title="Blend position entropy into selection score (weight 0.3). Positions where many mutations score similarly are prioritised — helps escape local optima."
            >
              <input
                type="checkbox"
                className="h-2.5 w-2.5 accent-purple-600"
                checked={entropyWeightEnabled}
                onChange={(e) => setEntropyWeightEnabled(e.target.checked)}
              />
              Entropy-guided
              <span className="ml-0.5 inline-flex items-center rounded bg-purple-100 px-1 py-0.5 text-[9px] font-medium text-purple-700">
                β
              </span>
            </label>
          </div>
        </PipelineStep>
      </div>

      {/* Final count */}
      <div className="ml-2 pl-3 mt-2 text-xs font-medium text-gray-700 border-l-2 border-transparent">
        <span className="inline-block w-1.5 h-1.5 rounded-full bg-green-500 mr-1.5 -translate-y-px" />
        {selectedCount} variants selected
      </div>
    </div>
  );
}
