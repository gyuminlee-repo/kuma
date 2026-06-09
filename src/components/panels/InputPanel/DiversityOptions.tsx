import { useMemo, useState, type KeyboardEvent } from "react";
import { useTranslation } from "react-i18next";
import { useAppStore } from "../../../store/appStore";
import {
  AdvancedSettingsSection,
  BenchmarkSection,
  DomainAllocationSection,
  OptimizationSummarySection,
  PipelineArrow,
  PipelineStep,
  RoundSettingsSection,
  WorkspaceSection,
} from "./DiversitySections";

function computeSigmaParams(round: number, size: number): { k: number; ew: number } {
  const cum = round * size;
  if (cum <= 96) return { k: 0.5, ew: 0.3 };
  if (cum <= 192) return { k: 0.4, ew: 0.25 };
  if (cum <= 384) return { k: 0.3, ew: 0.2 };
  return { k: 0.25, ew: 0.15 };
}

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
  const evolveproExtraExposed = useAppStore((s) => s.evolveproExtraExposed);
  const setEvolveproExtraExposed = useAppStore((s) => s.setEvolveproExtraExposed);
  const evolveproRankedCandidates = useAppStore((s) => s.evolveproRankedCandidates);
  const mutationInputMode = useAppStore((s) => s.mutationInputMode);

  const selectedCount = useMemo(
    () => mutationText.split("\n").filter((l) => l.trim() && !l.trim().startsWith("#")).length,
    [mutationText],
  );

  const { t } = useTranslation();
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [addingDomain, setAddingDomain] = useState(false);
  const [newDomainName, setNewDomainName] = useState("");
  const [newDomainStart, setNewDomainStart] = useState("");
  const [newDomainEnd, setNewDomainEnd] = useState("");
  const [maxPerPosStr, setMaxPerPosStr] = useState(String(maxPerPosition));
  const [roundStr, setRoundStr] = useState(String(evolveproRound));
  const [roundSizeStr, setRoundSizeStr] = useState(String(roundSize));
  const [extraExposedStr, setExtraExposedStr] = useState(String(evolveproExtraExposed));

  const commitMaxPerPos = () => {
    const n = parseInt(maxPerPosStr, 10);
    if (isFinite(n) && n >= 1) setMaxPerPosition(n);
  };

  const commitRound = () => {
    const n = parseInt(roundStr, 10);
    if (isFinite(n) && n >= 1) setEvolveproRound(n);
  };

  const commitRoundSize = () => {
    const n = parseInt(roundSizeStr, 10);
    if (isFinite(n) && n >= 1) setRoundSize(n);
  };

  const commitExtraExposed = () => {
    const n = parseInt(extraExposedStr, 10);
    if (isFinite(n) && n >= 0) setEvolveproExtraExposed(n);
  };

  const onEnterBlur = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") e.currentTarget.blur();
  };

  const autoParams = computeSigmaParams(evolveproRound, roundSize);

  const distanceBadge =
    distanceMode === "1d"
      ? "position distance"
      : distanceMode === "3d"
        ? "AlphaFold 3D"
        : structureLoaded
          ? "AlphaFold 3D"
          : "position distance";

  return (
    <div className="relative ml-1 rounded-container border border-border bg-card p-3">
      <div className="mb-1.5 text-caption font-semibold uppercase tracking-wide text-muted-foreground">
        Pipeline
      </div>

      <div className="ml-2 space-y-2 border-l-2 border-border pl-3">
        <PipelineStep
          step={1}
          label="Pre-filter"
          enabled={positionDiversityEnabled}
          onToggle={setPositionDiversityEnabled}
        />

        <PipelineArrow active={positionDiversityEnabled} />

        <PipelineStep
          step={2}
          label="Domain allocation"
          enabled={domainDiversityEnabled}
          onToggle={setDomainDiversityEnabled}
        >
          <DomainAllocationSection
            linkerHandling={linkerHandling}
            setLinkerHandling={setLinkerHandling}
            domains={domains}
            disabledDomains={disabledDomains}
            domainStats={domainStats}
            toggleDomain={toggleDomain}
            addingDomain={addingDomain}
            setAddingDomain={setAddingDomain}
            newDomainName={newDomainName}
            setNewDomainName={setNewDomainName}
            newDomainStart={newDomainStart}
            setNewDomainStart={setNewDomainStart}
            newDomainEnd={newDomainEnd}
            setNewDomainEnd={setNewDomainEnd}
            setDomains={setDomains}
          />
        </PipelineStep>

        <PipelineArrow active={domainDiversityEnabled} />

        <PipelineStep
          step={3}
          label="Optimization"
          enabled={paretoDiversityEnabled}
          onToggle={setParetoDiversityEnabled}
        >
          <OptimizationSummarySection
            distanceBadge={distanceBadge}
            structureLoading={structureLoading}
            structureLoaded={structureLoaded}
            distanceMode={distanceMode}
          />
        </PipelineStep>
      </div>

      <RoundSettingsSection
        roundStr={roundStr}
        setRoundStr={setRoundStr}
        roundSizeStr={roundSizeStr}
        setRoundSizeStr={setRoundSizeStr}
        commitRound={commitRound}
        commitRoundSize={commitRoundSize}
        onEnterBlur={onEnterBlur}
        autoK={autoParams.k}
        autoEntropy={autoParams.ew}
      />

      <AdvancedSettingsSection
        showAdvanced={showAdvanced}
        setShowAdvanced={setShowAdvanced}
        maxPerPosStr={maxPerPosStr}
        setMaxPerPosStr={setMaxPerPosStr}
        commitMaxPerPos={commitMaxPerPos}
        onEnterBlur={onEnterBlur}
        domainStrategy={domainStrategy}
        setDomainStrategy={setDomainStrategy}
        domainOverlapPolicy={domainOverlapPolicy}
        setDomainOverlapPolicy={setDomainOverlapPolicy}
        domainQuotaMin={domainQuotaMin}
        setDomainQuotaMin={setDomainQuotaMin}
        distanceMode={distanceMode}
        setDistanceMode={setDistanceMode}
        paretoPoolMultiplier={paretoPoolMultiplier}
        setParetoPoolMultiplier={setParetoPoolMultiplier}
        autoK={autoParams.k}
        entropyWeightEnabled={entropyWeightEnabled}
        setEntropyWeightEnabled={setEntropyWeightEnabled}
        autoEntropy={autoParams.ew}
        entropyWeight={entropyWeight}
        setEntropyWeight={setEntropyWeight}
      />

      {mutationInputMode === "evolvepro" && evolveproRankedCandidates.length > 0 && (
        <div className="mt-2 flex items-center gap-2 text-xs text-muted-foreground">
          <label htmlFor="extra-exposed-input" className="shrink-0">
            {t("mutationInput.extraExposedLabel")}
          </label>
          <input
            id="extra-exposed-input"
            type="number"
            min={0}
            max={evolveproRankedCandidates.length}
            value={extraExposedStr}
            onChange={(e) => setExtraExposedStr(e.target.value)}
            onBlur={commitExtraExposed}
            onKeyDown={(e) => { if (e.key === "Enter") e.currentTarget.blur(); }}
            className="w-16 rounded border border-border bg-card px-1.5 py-0.5 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
            aria-label={t("mutationInput.extraExposedAriaLabel")}
          />
          <span className="text-caption">
            {t("mutationInput.extraExposedHint")}
          </span>
        </div>
      )}
      <div className="ml-2 mt-2 border-l-2 border-transparent pl-3 text-xs font-medium text-foreground">
        <span className="mr-1.5 inline-block h-1.5 w-1.5 -translate-y-px rounded-full bg-emerald-500" />
        {selectedCount} variants selected
      </div>

      <WorkspaceSection
        autoRedesignOnLoad={autoRedesignOnLoad}
        setAutoRedesignOnLoad={setAutoRedesignOnLoad}
        saveCache={saveCache}
        setSaveCache={setSaveCache}
      />

      <BenchmarkSection
        benchmarkTopPercentile={benchmarkTopPercentile}
        setBenchmarkTopPercentile={setBenchmarkTopPercentile}
        benchmarkRandomTrials={benchmarkRandomTrials}
        setBenchmarkRandomTrials={setBenchmarkRandomTrials}
        benchmarkRandomSeed={benchmarkRandomSeed}
        setBenchmarkRandomSeed={setBenchmarkRandomSeed}
        benchmarkRunning={benchmarkRunning}
        runBenchmark={runBenchmark}
        hasBenchmarkData={Object.keys(yPredMap).length > 0}
      />
    </div>
  );
}
