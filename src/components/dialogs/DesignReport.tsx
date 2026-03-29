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

export function DesignReport() {
  const setShowReport = useAppStore((s) => s.setShowReport);
  const data = useAppStore((s) => {
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
      domains: s.domains,
      domainStats: s.domainStats,
      paretoDiversityEnabled: s.paretoDiversityEnabled,
      entropyWeightEnabled: s.entropyWeightEnabled,
      esmEmbeddingLoaded: s.esmEmbeddingLoaded,
      evolveproTotalCount: s.evolveproTotalCount,
      mutationInputMode: s.mutationInputMode,
    };
  });

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
    domains,
    domainStats,
    paretoDiversityEnabled,
    entropyWeightEnabled,
    esmEmbeddingLoaded,
    evolveproTotalCount,
    mutationInputMode,
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
              <Stat label="Position filter" value={positionDiversityEnabled ? `max ${maxPerPosition}/pos` : "OFF"} />
              <Stat label="Domain allocation" value={domainDiversityEnabled && domains.length > 0 ? `${domainStrategy} (${domains.length} domains)` : "OFF"} />
              <Stat label="Pareto diversity" value={paretoDiversityEnabled ? "ON" : "OFF"} />
              <Stat label="Entropy-guided" value={entropyWeightEnabled ? "ON" : "OFF"} />
              <Stat label="ESM-2 structural" value={esmEmbeddingLoaded ? "ON (cosine distance)" : "OFF (1D distance)"} />
              {evolveproTotalCount > 0 && (
                <Stat label={mutationInputMode === "multi-evolve" ? "MULTI-evolve pool" : "EVOLVEpro pool"} value={`${evolveproTotalCount} variants`} />
              )}
            </Section>
          )}

          {/* Primer Design Results */}
          <Section title="Primer Design">
            <Stat label="Succeeded" value={`${successCount}/${totalCount}`} />
            <Stat label="Tm condition met" value={`${tmMet}/${successCount}`} warn={tmMet < successCount} />
            {failCount > 0 && <Stat label="Failed" value={failCount} warn />}
          </Section>

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
