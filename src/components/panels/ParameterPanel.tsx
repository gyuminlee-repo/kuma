import { useEffect, useRef, useState, type ChangeEvent, type KeyboardEvent } from "react";
import { sendRequest } from "../../lib/ipc-kuro";
import { formatError } from "../../lib/utils";
import type { CodonStrategy, OverlapMode, PolymeraseProfile } from "../../types/models";
import { PolymeraseEditor } from "../dialogs/PolymeraseEditor";
import { Button } from "../ui/button";
import { HelpTip } from "./InputPanel/DiversitySections";
import { InlineHelp } from "../ui/InlineHelp";
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

function isOverlapMode(value: string): value is OverlapMode {
  return value === "partial" || value === "full";
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
  const overlapMode = useAppStore((s) => s.overlapMode);
  const setOverlapMode = useAppStore((s) => s.setOverlapMode);
  const randomSeed = useAppStore((s) => s.randomSeed);
  const setRandomSeed = useAppStore((s) => s.setRandomSeed);
  const setStatus = useAppStore((s) => s.setStatus);

  const [showAdvanced, setShowAdvanced] = useState(false);
  const [polymeraseEditorOpen, setPolymeraseEditorOpen] = useState(false);
  const [editingPolymerase, setEditingPolymerase] = useState<PolymeraseProfile | null>(null);
  const [seedStr, setSeedStr] = useState(() =>
    useAppStore.getState().randomSeed !== null
      ? String(useAppStore.getState().randomSeed)
      : "",
  );
  const seedStrRef = useRef(seedStr);
  seedStrRef.current = seedStr;
  // sync external reset (e.g. workspace load)
  useEffect(() => {
    setSeedStr(randomSeed !== null ? String(randomSeed) : "");
  }, [randomSeed]);

  const isFullOverlap = overlapMode === "full";

  const tmFwdInput = useLocalNum(tmFwd, 62, (v) => setTmTargets(v, tmRev, tmOv));
  const tmRevInput = useLocalNum(tmRev, 58, (v) => setTmTargets(tmFwd, v, tmOv));
  const tmOvInput = useLocalNum(tmOv, 42, (v) => setTmTargets(tmFwd, tmRev, v));
  const tmTolerance = useAppStore((s) => s.tmTolerance);
  const setTmTolerance = useAppStore((s) => s.setTmTolerance);
  const tmTolInput = useLocalNum(tmTolerance, 3.0, setTmTolerance);
  const gcMinInput = useLocalNum(gcMin, 40, (v) => setGcRange(v, gcMax));
  const gcMaxInput = useLocalNum(gcMax, 60, (v) => setGcRange(gcMin, v));
  const fwdLenMinInput = useLocalNum(fwdLenMin, 17, (v) => setPrimerLenRange(v, fwdLenMax, revLenMin, revLenMax));
  const fwdLenMaxInput = useLocalNum(fwdLenMax, 39, (v) => setPrimerLenRange(fwdLenMin, v, revLenMin, revLenMax));
  const revLenMinInput = useLocalNum(revLenMin, 19, (v) => setPrimerLenRange(fwdLenMin, fwdLenMax, v, revLenMax));
  const revLenMaxInput = useLocalNum(revLenMax, 27, (v) => setPrimerLenRange(fwdLenMin, fwdLenMax, revLenMin, v));
  // Full mode: single length range mirrors to both fwd and rev (engine intersects fwd/rev limits).
  const fullLenMinInput = useLocalNum(fwdLenMin, 17, (v) => setPrimerLenRange(v, fwdLenMax, v, fwdLenMax));
  const fullLenMaxInput = useLocalNum(fwdLenMax, 39, (v) => setPrimerLenRange(fwdLenMin, v, fwdLenMin, v));
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

      {/* Strategy — top-level switch that changes the meaning of parameters below */}
      <div className="space-y-1">
        <label
          htmlFor="design-strategy-select"
          className="flex items-center gap-2 text-caption"
        >
          <span className="w-24 text-muted-foreground">Strategy:</span>
          <InlineHelp text={"Partial (Gibson): overlap upstream of the codon; fwd and rev are independent.\nFull (Q5 SDM): rev = rc(fwd); single primer covers the mutation."} />
          <select
            id="design-strategy-select"
            className="h-control min-w-0 flex-1 rounded-control border border-border bg-card px-3 text-caption focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
            value={overlapMode}
            onChange={(e) => {
              if (isOverlapMode(e.target.value)) {
                setOverlapMode(e.target.value);
              }
            }}
            aria-describedby="design-strategy-hint"
          >
            <option value="partial">Partial overlap (Gibson)</option>
            <option value="full">Full overlap (Q5 SDM)</option>
          </select>
        </label>
        <p id="design-strategy-hint" className="pl-26 text-caption text-muted-foreground">
          {isFullOverlap
            ? "Reverse = rc(forward). Single primer Tm and length apply to both."
            : "Forward and reverse are independent with overlap upstream of the codon."}
        </p>
      </div>

      <div className="space-y-1">
        <label htmlFor="polymerase-select" className="flex items-center gap-2 text-caption">
          <span className="w-24 text-muted-foreground">Polymerase:</span>
          <InlineHelp text={"Selects Tm calculation preset (extension Tm target + tolerance defaults).\nChoose the polymerase used in your SDM reaction.\nUse 'Custom Polymerase' to define your own extension Tm."} />
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

      <label htmlFor="codon-strategy" className="flex items-center gap-2 text-caption">
        <span className="w-24 text-muted-foreground">Codon:</span>
        <InlineHelp text={"Min. changes: fewest nucleotide changes from wild-type codon (minimises synthesis cost).\nOptimal: highest-frequency codon for the selected organism (maximises expression)."} />
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

      <label className="flex items-center gap-2 text-caption">
        <span className="w-24 text-muted-foreground">Mutations:</span>
        <InlineHelp text={"Maximum number of primer designs to generate.\nFor EVOLVEpro / multi-evolve mode: capped by the CSV variant count.\nOne 96-well plate fits 95 mutants + 1 WT control."} />
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
          {/* Tm — branches by strategy */}
          <div className="pt-0.5 text-caption uppercase tracking-wider text-muted-foreground" title="Melting temperature targets. SantaLucia 1998 parameters.">Tm</div>
          {isFullOverlap ? (
            <div className="flex items-center gap-2 text-caption" title="Single Tm target. rev = rc(fwd), so both primers share Tm by construction.">
              <span className="w-20 text-muted-foreground">Primer:</span>
              <input type="number" className={numInput} {...tmFwdInput} />
              <span className="text-muted-foreground">°C</span>
            </div>
          ) : (
            <>
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
            </>
          )}
          <div className="flex items-center gap-2 text-caption">
            <span className="w-20 text-muted-foreground">Tm tol ±</span>
            <input
              type="number"
              min={0.5}
              max={10.0}
              step={0.5}
              className={numInput}
              {...tmTolInput}
            />
            <span className="text-muted-foreground">°C</span>
            <HelpTip>Allowed deviation from Tm targets. Cascade stages add delta on top. Recommended 2-5°C.</HelpTip>
          </div>

          {/* GC */}
          <div className="flex items-center gap-1 pt-1.5 text-caption uppercase tracking-wider text-muted-foreground">
            GC%
            <InlineHelp text={"Recommended range: 40–60%.\nPrimers outside this range receive a penalty score.\nVery low GC (<30%) or very high GC (>70%) reduces synthesis quality."} />
          </div>
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

          {/* Primer Length — branches by strategy */}
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
            {primerLenEnabled && isFullOverlap && (
              <span className="flex items-center gap-1 ml-1" title="Single length range applies to both primers (rev = rc(fwd)).">
                <input type="number" className={numInput} {...fullLenMinInput} />
                <span className="text-muted-foreground">~</span>
                <input type="number" className={numInput} {...fullLenMaxInput} />
                <span className="text-caption text-muted-foreground">bp</span>
              </span>
            )}
            {primerLenEnabled && !isFullOverlap && (
              <span className="flex items-center gap-1 ml-1">
                <span className="text-muted-foreground">F</span>
                <input type="number" className={numInput} {...fwdLenMinInput} />
                <span className="text-muted-foreground">~</span>
                <input type="number" className={numInput} {...fwdLenMaxInput} />
              </span>
            )}
          </label>
          {primerLenEnabled && !isFullOverlap && (
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
          {primerLenEnabled && isFullOverlap && fwdLenMin >= fwdLenMax && (
            <div className="text-caption text-error pl-8">Min must be less than Max</div>
          )}

          {/* Design Behavior */}
          <div className="pt-1.5 text-caption uppercase tracking-wider text-muted-foreground">Design</div>
          <label className="flex items-center gap-1 text-caption cursor-pointer" title="When enabled, retries failed mutations through 4 (top-N) or 6 (pipeline) stages of relaxed parameters. When disabled, failed mutations remain as-is with no auto-retry.">
            <input
              type="checkbox"
              className="h-3 w-3 accent-primary"
              checked={fillOnFailure}
              onChange={(e) => setFillOnFailure(e.target.checked)}
            />
            <span className="text-muted-foreground">Auto-rescue failed mutations</span>
          </label>

          {/* §12 Random seed */}
          <div
            className="flex items-center gap-2 text-caption"
            title="Optional integer seed. Will be passed to the backend and recorded in run manifests once manifest wiring is complete (backend integration pending)."
          >
            <label
              htmlFor="random-seed-input"
              className="w-20 text-muted-foreground shrink-0"
            >
              Seed:
            </label>
            <input
              id="random-seed-input"
              type="number"
              min={0}
              step={1}
              placeholder="auto"
              aria-label="Random seed (optional)"
              aria-describedby="random-seed-hint"
              className={`${numInput} w-20`}
              value={seedStr}
              onChange={(e) => setSeedStr(e.target.value)}
              onBlur={() => {
                const trimmed = seedStrRef.current.trim();
                if (trimmed === "") {
                  setRandomSeed(null);
                } else {
                  const parsed = parseInt(trimmed, 10);
                  if (Number.isInteger(parsed) && parsed >= 0) {
                    setRandomSeed(parsed);
                  } else {
                    setSeedStr(randomSeed !== null ? String(randomSeed) : "");
                  }
                }
              }}
              onKeyDown={(e) => { if (e.key === "Enter") e.currentTarget.blur(); }}
            />
            <span id="random-seed-hint" className="text-caption text-muted-foreground">
              {randomSeed !== null ? `fixed: ${randomSeed}` : "auto"}
            </span>
          </div>
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
