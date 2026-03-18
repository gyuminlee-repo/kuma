import { useEffect, useState, type ChangeEvent, type KeyboardEvent } from "react";
import { useAppStore } from "../../store/appStore";

/** Local string state synced with a numeric store value. Commits on blur/Enter. */
function useLocalNum(storeVal: number, fallback: number, commit: (v: number) => void) {
  const [str, setStr] = useState(String(storeVal));
  useEffect(() => setStr(String(storeVal)), [storeVal]);
  const onChange = (e: ChangeEvent<HTMLInputElement>) => setStr(e.target.value);
  const onBlur = () => { const n = parseFloat(str); commit(!isFinite(n) ? fallback : n); };
  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); };
  return { value: str, onChange, onBlur, onKeyDown };
}

export function ParameterPanel() {
  const selectedGene = useAppStore((s) => s.selectedGene);
  const codonStrategy = useAppStore((s) => s.codonStrategy);
  const maxPrimers = useAppStore((s) => s.maxPrimers);
  const seqInfo = useAppStore((s) => s.seqInfo);
  const setSelectedGene = useAppStore((s) => s.setSelectedGene);
  const setCodonStrategy = useAppStore((s) => s.setCodonStrategy);
  const setMaxPrimers = useAppStore((s) => s.setMaxPrimers);

  const tmFwd = useAppStore((s) => s.tmFwdTarget);
  const tmRev = useAppStore((s) => s.tmRevTarget);
  const tmOv = useAppStore((s) => s.tmOverlapTarget);
  const gcMin = useAppStore((s) => s.gcMin);
  const gcMax = useAppStore((s) => s.gcMax);

  const [showAdvanced, setShowAdvanced] = useState(false);

  const setTmTargets = useAppStore((s) => s.setTmTargets);
  const setGcRange = useAppStore((s) => s.setGcRange);

  const tmFwdInput = useLocalNum(tmFwd, 62, (v) => setTmTargets(v, tmRev, tmOv));
  const tmRevInput = useLocalNum(tmRev, 58, (v) => setTmTargets(tmFwd, v, tmOv));
  const tmOvInput = useLocalNum(tmOv, 42, (v) => setTmTargets(tmFwd, tmRev, v));
  const gcMinInput = useLocalNum(gcMin, 40, (v) => setGcRange(v, gcMax));
  const gcMaxInput = useLocalNum(gcMax, 60, (v) => setGcRange(gcMin, v));
  const maxPrimersInput = useLocalNum(maxPrimers, 95, setMaxPrimers);

  const gcInvalid = gcMin >= gcMax;

  const numInput = "w-16 h-6 text-xs border border-gray-300 rounded px-1 text-center focus:outline-none focus:ring-1 focus:ring-green-500";
  const gcInputBase = "w-16 h-6 text-xs rounded px-1 text-center focus:outline-none focus:ring-1";

  return (
    <div className="border border-gray-300 rounded p-3 space-y-2">
      <h3 className="text-xs font-semibold text-gray-700 uppercase tracking-wide">
        Parameters
      </h3>

      <label className="flex items-center gap-2 text-xs">
        <span className="w-24 text-gray-600">Target Gene:</span>
        {seqInfo && seqInfo.genes.length > 0 ? (
          <select
            className="flex-1 h-7 text-xs border border-gray-300 rounded px-2 focus:outline-none focus:ring-1 focus:ring-green-500"
            value={selectedGene}
            onChange={(e) => setSelectedGene(e.target.value)}
          >
            {[...seqInfo.genes].sort((a, b) => a.cds_start - b.cds_start).map((g) => {
              const isNamed = g.gene !== "ORF1" && g.gene !== "unknown";
              const label = isNamed ? `[${g.gene}]` : `(${g.gene})`;
              return (
                <option key={g.cds_start} value={String(g.cds_start)}>
                  {label} {g.cds_start}-{g.cds_end} ({g.aa_length} aa){g.product ? ` ${g.product}` : ""}
                </option>
              );
            })}
          </select>
        ) : (
          <span className="text-xs text-gray-400 italic">Load a sequence file first</span>
        )}
      </label>

      <label className="flex items-center gap-2 text-xs">
        <span className="w-24 text-gray-600">Codon:</span>
        <select
          className="flex-1 h-7 text-xs border border-gray-300 rounded px-2 focus:outline-none focus:ring-1 focus:ring-green-500"
          value={codonStrategy}
          onChange={(e) => setCodonStrategy(e.target.value as "closest" | "optimal")}
        >
          <option value="closest">Min. changes (fewest nt changes from WT)</option>
          <option value="optimal">Optimal (E. coli codon usage)</option>
        </select>
      </label>

      <label className="flex items-center gap-2 text-xs">
        <span className="w-24 text-gray-600">Mutations:</span>
        <input
          type="number"
          min={1}
          max={960}
          className="w-20 h-7 text-xs border border-gray-300 rounded px-2 text-center focus:outline-none focus:ring-1 focus:ring-green-500"
          {...maxPrimersInput}
        />
        <span className="text-gray-400 text-[10px]">
          {Math.ceil(maxPrimers / 96)} plate(s)
        </span>
      </label>

      {/* Advanced Options */}
      <button
        className="text-[10px] text-gray-400 hover:text-gray-600 underline"
        onClick={() => setShowAdvanced(!showAdvanced)}
      >
        {showAdvanced ? "Hide advanced" : "Advanced options..."}
      </button>

      {showAdvanced && (
        <div className="space-y-1.5 pl-2 border-l-2 border-gray-200">
          <div className="flex items-center gap-2 text-xs">
            <span className="w-20 text-gray-500">Tm Fwd:</span>
            <input type="number" className={numInput} {...tmFwdInput} />
            <span className="text-gray-400">°C</span>
          </div>
          <div className="flex items-center gap-2 text-xs">
            <span className="w-20 text-gray-500">Tm Rev:</span>
            <input type="number" className={numInput} {...tmRevInput} />
            <span className="text-gray-400">°C</span>
          </div>
          <div className="flex items-center gap-2 text-xs">
            <span className="w-20 text-gray-500">Tm Overlap:</span>
            <input type="number" className={numInput} {...tmOvInput} />
            <span className="text-gray-400">°C</span>
          </div>
          <div className="flex items-center gap-2 text-xs">
            <span className="w-20 text-gray-500">GC%:</span>
            <input type="number"
              className={`${gcInputBase} ${gcInvalid ? "border-red-400 focus:ring-red-400" : "border-gray-300 focus:ring-green-500"}`}
              {...gcMinInput} />
            <span className="text-gray-400">~</span>
            <input type="number"
              className={`${gcInputBase} ${gcInvalid ? "border-red-400 focus:ring-red-400" : "border-gray-300 focus:ring-green-500"}`}
              {...gcMaxInput} />
            <span className="text-gray-400">%</span>
          </div>
          {gcInvalid && (
            <div className="text-[10px] text-red-500 pl-20">Min must be less than Max</div>
          )}
        </div>
      )}
    </div>
  );
}
