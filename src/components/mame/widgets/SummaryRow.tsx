import { useMemo } from "react";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import type { VerdictClass } from "@/types/mame/models";
import { cn } from "@/lib/utils";

function getReadinessTone(readiness: number): string {
  if (readiness === 100) {
    return "border-l-4 border-l-primary bg-primary/5";
  }
  if (readiness > 0) {
    return "border-l-4 border-l-accent bg-[hsl(var(--accent)/0.10)]";
  }
  return "border-l-4 border-l-border bg-muted/35";
}

function getStatusTone(args: {
  isAnalyzing: boolean;
  validationErrors: number;
  hasResults: boolean;
  readyCount: number;
}): string {
  if (args.isAnalyzing) {
    return "border-l-4 border-l-primary bg-[hsl(var(--primary)/0.08)]";
  }
  if (args.validationErrors > 0) {
    return "border-l-4 border-l-destructive bg-destructive/5";
  }
  if (args.hasResults) {
    return "border-l-4 border-l-primary bg-primary/5";
  }
  if (args.readyCount === 4) {
    return "border-l-4 border-l-primary bg-[hsl(var(--primary)/0.08)]";
  }
  return "border-l-4 border-l-border bg-muted/35";
}

export function SummaryRow() {
  const verdicts = useMameAppStore((s) => s.verdicts);
  const wells = useMameAppStore((s) => s.wells);
  const inputDir = useMameAppStore((s) => s.inputDir);
  const expectedPath = useMameAppStore((s) => s.expectedPath);
  const referencePath = useMameAppStore((s) => s.referencePath);
  const outputPath = useMameAppStore((s) => s.outputPath);
  const isAnalyzing = useMameAppStore((s) => s.isAnalyzing);
  const analyzeProgress = useMameAppStore((s) => s.analyzeProgress);
  const validationErrors = useMameAppStore((s) => s.validationErrors);

  const readyCount = [inputDir, expectedPath, referencePath, outputPath].filter(Boolean).length;
  const readiness = Math.round((readyCount / 4) * 100);

  const stats = useMemo(() => {
    const FAIL: readonly VerdictClass[] = ["WRONG_AA", "FRAMESHIFT", "MANY"];
    let pass = 0;
    let fail = 0;
    for (const v of verdicts) {
      if (v.verdict === "PASS") pass += 1;
      else if (FAIL.includes(v.verdict)) fail += 1;
    }
    const total = verdicts.length;
    const successRate = total > 0 ? Math.round((pass / total) * 100) : null;
    return { total, pass, fail, successRate };
  }, [verdicts]);

  const plateEstimate = wells.length > 0 ? Math.ceil(wells.length / 96) : null;

  const statusLabel = isAnalyzing
    ? `Analyzing ${analyzeProgress}%`
    : validationErrors.length > 0
      ? `${validationErrors.length} error(s)`
      : verdicts.length > 0
        ? "Results ready"
        : readyCount === 4
          ? "Ready to run"
          : "Draft setup";

  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4" aria-label="Analysis summary">
      <SummaryTile
        className="bg-gradient-to-br from-[hsl(var(--hero-start))] to-[hsl(var(--hero-end))]"
        label="Success rate"
        value={stats.successRate !== null ? `${stats.successRate}%` : "—"}
        hint={stats.total > 0 ? `${stats.pass}/${stats.total} PASS` : "No results yet"}
      />
      <SummaryTile
        className="border-l-4 border-l-primary"
        label="Plates"
        value={plateEstimate ?? "—"}
        valueClassName="text-primary"
        hint={plateEstimate ? `${wells.length} wells` : "Awaiting analysis"}
      />
      <SummaryTile
        className={getReadinessTone(readiness)}
        label="Readiness"
        value={`${readiness}%`}
        valueClassName="text-foreground"
        hint={`${readyCount}/4 paths filled`}
      />
      <SummaryTile
        className={getStatusTone({
          isAnalyzing,
          validationErrors: validationErrors.length,
          hasResults: verdicts.length > 0,
          readyCount,
        })}
        label="Status"
        value={statusLabel}
        valueClassName="text-base"
        hint={isAnalyzing ? "In progress" : undefined}
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
}: {
  className?: string;
  label: string;
  value: string | number;
  valueClassName?: string;
  hint?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col gap-1 rounded-lg border border-border bg-background px-4 py-3",
        className,
      )}
      role="status"
      aria-label={`${label}: ${value}`}
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
