import { useEffect, useState, type ChangeEvent, type KeyboardEvent } from "react";
import { sendRequest } from "../../lib/ipc-kuro";
import { formatError } from "../../lib/utils";
import type { CodonStrategy, PolymeraseProfile } from "../../types/models";
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
  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => { if (e.key === "Enter") e.currentTarget.blur(); };
  return { value: str, onChange, onBlur, onKeyDown };
}

function isCodonStrategy(value: string): value is CodonStrategy {
  return value === "closest" || value === "optimal";
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
  const maxLimit = isEvolvepro && evolveproTotalCount > 0 ? evolveproTotalCount : 10000;
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
  const setStatus = useAppStore((s) => s.setStatus);

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

  const numInput = "h-control w-16 rounded-control border border-border px-1 text-center text-caption focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2";
  const gcInputBase = "h-control w-16 rounded-control px-1 text-center text-caption focus:outline-none focus-visible:ring-2 focus-visible:ring-ring";

  const openCustomEditor = async () => {
    try {
      const profile = await sendRequest("get_polymerase_details", {
        name: selectedPolymerase,
      });
      setEditingPolymerase(profile);
      setPolymeraseEditorOpen(true);
    } catch (err) {
      setStatus(`Polymerase load failed: ${formatError(err)}`);
    }
  };

  return (
    <section className="space-y-3 rounded-container border border-border bg-card p-3">
      <div>
        <div className="text-caption font-semibold uppercase tracking-widest text-muted-foreground">Control</div>
        <h3 className="text-title font-semibold text-foreground">Parameters</h3>
      </div>

      <div className="space-y-1">
        <label htmlFor="polymerase-select" className="flex items-center gap-2 text-caption">
          <span className="w-24 text-muted-foreground">Polymerase:</span>
          <select
            id="polymerase-select"
            className="h-control min-w-0 flex-1 rounded-control border border-border bg-card px-3 text-caption focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
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
          <Button type="button" variant="outline" size="sm" className="h-control rounded-control" onClick={() => void openCustomEditor()}>
            Custom Polymerase
          </Button>
        </div>
      </div>

      <label htmlFor="codon-strategy" className="flex items-center gap-2 text-caption" title="Min. changes = fewest nucleotide changes from WT codon. Optimal = highest-frequency codon for selected organism.">
        <span className="w-24 text-muted-foreground">Codon:</span>
        <select
          id="codon-strategy"
          className="h-control min-w-0 flex-1 rounded-control border border-border bg-card px-3 text-caption focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
          value={codonStrategy}
          onChange={(e) => {
            if (isCodonStrategy(e.target.value)) {
              setCodonStrategy(e.target.value);
            }
          }}
        >
          <option value="closest">Min. changes (fewest nt changes from WT)</option>
          <option value="optimal">Optimal (organism codon usage)</option>
        </select>
      </label>

      <label className="flex items-center gap-2 text-caption" title="Target number of successful primer designs.">
        <span className="w-24 text-muted-foreground">Mutations:</span>
        <input
          type="number"
          min={1}
          max={maxLimit}
          className={`h-control w-20 rounded-control border px-2 text-center text-caption focus:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
            overLimit ? "border-warning focus:ring-warning" : "border-border"
          }`}
          {...maxPrimersInput}
        />
        <span className="text-caption text-muted-foreground">
          {Math.ceil(maxPrimers / 96)} plate(s)
        </span>
      </label>
      {overLimit && (
        <div className="text-caption text-warning pl-26">
          CSV contains only {evolveproTotalCount} variants
        </div>
      )}

      {/* Advanced Options */}
      <button
        className="text-caption font-medium text-muted-foreground underline underline-offset-4 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
        onClick={() => setShowAdvanced(!showAdvanced)}
      >
        {showAdvanced ? "Hide advanced" : "Advanced options..."}
      </button>

      {showAdvanced && (
        <div className="space-y-1 rounded-container border border-border bg-card/80 p-3">
          {/* Tm */}
          <div className="pt-0.5 text-caption uppercase tracking-wider text-muted-foreground" title="Melting temperature targets. SantaLucia 1998 parameters.">Tm</div>
          <div className="flex items-center gap-2 text-caption" title="Melting temperature targets. SantaLucia 1998 parameters.">
            <span className="w-20 text-muted-foreground">Fwd:</span>
            <input type="number" className={numInput} {...tmFwdInput} />
            <span className="text-muted-foreground">°C</span>
          </div>
          <div className="flex items-center gap-2 text-caption" title="Melting temperature targets. SantaLucia 1998 parameters.">
            <span className="w-20 text-muted-foreground">Rev:</span>
            <input type="number" className={numInput} {...tmRevInput} />
            <span className="text-muted-foreground">°C</span>
          </div>
          <div className="flex items-center gap-2 text-caption" title="Melting temperature targets. SantaLucia 1998 parameters.">
            <span className="w-20 text-muted-foreground">Overlap:</span>
            <input type="number" className={numInput} {...tmOvInput} />
            <span className="text-muted-foreground">°C</span>
          </div>

          {/* GC */}
          <div className="pt-1.5 text-caption uppercase tracking-wider text-muted-foreground" title="Recommended range: 40-60%. Primers outside this range receive a penalty.">GC%</div>
          <div className="flex items-center gap-2 text-caption" title="Recommended range: 40-60%. Primers outside this range receive a penalty.">
            <span className="w-20 text-muted-foreground">Range:</span>
            <input type="number"
              className={`${gcInputBase} ${gcInvalid ? "border-error focus:ring-error" : "border-border"}`}
              {...gcMinInput} />
            <span className="text-muted-foreground">~</span>
            <input type="number"
              className={`${gcInputBase} ${gcInvalid ? "border-error focus:ring-error" : "border-border"}`}
              {...gcMaxInput} />
            <span className="text-muted-foreground">%</span>
          </div>
          {gcInvalid && (
            <div className="text-caption text-error pl-20">Min must be less than Max</div>
          )}

          {/* Primer Length */}
          <div className="flex items-center gap-1 pt-1.5 text-caption uppercase tracking-wider text-muted-foreground">
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
          <label className="flex items-center gap-1 text-caption cursor-pointer">
            <input
              type="checkbox"
              className="h-3 w-3 accent-primary"
              checked={primerLenEnabled}
              onChange={(e) => setPrimerLenEnabled(e.target.checked)}
            />
            <span className="text-muted-foreground">Limit</span>
            {primerLenEnabled && (
              <span className="flex items-center gap-1 ml-1">
                <span className="text-muted-foreground">F</span>
                <input type="number" className={numInput} {...fwdLenMinInput} />
                <span className="text-muted-foreground">~</span>
                <input type="number" className={numInput} {...fwdLenMaxInput} />
              </span>
            )}
          </label>
          {primerLenEnabled && (
            <>
              <div className="flex items-center gap-1 text-caption pl-4">
                <span className="ml-3 text-muted-foreground">R</span>
                <input type="number" className={numInput} {...revLenMinInput} />
                <span className="text-muted-foreground">~</span>
                <input type="number" className={numInput} {...revLenMaxInput} />
                <span className="text-caption text-muted-foreground">bp</span>
              </div>
              {(fwdLenMin >= fwdLenMax || revLenMin >= revLenMax) && (
                <div className="text-caption text-error pl-8">Min must be less than Max</div>
              )}
            </>
          )}

          {/* Design Behavior */}
          <div className="pt-1.5 text-caption uppercase tracking-wider text-muted-foreground">Design</div>
          <label className="flex items-center gap-1 text-caption cursor-pointer" title="When ON, automatically fills the requested count from extra candidates when some mutations fail.">
            <input
              type="checkbox"
              className="h-3 w-3 accent-primary"
              checked={fillOnFailure}
              onChange={(e) => setFillOnFailure(e.target.checked)}
            />
            <span className="text-muted-foreground">Fill on failure</span>
          </label>
        </div>
      )}

      <PolymeraseEditor
        open={polymeraseEditorOpen}
        profile={editingPolymerase}
        onOpenChange={setPolymeraseEditorOpen}
        onSave={saveCustomPolymerase}
      />
    </section>
  );
}
