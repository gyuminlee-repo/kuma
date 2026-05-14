/**
 * ParameterInspector — KURO Design/Parameters screen inspector.
 *
 * Shows expected design metrics that update as parameters change.
 * Data sources:
 *   - designResults (designSlice) — primer count after last run
 *   - plateMappings (exportSlice) — plate count
 *   - parsedMutations (inputSlice) — mutation count for runtime estimate
 *
 * When no design has run yet, counts show "--" (not 0) to avoid false signal.
 *
 * [source: v5-strategy.md §6.1 row 3]
 * [source: mockup v6 line 400]
 */

import { useTranslation } from "react-i18next";
import { useAppStore } from "@/store/appStore";
import { useShallow } from "zustand/react/shallow";
import { InspectorPanel } from "@/components/widgets/InspectorPanel";
import { InspectorCallout } from "@/components/inspectors/kuro/shared/InspectorCallout";

type MetricCardProps = {
  label: string;
  value: string;
  variant?: "default" | "warn" | "ok";
};

function MetricCard({ label, value, variant = "default" }: MetricCardProps) {
  const colorCls =
    variant === "warn"
      ? "text-warning"
      : variant === "ok"
        ? "text-success"
        : "text-foreground";
  return (
    <div className="rounded-md border border-border bg-muted/30 px-3 py-2">
      <div className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div className={`mt-0.5 text-[18px] font-bold tabular-nums ${colorCls}`}>
        {value}
      </div>
    </div>
  );
}

export function ParameterInspector() {
  const { t } = useTranslation();

  const { designResults, plateMappings, parsedMutations } = useAppStore(
    useShallow((s) => ({
      designResults: s.designResults,
      plateMappings: s.plateMappings,
      parsedMutations: s.parsedMutations,
    })),
  );

  const primerCount = designResults.length > 0 ? String(designResults.length) : "--";

  // Count unique plate names from plate mappings
  const plateSet = new Set(plateMappings.map((m) => m.primer_name.split("_")[0]));
  const plateCount = plateMappings.length > 0 ? String(plateSet.size > 0 ? Math.ceil(plateMappings.length / 96) : 1) : "--";

  const warnCount = designResults.reduce(
    (acc, r) => acc + (r.warnings.length > 0 ? 1 : 0),
    0,
  );
  const warnValue = designResults.length > 0 ? String(warnCount) : "--";
  const warnVariant: "default" | "warn" | "ok" =
    designResults.length === 0 ? "default" : warnCount > 0 ? "warn" : "ok";

  // Runtime estimate: ~0.5s per mutation, displayed as seconds or minutes
  const mutCount = parsedMutations.length;
  let runtimeValue = "--";
  if (mutCount > 0) {
    const secs = Math.max(5, Math.round(mutCount * 0.5));
    runtimeValue = secs >= 60 ? `~${Math.ceil(secs / 60)} min` : `~${secs}s`;
  }

  return (
    <InspectorPanel title={t("kuro.params.inspectorTitle")}>
      <div className="grid grid-cols-2 gap-2">
        <MetricCard label={t("kuro.params.metricPrimers")} value={primerCount} />
        <MetricCard label={t("kuro.params.metricPlates")} value={plateCount} />
        <MetricCard
          label={t("kuro.params.metricWarn")}
          value={warnValue}
          variant={warnVariant}
        />
        <MetricCard label={t("kuro.params.metricRuntime")} value={runtimeValue} />
      </div>
      <InspectorCallout label={t("kuro.inspector.intentLabel")}>
        {t("kuro.params.calloutText")}
      </InspectorCallout>
    </InspectorPanel>
  );
}
