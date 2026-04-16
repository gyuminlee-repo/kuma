import { useEffect, useState, type ChangeEvent, type KeyboardEvent } from "react";
import { sendRequest } from "../../lib/ipc";
import type { PolymeraseProfile } from "../../types/models";
import { PolymeraseEditor } from "../dialogs/PolymeraseEditor";
import { Button } from "../ui/button";
import { HelpTip } from "./InputPanel/DiversitySections";
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
  const polymerases = useAppStore((s) => s.polymerases);
  const selectedPolymerase = useAppStore((s) => s.selectedPolymerase);
  const setSelectedPolymerase = useAppStore((s) => s.setSelectedPolymerase);
  const saveCustomPolymerase = useAppStore((s) => s.saveCustomPolymerase);
  const codonStrategy = useAppStore((s) => s.codonStrategy);
  const maxPrimers = useAppStore((s) => s.maxPrimers);
  const setCodonStrategy = useAppStore((s) => s.setCodonStrategy);
  const setMaxPrimers = useAppStore((s) => s.setMaxPrimers);
  const mutationInputMode = useAppStore((s) => s.mutationInputMode);
  const evolveproTotalCount = useAppStore((s) => s.evolveproTotalCount);
  const isEvolvepro = mutationInputMode === "evolvepro" || mutationInputMode === "multi-evolve";
  const maxLimit = isEvolvepro && evolveproTotalCount > 0 ? evolveproTotalCount : 960;
  const overLimit = isEvolvepro && evolveproTotalCount > 0 && maxPrimers > evolveproTotalCount;

  const tmFwd = useAppStore((s) => s.tmFwdTarget);
  const tmRev = useAppStore((s) => s.tmRevTarget);
  const tmOv = useAppStore((s) => s.tmOverlapTarget);
  const gcMin = useAppStore((s) => s.gcMin);
  const gcMax = useAppStore((s) => s.gcMax);

  const [showAdvanced, setShowAdvanced] = useState(false);
  const [polymeraseEditorOpen, setPolymeraseEditorOpen] = useState(false);
  const [editingPolymerase, setEditingPolymerase] = useState<PolymeraseProfile | null>(null);

  const setTmTargets = useAppStore((s) => s.setTmTargets);
  const setGcRange = useAppStore((s) => s.setGcRange);
  const primerLenEnabled = useAppStore((s) => s.primerLenEnabled);
  const setPrimerLenEnabled = useAppStore((s) => s.setPrimerLenEnabled);
  const fwdLenMin = useAppStore((s) => s.fwdLenMin);
  const fwdLenMax = useAppStore((s) => s.fwdLenMax);
  const revLenMin = useAppStore((s) => s.revLenMin);
  const revLenMax = useAppStore((s) => s.revLenMax);
  const setPrimerLenRange = useAppStore((s) => s.setPrimerLenRange);
  const fillOnFailure = useAppStore((s) => s.fillOnFailure);
  const setFillOnFailure = useAppStore((s) => s.setFillOnFailure);

  const tmFwdInput = useLocalNum(tmFwd, 62, (v) => setTmTargets(v, tmRev, tmOv));
  const tmRevInput = useLocalNum(tmRev, 58, (v) => setTmTargets(tmFwd, v, tmOv));
  const tmOvInput = useLocalNum(tmOv, 42, (v) => setTmTargets(tmFwd, tmRev, v));
  const gcMinInput = useLocalNum(gcMin, 40, (v) => setGcRange(v, gcMax));
  const gcMaxInput = useLocalNum(gcMax, 60, (v) => setGcRange(gcMin, v));
  const fwdLenMinInput = useLocalNum(fwdLenMin, 17, (v) => setPrimerLenRange(v, fwdLenMax, revLenMin, revLenMax));
  const fwdLenMaxInput = useLocalNum(fwdLenMax, 39, (v) => setPrimerLenRange(fwdLenMin, v, revLenMin, revLenMax));
  const revLenMinInput = useLocalNum(revLenMin, 19, (v) => setPrimerLenRange(fwdLenMin, fwdLenMax, v, revLenMax));
  const revLenMaxInput = useLocalNum(revLenMax, 27, (v) => setPrimerLenRange(fwdLenMin, fwdLenMax, revLenMin, v));
  const maxPrimersInput = useLocalNum(maxPrimers, 95, setMaxPrimers);

  const gcInvalid = gcMin >= gcMax;

  const numInput = "w-16 h-6 text-xs border border-gray-300 rounded px-1 text-center focus:outline-none focus:ring-1 focus:ring-green-500";
  const gcInputBase = "w-16 h-6 text-xs rounded px-1 text-center focus:outline-none focus:ring-1";

  const openCustomEditor = async () => {
    try {
      const profile = await sendRequest<PolymeraseProfile>("get_polymerase_details", {
        name: selectedPolymerase,
      });
      setEditingPolymerase(profile);
      setPolymeraseEditorOpen(true);
    } catch {
      setEditingPolymerase(null);
      setPolymeraseEditorOpen(true);
    }
  };

  return (
    <div className="border border-gray-300 rounded p-3 space-y-2">
      <h3 className="text-xs font-semibold text-gray-700 uppercase tracking-wide">
        Parameters
      </h3>

      <div className="space-y-1">
        <label htmlFor="polymerase-select" className="flex items-center gap-2 text-xs">
          <span className="w-24 text-gray-600">Polymerase:</span>
          <select
            id="polymerase-select"
            className="flex-1 min-w-0 h-7 text-xs border border-gray-300 rounded px-2 focus:outline-none focus:ring-1 focus:ring-green-500"
            value={selectedPolymerase}
            onChange={(e) => void setSelectedPolymerase(e.target.value)}
          >
            {polymerases.map((poly) => (
              <option key={poly.name} value={poly.name}>
                {poly.name}
                {poly.manufacturer ? ` (${poly.manufacturer})` : ""}
              </option>
            ))}
          </select>
        </label>
        <div className="flex justify-end">
          <Button type="button" variant="outline" size="sm" onClick={() => void openCustomEditor()}>
            Custom Polymerase
          </Button>
        </div>
      </div>

      <label htmlFor="codon-strategy" className="flex items-center gap-2 text-xs" title="Min. changes = fewest nucleotide changes from WT codon. Optimal = highest-frequency codon for selected organism.">
        <span className="w-24 text-gray-600">Codon:</span>
        <select
          id="codon-strategy"
          className="flex-1 min-w-0 h-7 text-xs border border-gray-300 rounded px-2 focus:outline-none focus:ring-1 focus:ring-green-500"
          value={codonStrategy}
          onChange={(e) => setCodonStrategy(e.target.value as "closest" | "optimal")}
        >
          <option value="closest">Min. changes (fewest nt changes from WT)</option>
          <option value="optimal">Optimal (organism codon usage)</option>
        </select>
      </label>

      <label className="flex items-center gap-2 text-xs" title="Target number of successful primer designs.">
        <span className="w-24 text-gray-600">Mutations:</span>
        <input
          type="number"
          min={1}
          max={maxLimit}
          className={`w-20 h-7 text-xs border rounded px-2 text-center focus:outline-none focus:ring-1 ${
            overLimit ? "border-amber-400 focus:ring-amber-400" : "border-gray-300 focus:ring-green-500"
          }`}
          {...maxPrimersInput}
        />
        <span className="text-gray-400 text-[10px]">
          {Math.ceil(maxPrimers / 96)} plate(s)
        </span>
      </label>
      {overLimit && (
        <div className="text-[10px] text-amber-600 pl-26">
          CSV contains only {evolveproTotalCount} variants
        </div>
      )}

      {/* Advanced Options */}
      <button
        className="text-[10px] text-gray-400 hover:text-gray-600 underline"
        onClick={() => setShowAdvanced(!showAdvanced)}
      >
        {showAdvanced ? "Hide advanced" : "Advanced options..."}
      </button>

      {showAdvanced && (
        <div className="pl-2 border-l-2 border-gray-200 space-y-0.5">
          {/* Tm */}
          <div className="text-[9px] uppercase text-gray-400 tracking-wider pt-0.5" title="Melting temperature targets. SantaLucia 1998 parameters.">Tm</div>
          <div className="flex items-center gap-2 text-xs" title="Melting temperature targets. SantaLucia 1998 parameters.">
            <span className="w-20 text-gray-500">Fwd:</span>
            <input type="number" className={numInput} {...tmFwdInput} />
            <span className="text-gray-400">°C</span>
          </div>
          <div className="flex items-center gap-2 text-xs" title="Melting temperature targets. SantaLucia 1998 parameters.">
            <span className="w-20 text-gray-500">Rev:</span>
            <input type="number" className={numInput} {...tmRevInput} />
            <span className="text-gray-400">°C</span>
          </div>
          <div className="flex items-center gap-2 text-xs" title="Melting temperature targets. SantaLucia 1998 parameters.">
            <span className="w-20 text-gray-500">Overlap:</span>
            <input type="number" className={numInput} {...tmOvInput} />
            <span className="text-gray-400">°C</span>
          </div>

          {/* GC */}
          <div className="text-[9px] uppercase text-gray-400 tracking-wider pt-1.5" title="Recommended range: 40-60%. Primers outside this range receive a penalty.">GC%</div>
          <div className="flex items-center gap-2 text-xs" title="Recommended range: 40-60%. Primers outside this range receive a penalty.">
            <span className="w-20 text-gray-500">Range:</span>
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

          {/* Primer Length */}
          <div className="text-[9px] uppercase text-gray-400 tracking-wider pt-1.5 flex items-center gap-1">
            Primer Length
            <HelpTip>
              {"KOD One PCR Master Mix\n" +
               "  Standard:     22–35 bp, Tm >63°C\n" +
               "  Long targets: 25–35 bp, Tm >65°C\n" +
               "\n" +
               "Experimental (IspS SDM, n=165)\n" +
               "  Forward total: 19–38 bp (incl. overlap)\n" +
               "  Reverse total: 18–32 bp (incl. overlap)\n" +
               "\n" +
               "KURO primer length = overlap + priming region"}
            </HelpTip>
          </div>
          <label className="flex items-center gap-1 text-xs cursor-pointer">
            <input
              type="checkbox"
              className="h-3 w-3 accent-green-600"
              checked={primerLenEnabled}
              onChange={(e) => setPrimerLenEnabled(e.target.checked)}
            />
            <span className="text-gray-500">Limit</span>
            {primerLenEnabled && (
              <span className="flex items-center gap-1 ml-1">
                <span className="text-gray-400">F</span>
                <input type="number" className={numInput} {...fwdLenMinInput} />
                <span className="text-gray-400">~</span>
                <input type="number" className={numInput} {...fwdLenMaxInput} />
              </span>
            )}
          </label>
          {primerLenEnabled && (
            <>
              <div className="flex items-center gap-1 text-xs pl-4">
                <span className="text-gray-400 ml-3">R</span>
                <input type="number" className={numInput} {...revLenMinInput} />
                <span className="text-gray-400">~</span>
                <input type="number" className={numInput} {...revLenMaxInput} />
                <span className="text-gray-400 text-[10px]">bp</span>
              </div>
              {(fwdLenMin >= fwdLenMax || revLenMin >= revLenMax) && (
                <div className="text-[10px] text-red-500 pl-8">Min must be less than Max</div>
              )}
            </>
          )}

          {/* Design Behavior */}
          <div className="text-[9px] uppercase text-gray-400 tracking-wider pt-1.5">Design</div>
          <label className="flex items-center gap-1 text-xs cursor-pointer" title="When ON, automatically fills the requested count from extra candidates when some mutations fail.">
            <input
              type="checkbox"
              className="h-3 w-3 accent-green-600"
              checked={fillOnFailure}
              onChange={(e) => setFillOnFailure(e.target.checked)}
            />
            <span className="text-gray-500">Fill on failure</span>
          </label>
        </div>
      )}

      <PolymeraseEditor
        open={polymeraseEditorOpen}
        profile={editingPolymerase}
        onOpenChange={setPolymeraseEditorOpen}
        onSave={saveCustomPolymerase}
      />
    </div>
  );
}
