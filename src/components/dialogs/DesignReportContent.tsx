import { useTranslation } from "react-i18next";
import { useShallow } from "zustand/react/shallow";
import { useAppStore } from "../../store/appStore";
import { DialogFooter } from "../ui/dialog";
import { Button } from "../ui/button";

function Stat({ label, value, warn }: { label: string; value: string | number; warn?: boolean }) {
  return (
    <div className="flex justify-between text-xs">
      <span className="text-muted-foreground">{label}</span>
      <span className={warn ? "font-medium text-warning" : "font-medium text-foreground"}>{value}</span>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <h4 className="text-caption font-semibold uppercase tracking-widest text-muted-foreground">{title}</h4>
      <div className="space-y-1 rounded-2xl border border-border bg-card p-3">{children}</div>
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

export interface DesignReportContentProps {
  /**
   * When provided, a close button is rendered in the footer that invokes this callback.
   * Omit in inline (Inspector) contexts where no close affordance is needed.
   */
  onClose?: () => void;
}

export function DesignReportContent({ onClose }: DesignReportContentProps) {
  const { t } = useTranslation();
  const data = useAppStore(
    useShallow((s) => ({
      designResults: s.designResults,
      failedMutations: s.failedMutations,
      totalCount: s.totalCount,
      evolveproMode: s.evolveproMode,
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
    })),
  );

  if (data.designResults.length === 0) return null;

  const {
    designResults,
    failedMutations,
    totalCount,
    evolveproMode,
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

  const cascadeCounts = (() => {
    const c = { l1: 0, l2: 0, l3: 0, l4: 0, samePos: 0, diffPos: 0 };
    for (const r of rescuedMutationDetails) {
      if (r.type === "auto_suggestion_l1") c.l1++;
      else if (r.type === "auto_suggestion_l2") c.l2++;
      else if (r.type === "auto_suggestion_l3") c.l3++;
      else if (r.type === "auto_suggestion_l4") c.l4++;
      else if (r.type === "same_position") c.samePos++;
      else if (r.type === "diff_position") c.diffPos++;
    }
    return c;
  })();
  const cascadeTotal = cascadeCounts.l1 + cascadeCounts.l2 + cascadeCounts.l3 + cascadeCounts.l4 + cascadeCounts.samePos + cascadeCounts.diffPos;

  const rescuePenalties = rescuedMutationDetails
    .map((r) => r.penalty).filter((p): p is number => p != null);
  const avgRescuePenalty = avg(rescuePenalties);
  const rescuedSet = new Set(rescuedMutationDetails.map((d) => d.rescued_by));
  const avgNormalPenalty = avg(
    designResults.filter((r) => !rescuedSet.has(r.mutation)).map((r) => r.penalty),
  );
  const paretoExchanges = evolveproStepStats?.pareto_exchanges ?? evolveproParetoExchanges;

  return (
    <>
      <div className="flex flex-col space-y-1.5 text-center sm:text-left">
        <h2 className="flex items-center gap-2 text-lg font-semibold leading-none tracking-tight">
          <span className="text-xl">{t("designReport.title")}</span>
        </h2>
        <p className="text-sm text-muted-foreground">
          {t("designReport.description", { success: successCount, total: totalCount, rate: successRate })}
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        {/* Pipeline Summary */}
        {evolveproMode !== "topN" && (
          <Section title={t("designReport.sectionPipeline")}>
            <Stat
              label={t("designReport.statStep1Filter")}
              value={
                positionDiversityEnabled
                  ? positionRemoved != null && positionRemoved > 0
                    ? t("designReport.statStep1_onRemoved", { max: maxPerPosition, removed: positionRemoved })
                    : t("designReport.statStep1_on", { max: maxPerPosition })
                  : "OFF"
              }
            />
            <Stat
              label={t("designReport.statStep2Domains")}
              value={formatDomainAllocation(domainDiversityEnabled, domains, domainStats, domainStrategy)}
            />
            {domainDiversityEnabled && (
              <Stat label={t("designReport.statStep2Overlap")} value={domainOverlapPolicy === "largest" ? "LARGEST" : "FIRST"} />
            )}
            {domainDiversityEnabled && (
              <Stat label={t("designReport.statStep2Linker")} value={linkerHandling.toUpperCase()} />
            )}
            {domainDiversityEnabled && (
              <Stat label={t("designReport.statStep2MinQuota")} value={domainQuotaMin} />
            )}
            <Stat
              label={t("designReport.statStep3Pareto")}
              value={
                paretoDiversityEnabled
                  ? paretoExchanges != null && paretoExchanges > 0
                    ? t("designReport.statPareto_onSwapped", { count: paretoExchanges })
                    : t("designReport.statPareto_on")
                  : "OFF"
              }
            />
            <Stat label={t("designReport.statDistanceMode")} value={distanceMode === "auto" ? (structureLoaded ? t("designReport.statDistanceAuto3D") : t("designReport.statDistanceAuto1D")) : distanceMode.toUpperCase()} />
            <Stat label={t("designReport.statParetoPool")} value={`${paretoPoolMultiplier.toFixed(2)}x`} />
            <Stat label={t("designReport.statEntropyGuided")} value={entropyWeightEnabled ? `ON (${entropyWeight.toFixed(2)})` : "OFF"} />
            <Stat label={t("designReport.statAlphaFold3D")} value={structureLoaded ? "ON (Cα distance)" : "OFF (1D distance)"} />
            {positionRemoved != null && positionDiversityEnabled && (
              <Stat label={t("designReport.statRemovedByStep1")} value={positionRemoved} />
            )}
            {domainSelected != null && domainDiversityEnabled && (
              <Stat label={t("designReport.statAfterStep2")} value={domainSelected} />
            )}
            {paretoExchanges != null && paretoDiversityEnabled && (
              <Stat label={t("designReport.statStep3Exchanges")} value={paretoExchanges} />
            )}
            {evolveproTotalCount > 0 && (
              <Stat
                label={t("designReport.statEvolveproPool")}
                value={t("designReport.statVariants", { count: evolveproTotalCount })}
              />
            )}
          </Section>
        )}

        <Section title={t("designReport.sectionBenchmarkDefaults")}>
          <Stat label={t("designReport.statTopPercentile")} value={`${benchmarkTopPercentile}%`} />
          <Stat label={t("designReport.statRandomTrials")} value={benchmarkRandomTrials} />
          <Stat label={t("designReport.statRandomSeed")} value={benchmarkRandomSeed ?? t("designReport.statSeedAuto")} />
        </Section>

        {/* Primer Design */}
        <Section title={t("designReport.sectionPrimerDesign")}>
          <Stat label={t("designReport.statSucceeded")} value={`${successCount}/${totalCount}`} />
          <Stat label={t("designReport.statTmMet")} value={`${tmMet}/${successCount}`} warn={tmMet < successCount} />
          {failCount > 0 && <Stat label={t("designReport.statFailed")} value={failCount} warn />}
        </Section>

        {/* Position Rescue */}
        {rescueTotal > 0 && (
          <Section title={t("designReport.sectionPositionRescue")}>
            <Stat
              label={t("designReport.statPositionCoverage")}
              value={rescueStats.positions_attempted > 0
                ? t("designReport.statPositionCoverageValue", { rescued: rescueTotal, attempted: rescueStats.positions_attempted })
                : "0"}
            />
            {rescueStats.pool_cascade > 0 && (
              <Stat label={t("designReport.statPoolCascade")} value={t("designReport.statPoolCascadeValue", { cascade: rescueStats.pool_cascade, tried: rescueStats.pool_variants_tried })} />
            )}
            {rescueStats.auto_relax > 0 && (
              <Stat label={t("designReport.statAutoRelax")} value={rescueStats.auto_relax} />
            )}
            {rescuedMutationDetails.filter((r) => r.type === "auto_suggestion").length > 0 && (
              <Stat
                label={t("designReport.statAutoRetry")}
                value={rescuedMutationDetails.filter((r) => r.type === "auto_suggestion").length}
              />
            )}
            {cascadeTotal > 0 && (
              <Stat
                label={t("designReport.statCascadeRescues")}
                value={`↻¹ ${cascadeCounts.samePos} · ↻² ${cascadeCounts.diffPos} · \u{1F3AF}¹ ${cascadeCounts.l1} · \u{1F3AF}² ${cascadeCounts.l2} · \u{1F3AF}³ ${cascadeCounts.l3} · \u{1F3AF}⁴ ${cascadeCounts.l4}`}
              />
            )}
            {failCount > 0 && (
              <Stat label={t("designReport.statStillFailed")} value={failCount} warn />
            )}
            {rescuePenalties.length > 0 && (
              <Stat
                label={t("designReport.statRescuedAvgPenalty")}
                value={t("designReport.statRescuedPenaltyValue", { rescued: avgRescuePenalty.toFixed(1), normal: avgNormalPenalty.toFixed(1) })}
                warn={avgRescuePenalty > avgNormalPenalty * 1.5}
              />
            )}
            {rescuedMutationDetails.length > 0 && (
              <div className="mt-1 space-y-0.5 text-xs text-muted-foreground">
                {rescuedMutationDetails.slice(0, 5).map((r, i) => (
                  <div key={i} className="flex justify-between">
                    <span className="font-mono">
                      {(r.type === "pool_cascade" || r.type === "same_position" || r.type === "diff_position")
                        ? `${r.original} → ${r.rescued_by}`
                        : r.original}
                    </span>
                    <span
                      className={
                        r.type === "pool_cascade" || r.type === "same_position" || r.type === "diff_position"
                          ? "text-success"
                          : r.type === "auto_suggestion" || r.type === "auto_suggestion_l1" || r.type === "auto_suggestion_l2"
                            ? "text-info"
                            : "text-warning"
                      }
                    >
                      {r.type === "pool_cascade"
                        ? "↻ cascade"
                        : r.type === "same_position"
                          ? "↻¹ same pos"
                          : r.type === "diff_position"
                            ? "↻² diff pos"
                            : r.type === "auto_suggestion"
                              ? "\u{1F3AF} suggestion"
                              : r.type === "auto_suggestion_l1"
                                ? "\u{1F3AF}¹ stage 1"
                                : r.type === "auto_suggestion_l2"
                                  ? "\u{1F3AF}² stage 2"
                                  : r.type === "auto_suggestion_l3"
                                    ? "\u{1F3AF}³ stage 3"
                                    : r.type === "auto_suggestion_l4"
                                      ? "\u{1F3AF}⁴ stage 4"
                                      : "⚡ relaxed"}
                      {r.penalty != null && ` (${r.penalty.toFixed(1)})`}
                    </span>
                  </div>
                ))}
                {rescuedMutationDetails.length > 5 && (
                  <div className="text-muted-foreground">{t("designReport.moreItems", { count: rescuedMutationDetails.length - 5 })}</div>
                )}
              </div>
            )}
          </Section>
        )}

        {/* Tm Distribution */}
        {fwdTms.length > 0 && (
          <Section title={t("designReport.sectionTmDistribution")}>
            <Stat label={t("designReport.statForward")} value={`${avg(fwdTms).toFixed(1)} ± ${std(fwdTms).toFixed(1)} °C`} />
            <Stat label={t("designReport.statReverse")} value={`${avg(revTms).toFixed(1)} ± ${std(revTms).toFixed(1)} °C`} />
            <Stat label={t("designReport.statOverlap")} value={`${avg(ovTms).toFixed(1)} ± ${std(ovTms).toFixed(1)} °C`} />
          </Section>
        )}

        {/* Domain Stats */}
        {Object.keys(domainStats).length > 0 && (
          <Section title={t("designReport.sectionDomainAllocation")}>
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
          <Section title={t("designReport.sectionFailedMutations")}>
            <div className="space-y-0.5 text-xs text-muted-foreground min-w-0">
              {failedMutations.slice(0, 20).map((f) => (
                <div key={f.mutation} className="flex justify-between gap-2 min-w-0">
                  <span className="font-mono shrink-0">{f.mutation}</span>
                  <span className="ml-2 break-words whitespace-pre-wrap text-muted-foreground min-w-0 flex-1 text-right">{f.reason}</span>
                </div>
              ))}
              {failCount > 20 && <div className="text-muted-foreground">{t("designReport.moreItems", { count: failCount - 20 })}</div>}
            </div>
          </Section>
        )}
      </div>

      {onClose && (
        <DialogFooter>
          <Button variant="outline" size="sm" className="rounded-full" onClick={onClose}>
            {t("designReport.close")}
          </Button>
        </DialogFooter>
      )}
    </>
  );
}
