import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useMameAppStore } from "@/store/mame/mameAppStore";

import { formatRunDuration } from "@/lib/mame/runDuration";
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
  const runHealth = useMameAppStore((s) => s.runHealth);
  const analyzeDurationMs = useMameAppStore((s) => s.analyzeDurationMs);

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
    const pass = Array.from(passByMutant.values()).filter(Boolean).length;
    // Denominator is the designed-mutant count (matches the comment above and the
    // successRateHint copy). A designed mutant that produced zero consensus across
    // all of its wells emits no VerdictRecord, so it is absent from `verdicts` and
    // would otherwise be dropped from the denominator, inflating the headline rate.
    // Fall back to the observed count when runHealth is unavailable (e.g. the
    // workspace-reload path before analysis metrics load).
    const total = runHealth?.total_mutants ?? passByMutant.size;
    const successRate = total > 0 ? Math.round((pass / total) * 100) : null;
    return { total, pass, successRate };
  }, [verdicts, runHealth]);

  // `wells` is one entry per VerdictRecord (see handlers/export.py), i.e. one
  // per well PER REPLICATE PLATE, so a well sequenced on three native barcodes
  // is three entries. Both numbers built here are statements about distinct
  // wells: the hint says "N wells" and the estimate divides by a 96-well plate.
  // Counting entries made a ten-well declaration read as "웰 57개" on 96-well
  // hardware. This is the same over-count the success rate above already refuses
  // to make, made one line later.
  //
  // An entry whose barcode maps to no well carries `""` and is not a well to
  // count.
  const distinctWells = useMemo(() => {
    const ids = new Set<string>();
    for (const w of wells) {
      if (w.well) ids.add(w.well);
    }
    return ids.size;
  }, [wells]);

  const plateEstimate = distinctWells > 0 ? Math.ceil(distinctWells / 96) : null;

  const statusLabel = isAnalyzing
    ? t("mame.summaryRow.statusAnalyzing", { progress: analyzeProgress })
    : validationErrors.length > 0
      ? t("mame.summaryRow.statusErrors", { count: validationErrors.length })
      : verdicts.length > 0
        ? t("mame.summaryRow.statusReady")
        : readyCount === 4
          ? t("mame.summaryRow.statusReadyToRun")
          : t("mame.summaryRow.statusDraft");

  // Resident counterpart of the step 2.1 completion popup: the popup is gone
  // the moment it is dismissed, so the same duration stays on the Status tile
  // that already carries run state. Rendered as that tile's hint rather than a
  // fifth tile, which would stretch the 2.2 layout by a whole row on narrow
  // widths. `analyzeDurationMs` is null before the first run and after a
  // cancel/failure, and a zero-verdict run is left to EmptyAnalysisNotice, so
  // in all three cases the hint is simply absent instead of reading "0 min".
  const elapsedHint =
    !isAnalyzing && analyzeDurationMs !== null && verdicts.length > 0
      ? t("mame.summaryRow.statusElapsed", {
          duration: formatRunDuration(analyzeDurationMs, t),
        })
      : undefined;

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
        hint={plateEstimate ? t("mame.summaryRow.platesHint", { count: distinctWells }) : t("mame.summaryRow.platesEmpty")}
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
        hint={isAnalyzing ? t("mame.summaryRow.statusInProgress") : elapsedHint}
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
