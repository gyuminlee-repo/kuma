import { useEffect, useState } from "react";
import { useAppStore } from "../../store/appStore";

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

  // Local string states for Tm inputs to allow typing without reset
  const [tmFwdStr, setTmFwdStr] = useState(String(tmFwd));
  const [tmRevStr, setTmRevStr] = useState(String(tmRev));
  const [tmOvStr, setTmOvStr] = useState(String(tmOv));
  const [gcMinStr, setGcMinStr] = useState(String(gcMin));
  const [gcMaxStr, setGcMaxStr] = useState(String(gcMax));

  // Sync local strings when store changes externally (e.g. workspace load)
  useEffect(() => setTmFwdStr(String(tmFwd)), [tmFwd]);
  useEffect(() => setTmRevStr(String(tmRev)), [tmRev]);
  useEffect(() => setTmOvStr(String(tmOv)), [tmOv]);
  useEffect(() => setGcMinStr(String(gcMin)), [gcMin]);
  useEffect(() => setGcMaxStr(String(gcMax)), [gcMax]);

  const setTmTargets = useAppStore((s) => s.setTmTargets);
  const setGcRange = useAppStore((s) => s.setGcRange);

  function parseNum(str: string, fallback: number): number {
    const n = parseFloat(str);
    return isNaN(n) ? fallback : n;
  }

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
          value={maxPrimers}
          onChange={(e) => setMaxPrimers(parseInt(e.target.value, 10) || 95)}
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
            <input type="number" className={numInput} value={tmFwdStr}
              onChange={(e) => setTmFwdStr(e.target.value)}
              onBlur={() => setTmTargets(parseNum(tmFwdStr, 62), tmRev, tmOv)}
              onKeyDown={(e) => { if (e.key === "Enter") { (e.target as HTMLInputElement).blur(); setTmTargets(parseNum(tmFwdStr, 62), tmRev, tmOv); } }} />
            <span className="text-gray-400">°C</span>
          </div>
          <div className="flex items-center gap-2 text-xs">
            <span className="w-20 text-gray-500">Tm Rev:</span>
            <input type="number" className={numInput} value={tmRevStr}
              onChange={(e) => setTmRevStr(e.target.value)}
              onBlur={() => setTmTargets(tmFwd, parseNum(tmRevStr, 58), tmOv)}
              onKeyDown={(e) => { if (e.key === "Enter") { (e.target as HTMLInputElement).blur(); setTmTargets(tmFwd, parseNum(tmRevStr, 58), tmOv); } }} />
            <span className="text-gray-400">°C</span>
          </div>
          <div className="flex items-center gap-2 text-xs">
            <span className="w-20 text-gray-500">Tm Overlap:</span>
            <input type="number" className={numInput} value={tmOvStr}
              onChange={(e) => setTmOvStr(e.target.value)}
              onBlur={() => setTmTargets(tmFwd, tmRev, parseNum(tmOvStr, 42))}
              onKeyDown={(e) => { if (e.key === "Enter") { (e.target as HTMLInputElement).blur(); setTmTargets(tmFwd, tmRev, parseNum(tmOvStr, 42)); } }} />
            <span className="text-gray-400">°C</span>
          </div>
          <div className="flex items-center gap-2 text-xs">
            <span className="w-20 text-gray-500">GC%:</span>
            <input type="number"
              className={`${gcInputBase} ${gcInvalid ? "border-red-400 focus:ring-red-400" : "border-gray-300 focus:ring-green-500"}`}
              value={gcMinStr}
              onChange={(e) => setGcMinStr(e.target.value)}
              onBlur={() => setGcRange(parseNum(gcMinStr, 40), gcMax)}
              onKeyDown={(e) => { if (e.key === "Enter") { (e.target as HTMLInputElement).blur(); setGcRange(parseNum(gcMinStr, 40), gcMax); } }} />
            <span className="text-gray-400">~</span>
            <input type="number"
              className={`${gcInputBase} ${gcInvalid ? "border-red-400 focus:ring-red-400" : "border-gray-300 focus:ring-green-500"}`}
              value={gcMaxStr}
              onChange={(e) => setGcMaxStr(e.target.value)}
              onBlur={() => setGcRange(gcMin, parseNum(gcMaxStr, 60))}
              onKeyDown={(e) => { if (e.key === "Enter") { (e.target as HTMLInputElement).blur(); setGcRange(gcMin, parseNum(gcMaxStr, 60)); } }} />
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
