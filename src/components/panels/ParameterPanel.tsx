import { useEffect, useRef, useState, type ChangeEvent, type KeyboardEvent } from "react";
import { useTranslation } from "react-i18next";
import { sendRequest } from "../../lib/ipc-kuro";
import { formatError } from "../../lib/utils";
import type { CodonStrategy, OverlapMode, PolymeraseProfile } from "../../types/models";
import { PolymeraseEditor } from "../dialogs/PolymeraseEditor";
import { EnzymeEditor } from "../dialogs/EnzymeEditor";
import { Button } from "../ui/button";
import { HelpTip } from "./InputPanel/DiversitySections";
import { InlineHelp } from "../ui/InlineHelp";
import { AdvancedSection } from "../ui/AdvancedSection";
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
  const { t } = useTranslation();
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
  const isEvolvepro = mutationInputMode === "evolvepro";
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
  const designMethod = useAppStore((s) => s.designMethod);
  const enzyme = useAppStore((s) => s.enzyme);
  const setDesignMethod = useAppStore((s) => s.setDesignMethod);
  const setEnzyme = useAppStore((s) => s.setEnzyme);
  const typeiisEnzymes = useAppStore((s) => s.typeiisEnzymes);
  const saveCustomEnzyme = useAppStore((s) => s.saveCustomEnzyme);
  const prefixOverride = useAppStore((s) => s.prefixOverride);
  const setPrefixOverride = useAppStore((s) => s.setPrefixOverride);
  const forbiddenOverhangs = useAppStore((s) => s.forbiddenOverhangs);
  const setForbiddenOverhangs = useAppStore((s) => s.setForbiddenOverhangs);
  const randomSeed = useAppStore((s) => s.randomSeed);
  const setRandomSeed = useAppStore((s) => s.setRandomSeed);
  const setStatus = useAppStore((s) => s.setStatus);

  const [showAdvanced, setShowAdvanced] = useState(false);
  const [polymeraseEditorOpen, setPolymeraseEditorOpen] = useState(false);
  const [enzymeEditorOpen, setEnzymeEditorOpen] = useState(false);
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
  const selectedEnzyme = typeiisEnzymes.find((ez) => ez.name === enzyme) ?? null;
  const isGoldenGate = designMethod === "goldengate";
  const methodSelectValue = isGoldenGate ? `gg:${enzyme}` : `overlap:${overlapMode}`;
  const onMethodSelectChange = (e: ChangeEvent<HTMLSelectElement>) => {
    const [prefix, rest] = e.target.value.split(":");
    if (prefix === "gg") {
      setDesignMethod("goldengate");
      setEnzyme(rest);
    } else if (prefix === "overlap" && isOverlapMode(rest)) {
      setDesignMethod("overlap");
      setOverlapMode(rest);
    }
  };

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
        <div className="text-caption font-semibold uppercase tracking-widest text-muted-foreground">{t("parameterPanel.sectionLabel")}</div>
        <h3 className="text-title font-semibold text-foreground">{t("parameterPanel.title")}</h3>
      </div>

      {/* Strategy — top-level switch that changes the meaning of parameters below */}
      <div className="space-y-1">
        <label
          htmlFor="design-strategy-select"
          className="flex items-center gap-2 text-caption"
        >
          <span className="w-24 text-muted-foreground">{t("parameterPanel.designMethodLabel")}</span>
          <InlineHelp text={t("parameterPanel.designMethodHelp")} />
          <select
            id="design-strategy-select"
            className="h-control min-w-0 flex-1 rounded-control border border-border bg-card px-3 text-caption focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
            value={methodSelectValue}
            onChange={onMethodSelectChange}
            aria-describedby="design-strategy-hint"
          >
            <optgroup label={t("parameterPanel.methodGroup_overlap")}>
              <option value="overlap:partial" title={t("parameterPanel.strategyOption_partial_title")}>{t("parameterPanel.strategyOption_partial")}</option>
              <option value="overlap:full" title={t("parameterPanel.strategyOption_full_title")}>{t("parameterPanel.strategyOption_full")}</option>
            </optgroup>
            <optgroup label={t("parameterPanel.methodGroup_goldengate")}>
              {typeiisEnzymes.map((ez) => (
                <option
                  key={ez.name}
                  value={`gg:${ez.name}`}
                  title={t("parameterPanel.enzymeOptionTitle", {
                    recognition: ez.recognition,
                    cutTop: ez.cut_offset[0],
                    cutBottom: ez.cut_offset[1],
                    overhang: ez.overhang_len,
                  })}
                >
                  {ez.name} — {ez.recognition} ({ez.cut_offset[0]}/{ez.cut_offset[1]}, {ez.overhang_len} nt)
                </option>
              ))}
            </optgroup>
          </select>
        </label>
        <p id="design-strategy-hint" className="pl-26 text-caption text-muted-foreground">
          {isGoldenGate
            ? selectedEnzyme
              ? t("parameterPanel.methodHint_goldengateEnzyme", {
                  enzyme,
                  recognition: selectedEnzyme.recognition,
                  cutTop: selectedEnzyme.cut_offset[0],
                  cutBottom: selectedEnzyme.cut_offset[1],
                  overhang: selectedEnzyme.overhang_len,
                })
              : t("parameterPanel.methodHint_goldengate", { enzyme })
            : isFullOverlap
              ? t("parameterPanel.strategyHint_full")
              : t("parameterPanel.strategyHint_partial")}
        </p>
        {isGoldenGate && (
          <div className="flex justify-end">
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-control rounded-control"
              onClick={() => setEnzymeEditorOpen(true)}
            >
              {t("parameterPanel.customEnzyme")}
            </Button>
          </div>
        )}
      </div>

      <div className="space-y-1">
        <label htmlFor="polymerase-select" className="flex items-center gap-2 text-caption">
          <span className="w-24 text-muted-foreground">{t("parameterPanel.polymeraseLabel")}</span>
          <InlineHelp text={t("parameterPanel.polymeraseHelp")} />
          <select
            id="polymerase-select"
            className="h-control min-w-0 flex-1 rounded-control border border-border bg-card px-3 text-caption focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:opacity-60"
            value={polymerases.length === 0 ? "" : selectedPolymerase}
            disabled={polymerases.length === 0}
            onChange={(e) => void setSelectedPolymerase(e.target.value)}
          >
            {polymerases.length === 0 ? (
              // i18n note: hardcoded English placeholder; locale fanout deferred.
              <option value="" disabled>
                Loading polymerase profiles…
              </option>
            ) : (
              polymerases.map((poly) => {
                const parts = [
                  poly.manufacturer ? t("parameterPanel.polymeraseManufacturer", { manufacturer: poly.manufacturer }) : "",
                  poly.fidelity ? t("parameterPanel.polymeraseFidelity", { fidelity: poly.fidelity }) : "",
                ].filter(Boolean);
                return (
                  <option
                    key={poly.name}
                    value={poly.name}
                    title={parts.length ? `${poly.name} — ${parts.join(", ")}` : poly.name}
                  >
                    {poly.name}
                    {poly.manufacturer ? ` (${poly.manufacturer})` : ""}
                  </option>
                );
              })
            )}
          </select>
        </label>
        <div className="flex justify-end">
          <Button type="button" variant="outline" size="sm" className="h-control rounded-control" onClick={() => void openCustomEditor()}>
            {t("parameterPanel.customPolymerase")}
          </Button>
        </div>
      </div>

      <label htmlFor="codon-strategy" className="flex items-center gap-2 text-caption">
        <span className="w-24 text-muted-foreground">{t("parameterPanel.codonLabel")}</span>
        <InlineHelp text={t("parameterPanel.codonHelp")} />
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
          <option value="closest" title={t("parameterPanel.codonOption_closest_title")}>{t("parameterPanel.codonOption_closest")}</option>
          <option value="optimal" title={t("parameterPanel.codonOption_optimal_title")}>{t("parameterPanel.codonOption_optimal")}</option>
        </select>
      </label>

      <label className="flex items-center gap-2 text-caption">
        <span className="w-24 text-muted-foreground">{t("parameterPanel.mutationsLabel")}</span>
        <InlineHelp text={t("parameterPanel.mutationsHelp")} />
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
          {t("parameterPanel.plates", { count: Math.ceil(maxPrimers / 96) })}
        </span>
      </label>
      {overLimit && (
        <div className="text-caption text-warning pl-26">
          {t("parameterPanel.csvVariantWarning", { count: evolveproTotalCount })}
        </div>
      )}

      {/* Advanced Options */}
      <AdvancedSection
        title={t("parameterPanel.advancedToggleShow")}
        open={showAdvanced}
        onToggle={() => setShowAdvanced(!showAdvanced)}
        id="kuro-params-advanced"
      >
        <div className="space-y-1">
          {/* Tm — branches by strategy */}
          {isGoldenGate && (
            <>
              <p className="text-caption text-muted-foreground">{t("parameterPanel.goldenGateAdvancedNote")}</p>
              <div className="pt-0.5 text-caption uppercase tracking-wider text-muted-foreground">
                <span className="inline-flex items-center gap-1.5">
                  {t("parameterPanel.junctionSectionLabel")}
                  <InlineHelp text={t("parameterPanel.junctionSectionHelp")} />
                </span>
              </div>
              <label className="flex items-center gap-2 text-caption">
                <span className="w-24 text-muted-foreground shrink-0">{t("parameterPanel.prefixOverrideLabel")}</span>
                <input
                  type="text"
                  className="h-control min-w-0 flex-1 rounded-control border border-border bg-card px-2 text-caption focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  value={prefixOverride}
                  placeholder={selectedEnzyme?.recognition ? `${selectedEnzyme.name}: catalog prefix` : t("parameterPanel.prefixOverridePlaceholder")}
                  onChange={(e) => setPrefixOverride(e.target.value)}
                />
                <InlineHelp text={t("parameterPanel.prefixOverrideHelp")} />
              </label>
              <label className="flex items-center gap-2 text-caption">
                <span className="w-24 text-muted-foreground shrink-0">{t("parameterPanel.forbiddenOverhangsLabel")}</span>
                <input
                  type="text"
                  className="h-control min-w-0 flex-1 rounded-control border border-border bg-card px-2 text-caption focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  value={forbiddenOverhangs}
                  placeholder="AATG, AGGT"
                  onChange={(e) => setForbiddenOverhangs(e.target.value)}
                />
                <InlineHelp text={t("parameterPanel.forbiddenOverhangsHelp")} />
              </label>
            </>
          )}
          {!isGoldenGate && (
            <>
          <div className="pt-0.5 text-caption uppercase tracking-wider text-muted-foreground" title={t("parameterPanel.tmSectionTitle")}>
            <span className="inline-flex items-center gap-1.5">
              {t("parameterPanel.tmSectionLabel")}
              <InlineHelp text={t("parameterPanel.tmSectionHelp")} />
            </span>
          </div>
          {isFullOverlap ? (
            <div className="flex items-center gap-2 text-caption" title={t("parameterPanel.tmPrimerTitle")}>
              <span className="w-20 text-muted-foreground">{t("parameterPanel.tmPrimerLabel")}</span>
              <input type="number" className={numInput} {...tmFwdInput} />
              <span className="text-muted-foreground">°C</span>
              <InlineHelp text={t("parameterPanel.tmPrimerHelp")} />
            </div>
          ) : (
            <>
              <div className="flex items-center gap-2 text-caption" title={t("parameterPanel.tmSectionTitle")}>
                <span className="w-20 text-muted-foreground">{t("parameterPanel.tmFwdLabel")}</span>
                <input type="number" className={numInput} {...tmFwdInput} />
                <span className="text-muted-foreground">°C</span>
                <InlineHelp text={t("parameterPanel.tmFwdHelp")} />
              </div>
              <div className="flex items-center gap-2 text-caption" title={t("parameterPanel.tmSectionTitle")}>
                <span className="w-20 text-muted-foreground">{t("parameterPanel.tmRevLabel")}</span>
                <input type="number" className={numInput} {...tmRevInput} />
                <span className="text-muted-foreground">°C</span>
                <InlineHelp text={t("parameterPanel.tmRevHelp")} />
              </div>
              <div className="flex items-center gap-2 text-caption" title={t("parameterPanel.tmSectionTitle")}>
                <span className="w-20 text-muted-foreground">{t("parameterPanel.tmOverlapLabel")}</span>
                <input type="number" className={numInput} {...tmOvInput} />
                <span className="text-muted-foreground">°C</span>
                <InlineHelp text={t("parameterPanel.tmOverlapHelp")} />
              </div>
            </>
          )}
          <div className="flex items-center gap-2 text-caption">
            <span className="w-20 text-muted-foreground">{t("parameterPanel.tmTolLabel")}</span>
            <input
              type="number"
              min={0.5}
              max={10.0}
              step={0.5}
              className={numInput}
              {...tmTolInput}
            />
            <span className="text-muted-foreground">°C</span>
            <HelpTip>{t("parameterPanel.tmTolHelp")}</HelpTip>
          </div>

          {/* GC */}
          <div className="flex items-center gap-1 pt-1.5 text-caption uppercase tracking-wider text-muted-foreground">
            {t("parameterPanel.gcSectionLabel")}
            <InlineHelp text={t("parameterPanel.gcHelp")} />
          </div>
          <div className="flex items-center gap-2 text-caption" title={t("parameterPanel.gcRangeTitle")}>
            <span className="w-20 text-muted-foreground">{t("parameterPanel.gcRangeLabel")}</span>
            <input type="number"
              className={`${gcInputBase} ${gcInvalid ? "border-error focus:ring-error" : "border-border"}`}
              {...gcMinInput} />
            <span className="text-muted-foreground">~</span>
            <input type="number"
              className={`${gcInputBase} ${gcInvalid ? "border-error focus:ring-error" : "border-border"}`}
              {...gcMaxInput} />
            <span className="text-muted-foreground">%</span>
            <InlineHelp text={t("parameterPanel.gcRangeHelp")} />
          </div>
          {gcInvalid && (
            <div className="text-caption text-error pl-20">{t("parameterPanel.gcInvalidError")}</div>
          )}

          {/* Primer Length — branches by strategy */}
          <div className="flex items-center gap-1 pt-1.5 text-caption uppercase tracking-wider text-muted-foreground">
            {t("parameterPanel.primerLenSectionLabel")}
            <HelpTip>{t("parameterPanel.primerLenHelp")}</HelpTip>
          </div>
          <label className="flex items-center gap-1 text-caption cursor-pointer">
            <input
              type="checkbox"
              className="h-3 w-3 accent-primary"
              checked={primerLenEnabled}
              onChange={(e) => setPrimerLenEnabled(e.target.checked)}
            />
            <span className="text-muted-foreground">{t("parameterPanel.primerLenLimit")}</span>
            <InlineHelp text={t("parameterPanel.primerLenLimitHelp")} />
            {primerLenEnabled && isFullOverlap && (
              <span className="flex items-center gap-1 ml-1" title={t("parameterPanel.primerLenSingleTitle")}>
                <input type="number" className={numInput} {...fullLenMinInput} />
                <span className="text-muted-foreground">~</span>
                <input type="number" className={numInput} {...fullLenMaxInput} />
                <span className="text-caption text-muted-foreground">bp</span>
              </span>
            )}
            {primerLenEnabled && !isFullOverlap && (
              <span className="flex items-center gap-1 ml-1">
                <span className="text-muted-foreground">{t("parameterPanel.primerLenFwdLabel")}</span>
                <input type="number" className={numInput} {...fwdLenMinInput} />
                <span className="text-muted-foreground">~</span>
                <input type="number" className={numInput} {...fwdLenMaxInput} />
                <InlineHelp text={t("parameterPanel.primerLenFwdHelp")} />
              </span>
            )}
          </label>
          {primerLenEnabled && !isFullOverlap && (
            <>
              <div className="flex items-center gap-1 text-caption pl-4">
                <span className="ml-3 text-muted-foreground">{t("parameterPanel.primerLenRevLabel")}</span>
                <input type="number" className={numInput} {...revLenMinInput} />
                <span className="text-muted-foreground">~</span>
                <input type="number" className={numInput} {...revLenMaxInput} />
                <span className="text-caption text-muted-foreground">bp</span>
                <InlineHelp text={t("parameterPanel.primerLenRevHelp")} />
              </div>
              {(fwdLenMin >= fwdLenMax || revLenMin >= revLenMax) && (
                <div className="text-caption text-error pl-8">{t("parameterPanel.primerLenInvalidError")}</div>
              )}
            </>
          )}
          {primerLenEnabled && isFullOverlap && fwdLenMin >= fwdLenMax && (
            <div className="text-caption text-error pl-8">{t("parameterPanel.primerLenInvalidError")}</div>
          )}
            </>
          )}

          {/* Design Behavior */}
          <div className="pt-1.5 text-caption uppercase tracking-wider text-muted-foreground">{t("parameterPanel.designSectionLabel")}</div>
          <label className="flex items-center gap-1 text-caption cursor-pointer" title={t("parameterPanel.autoRescueTitle")}>
            <input
              type="checkbox"
              className="h-3 w-3 accent-primary"
              checked={fillOnFailure}
              onChange={(e) => setFillOnFailure(e.target.checked)}
            />
            <span className="text-muted-foreground">{t("parameterPanel.autoRescueLabel")}</span>
            <InlineHelp text={t("parameterPanel.autoRescueHelp")} />
          </label>

          {/* §12 Random seed */}
          <div
            className="flex items-center gap-2 text-caption"
            title={t("parameterPanel.seedTitle")}
          >
            <label
              htmlFor="random-seed-input"
              className="w-20 text-muted-foreground shrink-0"
            >
              {t("parameterPanel.seedLabel")}
            </label>
            <input
              id="random-seed-input"
              type="number"
              min={0}
              step={1}
              placeholder={t("parameterPanel.seedAuto")}
              aria-label={t("parameterPanel.seedAriaLabel")}
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
              {randomSeed !== null ? t("parameterPanel.seedFixed", { seed: randomSeed }) : t("parameterPanel.seedAuto")}
            </span>
            <InlineHelp text={t("parameterPanel.seedHelp")} />
          </div>
        </div>
      </AdvancedSection>

      <PolymeraseEditor
        open={polymeraseEditorOpen}
        profile={editingPolymerase}
        onOpenChange={setPolymeraseEditorOpen}
        onSave={saveCustomPolymerase}
      />

      <EnzymeEditor
        open={enzymeEditorOpen}
        onOpenChange={setEnzymeEditorOpen}
        onSave={saveCustomEnzyme}
      />
    </section>
  );
}
