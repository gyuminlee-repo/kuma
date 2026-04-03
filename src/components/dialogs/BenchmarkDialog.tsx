import { useShallow } from "zustand/react/shallow";
import { useAppStore } from "../../store/appStore";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";
import { Button } from "../ui/button";
import { handleExportBenchmarkCsv, handleSaveBenchmarkJson } from "../layout/export-handlers";

const STRATEGY_LABELS: Record<string, string> = {
  topn: "Top-N",
  random: "Random",
  position_cap: "Position Cap",
  domain: "Domain",
  pareto_1d: "Pareto 1D",
  pareto_3d: "Pareto 3D",
  pareto_entropy: "Pareto + Entropy",
};

function MetricRow({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex justify-between text-xs">
      <span className="text-gray-500">{label}</span>
      <span className="font-medium text-gray-800">{value}</span>
    </div>
  );
}

export function BenchmarkDialog() {
  const data = useAppStore(
    useShallow((s) => ({
      open: s.showBenchmark,
      results: s.benchmarkResults,
      topPercentile: s.benchmarkTopPercentile,
      randomTrials: s.benchmarkRandomTrials,
      randomSeed: s.benchmarkRandomSeed,
      domainStrategy: s.domainStrategy,
      distanceMode: s.distanceMode,
      paretoPoolMultiplier: s.paretoPoolMultiplier,
      entropyWeight: s.entropyWeightEnabled ? s.entropyWeight : 0,
      setOpen: s.setShowBenchmark,
    })),
  );

  if (!data.results) return null;
  const results = data.results;

  return (
    <Dialog open={data.open} onOpenChange={data.setOpen}>
      <DialogContent className="max-w-3xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Benchmark</DialogTitle>
          <DialogDescription>
            Top {data.topPercentile}% hit threshold, random {data.randomTrials} trials, seed {data.randomSeed ?? "AUTO"}
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-3 md:grid-cols-2">
          {Object.entries(data.results).map(([strategy, metrics]) => (
            <div key={strategy} className="rounded-md border border-gray-200 p-3 space-y-1.5">
              <div className="text-sm font-semibold text-gray-800">
                {STRATEGY_LABELS[strategy] ?? strategy}
              </div>
              <MetricRow label="Hit rate" value={`${metrics.hit_rate.toFixed(1)}%`} />
              <MetricRow label="Mean fitness" value={metrics.mean_fitness.toFixed(3)} />
              <MetricRow label="Unique positions" value={metrics.unique_positions} />
              <MetricRow label="Position coverage" value={`${metrics.position_coverage.toFixed(1)}%`} />
              <MetricRow label="Domain coverage" value={`${metrics.domain_coverage.toFixed(1)}%`} />
              <MetricRow label="Structural spread" value={`${metrics.structural_spread.toFixed(1)}%`} />
              <MetricRow label="Hits" value={metrics.hits} />
              {metrics.n_trials != null && (
                <MetricRow label="Trials" value={metrics.n_trials} />
              )}
            </div>
          ))}
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              void handleSaveBenchmarkJson({
                exported_at: new Date().toISOString(),
                settings: {
                  top_percentile: data.topPercentile,
                  random_trials: data.randomTrials,
                  random_seed: data.randomSeed,
                  domain_strategy: data.domainStrategy,
                  distance_mode: data.distanceMode,
                  pareto_pool_multiplier: data.paretoPoolMultiplier,
                  entropy_weight: data.entropyWeight,
                },
                results,
              });
            }}
          >
            Save JSON
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              void handleExportBenchmarkCsv(results);
            }}
          >
            Export CSV
          </Button>
          <Button variant="outline" size="sm" onClick={() => data.setOpen(false)}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
