import { useMameAppStore } from "@/store/mame/mameAppStore";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { AlertTriangle } from "lucide-react";
import type { DistributionStats } from "@/types/mame/models";

const METHOD_LABELS: Record<DistributionStats["suggested_method"], string> = {
  median_minus_2sigma: "median − 2σ",
  p05: "p05",
  kneedle: "knee",
  fixed_50: "floor 50",
};

const BIMODAL_TOOLTIP = "Distribution looks bimodal. Recommended uses knee detection.";

function RecommendedCutoff({
  stats,
  onApply,
}: {
  stats: DistributionStats;
  onApply: (value: number) => void;
}) {
  const methodLabel = METHOD_LABELS[stats.suggested_method];

  return (
    <div className="flex items-center gap-1.5">
      <span className="text-caption text-muted-foreground">
        Recommended:{" "}
        <span className="font-medium text-foreground">
          {stats.suggested_cutoff_kb.toFixed(1)} KB
        </span>{" "}
        <span className="text-muted-foreground">({methodLabel})</span>
      </span>
      {stats.bimodal && (
        <span
          className="inline-flex cursor-help items-center text-warning"
          aria-label={BIMODAL_TOOLTIP}
          title={BIMODAL_TOOLTIP}
          role="img"
        >
          <AlertTriangle size={11} aria-hidden="true" />
        </span>
      )}
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="h-5 px-1.5 text-caption"
        onClick={() => onApply(stats.suggested_cutoff_kb)}
        aria-label={`Apply recommended cutoff of ${stats.suggested_cutoff_kb.toFixed(1)} KB`}
      >
        Use
      </Button>
    </div>
  );
}

export function ParameterPanel() {
  const mode = useMameAppStore((s) => s.mode);
  const ingestMode = useMameAppStore((s) => s.ingestMode);
  const cdsStart = useMameAppStore((s) => s.cdsStart);
  const cdsEnd = useMameAppStore((s) => s.cdsEnd);
  const minFileSizeKb = useMameAppStore((s) => s.minFileSizeKb);
  const manyCutoff = useMameAppStore((s) => s.manyCutoff);
  const distributionStats = useMameAppStore((s) => s.distributionStats);
  const setParams = useMameAppStore((s) => s.setParams);

  return (
    <div className="rounded-lg border border-border bg-background p-4 space-y-3">
      <header>
        <h3 className="text-sm font-semibold text-foreground">Parameters</h3>
        <p className="mt-1 text-xs text-muted-foreground">
          Thresholds and ingest mode for this batch.
        </p>
      </header>

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1">
          <Label htmlFor="mode-select" className="text-caption font-medium uppercase tracking-wide text-muted-foreground">
            Mode
          </Label>
          <Select
            value={mode}
            onValueChange={(value) => setParams({ mode: value as "amplicon" | "plasmid" })}
          >
            <SelectTrigger id="mode-select" className="h-8 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="amplicon">amplicon</SelectItem>
              <SelectItem value="plasmid">plasmid</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-1">
          <Label htmlFor="ingest-mode-select" className="text-caption font-medium uppercase tracking-wide text-muted-foreground">
            Ingest
          </Label>
          <Select
            value={ingestMode}
            onValueChange={(value) => setParams({ ingestMode: value as "barcode" | "amplicon" })}
          >
            <SelectTrigger id="ingest-mode-select" className="h-8 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="barcode">barcode</SelectItem>
              <SelectItem value="amplicon">amplicon</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <NumericField
          id="cds-start"
          label="CDS Start"
          value={cdsStart}
          onChange={(value) => setParams({ cdsStart: value })}
        />
        <NumericField
          id="cds-end"
          label="CDS End"
          value={cdsEnd}
          onChange={(value) => setParams({ cdsEnd: value })}
        />

        <div className="space-y-1 sm:col-span-2">
          <Label htmlFor="min-file-kb" className="text-caption font-medium uppercase tracking-wide text-muted-foreground">
            Min File KB
          </Label>
          <Input
            id="min-file-kb"
            type="number"
            step="0.1"
            value={Number.isFinite(minFileSizeKb) ? minFileSizeKb : ""}
            onChange={(e) => {
              const raw = e.target.value;
              if (raw === "") return;
              const n = Number(raw);
              if (Number.isFinite(n)) setParams({ minFileSizeKb: n });
            }}
            className="h-8 text-xs"
            aria-label="Min File KB"
          />
          {distributionStats !== null && (
            <RecommendedCutoff
              stats={distributionStats}
              onApply={(value) => setParams({ minFileSizeKb: value })}
            />
          )}
        </div>

        <NumericField
          id="many-cutoff"
          label="Many Cutoff"
          value={manyCutoff}
          onChange={(value) => setParams({ manyCutoff: value })}
        />
      </div>
    </div>
  );
}

function NumericField({
  id,
  label,
  value,
  onChange,
  step,
}: {
  id: string;
  label: string;
  value: number;
  onChange: (value: number) => void;
  step?: string;
}) {
  return (
    <div className="space-y-1">
      <Label htmlFor={id} className="text-caption font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </Label>
      <Input
        id={id}
        type="number"
        step={step}
        value={Number.isFinite(value) ? value : ""}
        onChange={(e) => {
          const raw = e.target.value;
          if (raw === "") return;
          const n = Number(raw);
          if (Number.isFinite(n)) onChange(n);
        }}
        className="h-8 text-xs"
        aria-label={label}
      />
    </div>
  );
}
