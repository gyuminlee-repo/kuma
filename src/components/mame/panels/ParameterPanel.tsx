import { useMameAppStore } from "@/store/mame/mameAppStore";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

export function ParameterPanel() {
  const mode = useMameAppStore((s) => s.mode);
  const ingestMode = useMameAppStore((s) => s.ingestMode);
  const cdsStart = useMameAppStore((s) => s.cdsStart);
  const cdsEnd = useMameAppStore((s) => s.cdsEnd);
  const minFileSizeKb = useMameAppStore((s) => s.minFileSizeKb);
  const manyCutoff = useMameAppStore((s) => s.manyCutoff);
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
          <Label htmlFor="mode-select" className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
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
          <Label htmlFor="ingest-mode-select" className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
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
        <NumericField
          id="min-file-kb"
          label="Min File KB"
          value={minFileSizeKb}
          step="0.1"
          onChange={(value) => setParams({ minFileSizeKb: value })}
        />
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
      <Label htmlFor={id} className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
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
