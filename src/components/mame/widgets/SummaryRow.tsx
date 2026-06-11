import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useMameAppStore } from "@/store/mame/mameAppStore";

import { cn } from "@/lib/utils";

function getReadinessTone(readiness: number): string {
  if (readiness === 100) {
    return "bg-primary/5";
  }
  if (readiness > 0) {
    return "bg-[hsl(var(--accent)/0.10)]";
  }
  return "bg-muted/35";
}

function getStatusTone(args: {
  isAnalyzing: boolean;
  validationErrors: number;
  hasResults: boolean;
  readyCount: number;
  requiredCount: number;
}): string {
  if (args.isAnalyzing) {
    return "bg-[hsl(var(--primary)/0.08)]";
  }
  if (args.validationErrors > 0) {
    return "bg-destructive/5";
  }
  if (args.hasResults) {
    return "bg-primary/5";
  }
  if (args.readyCount === args.requiredCount) {
    return "bg-[hsl(var(--primary)/0.08)]";
  }
  return "bg-muted/35";
}

export function SummaryRow() {
  const { t } = useTranslation();
  const verdicts = useMameAppStore((s) => s.verdicts);
  const wells = useMameAppStore((s) => s.wells);
  const inputDir = useMameAppStore((s) => s.inputDir);
  const expectedPath = useMameAppStore((s) => s.expectedPath);
  const referencePath = useMameAppStore((s) => s.referencePath);
  const outputPath = useMameAppStore((s) => s.outputPath);
  const inputMode = useMameAppStore((s) => s.inputMode);
  const customBarcodesPath = useMameAppStore((s) => s.rawRunParams.customBarcodesPath);
  const isAnalyzing = useMameAppStore((s) => s.isAnalyzing);
  const analyzeProgress = useMameAppStore((s) => s.analyzeProgress);
  const validationErrors = useMameAppStore((s) => s.validationErrors);

  const requiredInputs = inputMode === "raw_run"
    ? [inputDir, customBarcodesPath, expectedPath, referencePath, outputPath]
    : [inputDir, expectedPath, referencePath, outputPath];
  const readyCount = requiredInputs.filter(Boolean).length;
  const readiness = Math.round((readyCount / requiredInputs.length) * 100);

  const stats = useMemo(() => {
    // Success = a designed mutant with at least one PASS replicate, over all
    // designed mutants. A per-record pass/total ratio overcounts because each
    // well is sequenced across several replicates (e.g. 171/288); the intent is
    // the share of variants reproduced cleanly at least once. WT controls and
    // UNKNOWN_* heuristic groups are excluded (not designed mutants).
    const passByMutant = new Map<string, boolean>();
    for (const v of verdicts) {
      const id = v.mutant_id || v.native_barcode || "—";
      if (id === "WT" || id.startsWith("UNKNOWN_")) continue;
      passByMutant.set(
        id,
        (passByMutant.get(id) ?? false) || v.verdict === "PASS",
      );
    }
    const total = passByMutant.size;
    const pass = Array.from(passByMutant.values()).filter(Boolean).length;
    const successRate = total > 0 ? Math.round((pass / total) * 100) : null;
    return { total, pass, successRate };
  }, [verdicts]);

  const plateEstimate = wells.length > 0 ? Math.ceil(wells.length / 96) : null;

  const statusLabel = isAnalyzing
    ? t("mame.summaryRow.statusAnalyzing", { progress: analyzeProgress })
    : validationErrors.length > 0
      ? t("mame.summaryRow.statusErrors", { count: validationErrors.length })
      : verdicts.length > 0
        ? t("mame.summaryRow.statusReady")
        : readyCount === 4
          ? t("mame.summaryRow.statusReadyToRun")
          : t("mame.summaryRow.statusDraft");

  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4" aria-label={t("mame.summaryRow.ariaLabel")}>
      <SummaryTile
        className="bg-gradient-to-br from-[hsl(var(--hero-start))] to-[hsl(var(--hero-end))]"
        title={t("mame.summaryRow.successRateHelp")}
        label={t("mame.summaryRow.successRate")}
        value={stats.successRate !== null ? `${stats.successRate}%` : "—"}
        hint={stats.total > 0 ? t("mame.summaryRow.successRateHint", { pass: stats.pass, total: stats.total }) : t("mame.summaryRow.successRateEmpty")}
      />
      <SummaryTile
        label={t("mame.summaryRow.plates")}
        value={plateEstimate ?? "—"}
        valueClassName="text-primary"
        hint={plateEstimate ? t("mame.summaryRow.platesHint", { count: wells.length }) : t("mame.summaryRow.platesEmpty")}
      />
      <SummaryTile
        className={getReadinessTone(readiness)}
        label={t("mame.summaryRow.readiness")}
        value={`${readiness}%`}
        valueClassName="text-foreground"
        hint={t("mame.summaryRow.readinessHint", { ready: readyCount, total: requiredInputs.length })}
      />
      <SummaryTile
        className={getStatusTone({
          isAnalyzing,
          validationErrors: validationErrors.length,
          hasResults: verdicts.length > 0,
          readyCount,
          requiredCount: requiredInputs.length,
        })}
        label={t("mame.summaryRow.status")}
        value={statusLabel}
        valueClassName="text-base"
        hint={isAnalyzing ? t("mame.summaryRow.statusInProgress") : undefined}
      />
    </div>
  );
}

function SummaryTile({
  className,
  label,
  value,
  valueClassName,
  hint,
  title,
}: {
  className?: string;
  label: string;
  value: string | number;
  valueClassName?: string;
  hint?: string;
  title?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col gap-1 rounded-lg border border-border bg-background px-4 py-3",
        className,
      )}
      role="status"
      aria-label={`${label}: ${value}`}
      title={title}
    >
      <span className="text-caption font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </span>
      <span
        className={cn(
          "font-display text-2xl font-semibold tabular-nums leading-none text-foreground",
          valueClassName,
        )}
      >
        {value}
      </span>
      {hint && <span className="text-caption text-muted-foreground">{hint}</span>}
    </div>
  );
}
