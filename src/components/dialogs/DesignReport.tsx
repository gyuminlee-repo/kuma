import { useShallow } from "zustand/react/shallow";
import { useAppStore } from "../../store/appStore";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "../ui/dialog";
import { Button } from "../ui/button";

function Stat({ label, value, warn }: { label: string; value: string | number; warn?: boolean }) {
  return (
    <div className="flex justify-between text-xs">
      <span className="text-gray-500">{label}</span>
      <span className={warn ? "text-amber-600 font-medium" : "text-gray-800 font-medium"}>{value}</span>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <h4 className="text-xs font-semibold text-gray-700 uppercase tracking-wide">{title}</h4>
      <div className="bg-gray-50 rounded-md p-2 space-y-0.5">{children}</div>
    </div>
  );
}

function formatDomainAllocation(
  enabled: boolean,
  domains: Array<{ name: string }>,
  domainStats: Record<string, { quota: number; selected: number }>,
  domainStrategy: "proportional" | "equal",
): string {
  if (!enabled || domains.length === 0) return "OFF";
  const total = Object.values(domainStats).reduce((sum, stat) => sum + stat.selected, 0);
  const quota = Object.values(domainStats).reduce((sum, stat) => sum + stat.quota, 0);
  return quota > 0 ? `${domainStrategy}: ${total}/${quota}` : `${domainStrategy} (${domains.length} domains)`;
}

export function DesignReport() {
  const setShowReport = useAppStore((s) => s.setShowReport);
  const data = useAppStore(
    useShallow((s) => {
      if (!s.showReport) return null;
      return {
        showReport: s.showReport,
        designResults: s.designResults,
        failedMutations: s.failedMutations,
        totalCount: s.totalCount,
        pipelineMode: s.pipelineMode,
        positionDiversityEnabled: s.positionDiversityEnabled,
        maxPerPosition: s.maxPerPosition,
        domainDiversityEnabled: s.domainDiversityEnabled,
        domainStrategy: s.domainStrategy,
        domainOverlapPolicy: s.domainOverlapPolicy,
        linkerHandling: s.linkerHandling,
        domainQuotaMin: s.domainQuotaMin,
        domains: s.domains,
        domainStats: s.domainStats,
        paretoDiversityEnabled: s.paretoDiversityEnabled,
        entropyWeightEnabled: s.entropyWeightEnabled,
        entropyWeight: s.entropyWeight,
        paretoPoolMultiplier: s.paretoPoolMultiplier,
        distanceMode: s.distanceMode,
        benchmarkTopPercentile: s.benchmarkTopPercentile,
        benchmarkRandomTrials: s.benchmarkRandomTrials,
        benchmarkRandomSeed: s.benchmarkRandomSeed,
        structureLoaded: s.structureLoaded,
        evolveproTotalCount: s.evolveproTotalCount,
        evolveproFilteredCount: s.evolveproFilteredCount,
        evolveproParetoExchanges: s.evolveproParetoExchanges,
        evolveproStepStats: s.evolveproStepStats,
        mutationInputMode: s.mutationInputMode,
        rescueStats: s.rescueStats,
        rescuedMutationDetails: s.rescuedMutationDetails,
      };
    }),
  );

  if (!data || data.designResults.length === 0) return null;

  const {
    showReport,
    designResults,
    failedMutations,
    totalCount,
    pipelineMode,
    positionDiversityEnabled,
    maxPerPosition,
    domainDiversityEnabled,
    domainStrategy,
    domainOverlapPolicy,
    linkerHandling,
    domainQuotaMin,
    domains,
    domainStats,
    paretoDiversityEnabled,
    entropyWeightEnabled,
    entropyWeight,
    paretoPoolMultiplier,
    distanceMode,
    benchmarkTopPercentile,
    benchmarkRandomTrials,
    benchmarkRandomSeed,
    structureLoaded,
    evolveproTotalCount,
    evolveproFilteredCount,
    evolveproParetoExchanges,
    evolveproStepStats,
    mutationInputMode,
    rescueStats,
    rescuedMutationDetails,
  } = data;

  const successCount = designResults.length;
  const failCount = failedMutations.length;
  const successRate = totalCount > 0 ? Math.round((successCount / totalCount) * 100) : 0;

  // Tm statistics
  const fwdTms = designResults.map((r) => r.tm_no_fwd).filter((t) => t > 0);
  const revTms = designResults.map((r) => r.tm_no_rev).filter((t) => t > 0);
  const ovTms = designResults.map((r) => r.tm_overlap).filter((t) => t > 0);
  const avg = (arr: number[]) => arr.length > 0 ? arr.reduce((a, b) => a + b, 0) / arr.length : 0;
  const std = (arr: number[]) => {
    if (arr.length < 2) return 0;
    const m = avg(arr);
    return Math.sqrt(arr.reduce((s, v) => s + (v - m) ** 2, 0) / (arr.length - 1));
  };

  const tmMet = designResults.filter((r) => r.tm_condition_met).length;
  const positionRemoved = evolveproStepStats?.position_filter_removed ?? evolveproFilteredCount;
  const domainSelected = evolveproStepStats?.domain_selected;

  const rescueTotal = rescueStats.pool_cascade + rescueStats.auto_relax;
  const rescuePenalties = rescuedMutationDetails
    .map((r) => r.penalty).filter((p): p is number => p != null);
  const avgRescuePenalty = avg(rescuePenalties);
  const rescuedSet = new Set(rescuedMutationDetails.map((d) => d.rescued_by));
  const avgNormalPenalty = avg(
    designResults.filter((r) => !rescuedSet.has(r.mutation)).map((r) => r.penalty),
  );
  const paretoExchanges = evolveproStepStats?.pareto_exchanges ?? evolveproParetoExchanges;

  return (
    <Dialog open={showReport} onOpenChange={setShowReport}>
      <DialogContent className="max-w-md max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <span className="text-lg">Design Report</span>
          </DialogTitle>
          <DialogDescription>
            {successCount}/{totalCount} primers designed ({successRate}% success)
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          {/* Pipeline Summary */}
          {pipelineMode && (
            <Section title="Pipeline">
              <Stat
                label="Step 1 filter"
                value={
                  positionDiversityEnabled
                    ? `max ${maxPerPosition}/pos${positionRemoved != null && positionRemoved > 0 ? ` (−${positionRemoved})` : ""}`
                    : "OFF"
                }
              />
              <Stat
                label="Step 2 domains"
                value={formatDomainAllocation(domainDiversityEnabled, domains, domainStats, domainStrategy)}
              />
              {domainDiversityEnabled && (
                <Stat label="Step 2 overlap" value={domainOverlapPolicy === "largest" ? "LARGEST" : "FIRST"} />
              )}
              {domainDiversityEnabled && (
                <Stat label="Step 2 linker" value={linkerHandling.toUpperCase()} />
              )}
              {domainDiversityEnabled && (
                <Stat label="Step 2 min quota" value={domainQuotaMin} />
              )}
              <Stat
                label="Step 3 Pareto"
                value={
                  paretoDiversityEnabled
                    ? `ON${paretoExchanges != null && paretoExchanges > 0 ? ` (${paretoExchanges} swapped)` : ""}`
                    : "OFF"
                }
              />
              <Stat label="Distance mode" value={distanceMode === "auto" ? (structureLoaded ? "AUTO -> 3D" : "AUTO -> 1D") : distanceMode.toUpperCase()} />
              <Stat label="Pareto pool" value={`${paretoPoolMultiplier.toFixed(2)}x`} />
              <Stat label="Entropy-guided" value={entropyWeightEnabled ? `ON (${entropyWeight.toFixed(2)})` : "OFF"} />
              <Stat label="AlphaFold 3D" value={structureLoaded ? "ON (Cα distance)" : "OFF (1D distance)"} />
              {positionRemoved != null && positionDiversityEnabled && (
                <Stat label="Removed by Step 1" value={positionRemoved} />
              )}
              {domainSelected != null && domainDiversityEnabled && (
                <Stat label="After Step 2" value={domainSelected} />
              )}
              {paretoExchanges != null && paretoDiversityEnabled && (
                <Stat label="Step 3 exchanges" value={paretoExchanges} />
              )}
              {evolveproTotalCount > 0 && (
                <Stat label={mutationInputMode === "multi-evolve" ? "MULTI-evolve pool" : "EVOLVEpro pool"} value={`${evolveproTotalCount} variants`} />
              )}
            </Section>
          )}

          <Section title="Benchmark Defaults">
            <Stat label="Top percentile" value={`${benchmarkTopPercentile}%`} />
            <Stat label="Random trials" value={benchmarkRandomTrials} />
            <Stat label="Random seed" value={benchmarkRandomSeed ?? "AUTO"} />
          </Section>

          {/* Primer Design Results */}
          <Section title="Primer Design">
            <Stat label="Succeeded" value={`${successCount}/${totalCount}`} />
            <Stat label="Tm condition met" value={`${tmMet}/${successCount}`} warn={tmMet < successCount} />
            {failCount > 0 && <Stat label="Failed" value={failCount} warn />}
          </Section>

          {/* Position Rescue */}
          {rescueTotal > 0 && (
            <Section title="Position Rescue">
              <Stat
                label="Position coverage"
                value={rescueStats.positions_attempted > 0
                  ? `${rescueTotal}/${rescueStats.positions_attempted} rescued`
                  : "0"}
              />
              {rescueStats.pool_cascade > 0 && (
                <Stat label="Pool cascade" value={`${rescueStats.pool_cascade} (${rescueStats.pool_variants_tried} tried)`} />
              )}
              {rescueStats.auto_relax > 0 && (
                <Stat label="Auto-relax (\u00B13\u2192\u00B15\u00B0C)" value={rescueStats.auto_relax} />
              )}
              {failCount > 0 && (
                <Stat label="Still failed" value={failCount} warn />
              )}
              {rescuePenalties.length > 0 && (
                <Stat
                  label="Rescued avg penalty"
                  value={`${avgRescuePenalty.toFixed(1)} vs ${avgNormalPenalty.toFixed(1)} normal`}
                  warn={avgRescuePenalty > avgNormalPenalty * 1.5}
                />
              )}
              {rescuedMutationDetails.length > 0 && (
                <div className="text-xs text-gray-600 space-y-0.5 mt-1">
                  {rescuedMutationDetails.slice(0, 5).map((r, i) => (
                    <div key={i} className="flex justify-between">
                      <span className="font-mono">
                        {r.type === "pool_cascade"
                          ? `${r.original} \u2192 ${r.rescued_by}`
                          : r.original}
                      </span>
                      <span className={r.type === "pool_cascade" ? "text-green-600" : "text-amber-600"}>
                        {r.type === "pool_cascade" ? "\u21BB cascade" : "\u26A1 relaxed"}
                        {r.penalty != null && ` (${r.penalty.toFixed(1)})`}
                      </span>
                    </div>
                  ))}
                  {rescuedMutationDetails.length > 5 && (
                    <div className="text-gray-400">+{rescuedMutationDetails.length - 5} more</div>
                  )}
                </div>
              )}
            </Section>
          )}

          {/* Tm Distribution */}
          {fwdTms.length > 0 && (
            <Section title="Tm Distribution">
              <Stat label="Forward" value={`${avg(fwdTms).toFixed(1)} \u00b1 ${std(fwdTms).toFixed(1)} \u00b0C`} />
              <Stat label="Reverse" value={`${avg(revTms).toFixed(1)} \u00b1 ${std(revTms).toFixed(1)} \u00b0C`} />
              <Stat label="Overlap" value={`${avg(ovTms).toFixed(1)} \u00b1 ${std(ovTms).toFixed(1)} \u00b0C`} />
            </Section>
          )}

          {/* Domain Stats */}
          {Object.keys(domainStats).length > 0 && (
            <Section title="Domain Allocation">
              {Object.entries(domainStats).map(([name, stat]) => (
                <Stat
                  key={name}
                  label={name}
                  value={`${stat.selected}/${stat.quota}`}
                  warn={stat.selected < stat.quota}
                />
              ))}
            </Section>
          )}

          {/* Failed Mutations */}
          {failCount > 0 && (
            <Section title="Failed Mutations">
              <div className="text-xs text-gray-600 space-y-0.5">
                {failedMutations.slice(0, 5).map((f) => (
                  <div key={f.mutation} className="flex justify-between">
                    <span className="font-mono">{f.mutation}</span>
                    <span className="text-gray-400 truncate ml-2">{f.reason}</span>
                  </div>
                ))}
                {failCount > 5 && <div className="text-gray-400">+{failCount - 5} more</div>}
              </div>
            </Section>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" size="sm" onClick={() => setShowReport(false)}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
