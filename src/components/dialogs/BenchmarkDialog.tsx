import { useMemo, useState } from "react";
import { useShallow } from "zustand/react/shallow";
import { useAppStore } from "../../store/appStore";
import type { BenchmarkResult } from "../../types/models";
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

const METRICS = [
  {
    key: "hit_rate",
    label: "Hit rate",
    format: (value: number) => `${value.toFixed(1)}%`,
    deltaUnit: "pp",
    decimals: 1,
  },
  {
    key: "mean_fitness",
    label: "Mean fitness",
    format: (value: number) => value.toFixed(3),
    deltaUnit: "",
    decimals: 3,
  },
  {
    key: "position_coverage",
    label: "Position cov",
    format: (value: number) => `${value.toFixed(1)}%`,
    deltaUnit: "pp",
    decimals: 1,
  },
  {
    key: "structural_spread",
    label: "Structural spread",
    format: (value: number) => `${value.toFixed(1)}%`,
    deltaUnit: "pp",
    decimals: 1,
  },
] as const;

type MetricKey = (typeof METRICS)[number]["key"];
type BaselineKey = "topn" | "random";

function formatDelta(value: number, decimals: number, unit: string): string {
  const abs = Math.abs(value).toFixed(decimals);
  const sign = value > 0 ? "+" : value < 0 ? "-" : "±";
  return `${sign}${abs}${unit ? ` ${unit}` : ""}`;
}

function baselineOptions(results: Record<string, BenchmarkResult>): BaselineKey[] {
  const options: BaselineKey[] = [];
  if (results.topn) options.push("topn");
  if (results.random) options.push("random");
  return options.length > 0 ? options : ["topn"];
}

function metricExtents(results: Record<string, BenchmarkResult>): Record<MetricKey, { min: number; max: number }> {
  const extents = {} as Record<MetricKey, { min: number; max: number }>;
  for (const metric of METRICS) {
    const values = Object.values(results).map((result) => result[metric.key]);
    const min = Math.min(...values);
    const max = Math.max(...values);
    extents[metric.key] = { min, max };
  }
  return extents;
}

function relativeBarWidth(value: number, min: number, max: number): string {
  if (max <= min) return "100%";
  const pct = ((value - min) / (max - min)) * 100;
  return `${Math.max(6, Math.min(100, pct))}%`;
}

function deltaTone(delta: number): string {
  if (delta > 0) return "text-success";
  if (delta < 0) return "text-error";
  return "text-muted-foreground";
}

function deltaBarTone(delta: number): string {
  if (delta > 0) return "bg-success/70";
  if (delta < 0) return "bg-error/70";
  return "bg-muted-foreground/50";
}

function BaselineSelector({
  options,
  selected,
  onChange,
}: {
  options: BaselineKey[];
  selected: BaselineKey;
  onChange: (key: BaselineKey) => void;
}) {
  if (options.length <= 1) {
    return (
      <span className="rounded-full border border-border bg-muted/50 px-3 py-1 text-caption font-medium text-muted-foreground">
        Baseline: {STRATEGY_LABELS[selected]}
      </span>
    );
  }

  return (
    <div className="inline-flex items-center rounded-full border border-border bg-muted/40 p-1">
      {options.map((option) => (
        <button
          key={option}
          type="button"
          className={`rounded-full px-3 py-1 text-caption font-medium transition-colors ${
            option === selected
              ? "bg-background text-foreground shadow-sm"
              : "text-muted-foreground hover:bg-muted/60"
          }`}
          onClick={() => onChange(option)}
        >
          {STRATEGY_LABELS[option]}
        </button>
      ))}
    </div>
  );
}

function MetricCell({
  value,
  baselineValue,
  min,
  max,
  format,
  decimals,
  deltaUnit,
}: {
  value: number;
  baselineValue: number;
  min: number;
  max: number;
  format: (value: number) => string;
  decimals: number;
  deltaUnit: string;
}) {
  const delta = value - baselineValue;
  const deltaAbsMax = Math.max(Math.abs(min - baselineValue), Math.abs(max - baselineValue), 0.0001);
  const deltaPct = `${Math.max(4, Math.min(100, Math.abs(delta) / deltaAbsMax * 100))}%`;

  return (
    <td className="min-w-40 border-b border-border/70 px-3 py-2 align-top">
      <div className="flex items-baseline justify-between gap-3">
        <span className="font-medium text-foreground">{format(value)}</span>
        <span className={`text-caption font-medium ${deltaTone(delta)}`}>
          {formatDelta(delta, decimals, deltaUnit)}
        </span>
      </div>
      <div className="mt-1.5 h-2 rounded-full bg-muted/70">
        <div
          className="h-full rounded-full bg-info/70"
          style={{ width: relativeBarWidth(value, min, max) }}
        />
      </div>
      <div className="mt-1 flex items-center gap-2">
        <span className="text-[11px] text-muted-foreground">vs baseline</span>
        <div className="h-1.5 flex-1 rounded-full bg-muted/40">
          <div
            className={`h-full rounded-full ${deltaBarTone(delta)}`}
            style={{ width: deltaPct }}
          />
        </div>
      </div>
    </td>
  );
}

export function BenchmarkDialog() {
  const data = useAppStore(
    useShallow((s) => ({
      open: s.showBenchmark,
      results: s.benchmarkResults,
      yPredMap: s.yPredMap,
      maxPrimers: s.maxPrimers,
      domains: s.domains,
      disabledDomains: s.disabledDomains,
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

  const baselineChoices = useMemo<BaselineKey[]>(
    () => (data.results ? baselineOptions(data.results) : ["topn"]),
    [data.results],
  );
  const [baseline, setBaseline] = useState<BaselineKey>(baselineChoices[0] ?? "topn");

  const normalizedBaseline = baselineChoices.includes(baseline) ? baseline : baselineChoices[0] ?? "topn";

  if (!data.results) return null;
  const results = data.results;
  const extents = metricExtents(results);
  const baselineResult = results[normalizedBaseline] ?? Object.values(results)[0];
  const activeDomains = data.domains.filter(
    (domain) => !data.disabledDomains.includes(`${domain.name}-${domain.start}`),
  );
  const excludedDomains = data.domains.filter(
    (domain) => data.disabledDomains.includes(`${domain.name}-${domain.start}`),
  );
  const landscape = Object.entries(data.yPredMap)
    .map(([variant, fitness]) => ({ variant, fitness }))
    .sort((a, b) => b.fitness - a.fitness);

  return (
    <Dialog open={data.open} onOpenChange={data.setOpen}>
      <DialogContent className="max-h-[84vh] max-w-6xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="text-xl">Benchmark</DialogTitle>
          <DialogDescription className="text-muted-foreground">
            Top {data.topPercentile}% hit threshold, random {data.randomTrials} trials, seed {data.randomSeed ?? "AUTO"}
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="text-caption text-muted-foreground">
            Compare each strategy against <span className="font-medium text-foreground">{STRATEGY_LABELS[normalizedBaseline]}</span>.
          </div>
          <BaselineSelector
            options={baselineChoices}
            selected={normalizedBaseline}
            onChange={setBaseline}
          />
        </div>

        <div className="overflow-x-auto rounded-container border border-border bg-card">
          <table className="w-full min-w-[920px] border-collapse text-caption">
            <thead className="sticky top-0 z-10 bg-card">
              <tr>
                <th className="border-b border-border px-3 py-2 text-left font-semibold text-muted-foreground">
                  Strategy
                </th>
                {METRICS.map((metric) => (
                  <th
                    key={metric.key}
                    className="border-b border-border px-3 py-2 text-left font-semibold text-muted-foreground"
                  >
                    {metric.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {Object.entries(results).map(([strategy, metrics]) => (
                <tr key={strategy} className="hover:bg-muted/20">
                  <td className="border-b border-border/70 px-3 py-2 align-top">
                    <div className="font-medium text-foreground">
                      {STRATEGY_LABELS[strategy] ?? strategy}
                    </div>
                    <div className="mt-1 text-[11px] text-muted-foreground">
                      hits {metrics.hits}
                      {metrics.n_trials != null ? ` · trials ${metrics.n_trials}` : ""}
                    </div>
                  </td>
                  {METRICS.map((metric) => (
                    <MetricCell
                      key={metric.key}
                      value={metrics[metric.key]}
                      baselineValue={baselineResult[metric.key]}
                      min={extents[metric.key].min}
                      max={extents[metric.key].max}
                      format={metric.format}
                      decimals={metric.decimals}
                      deltaUnit={metric.deltaUnit}
                    />
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="grid gap-2 text-caption text-muted-foreground md:grid-cols-2">
          <div>
            Blue bar: absolute value percentile within this benchmark run.
          </div>
          <div>
            Delta label/bar: difference from {STRATEGY_LABELS[normalizedBaseline]}.
          </div>
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            size="sm"
            className="rounded-full"
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
                  baseline: normalizedBaseline,
                },
                results,
              });
            }}
          >
            Save Summary JSON
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="rounded-full"
            onClick={() => {
              void handleSaveBenchmarkJson({
                exported_at: new Date().toISOString(),
                kind: "benchmark_raw",
                settings: {
                  baseline: normalizedBaseline,
                  n_select: Math.max(1, data.maxPrimers),
                  top_percentile: data.topPercentile,
                  random_trials: data.randomTrials,
                  random_seed: data.randomSeed,
                  domain_strategy: data.domainStrategy,
                  distance_mode: data.distanceMode,
                  pareto_pool_multiplier: data.paretoPoolMultiplier,
                  entropy_weight: data.entropyWeight,
                },
                domains: {
                  active: activeDomains,
                  excluded: excludedDomains,
                },
                landscape,
                results,
              });
            }}
          >
            Export Raw JSON
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="rounded-full"
            onClick={() => {
              void handleExportBenchmarkCsv(results);
            }}
          >
            Export CSV
          </Button>
          <Button variant="outline" size="sm" className="rounded-full" onClick={() => data.setOpen(false)}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
