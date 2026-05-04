import { useMameAppStore } from "@/store/mame/mameAppStore";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { AlertTriangle, Dna } from "lucide-react";
import { cn } from "@/lib/utils";
import type { AmpliconLengthEstimate, DistributionStats } from "@/types/mame/models";
import type { InputMode } from "@/store/mame/slice-interfaces";
import { ActivityUploadPanel } from "./ActivityUploadPanel";
import { WtWellEditor } from "@/components/mame/dialogs/WtWellEditor";
import { RoundHandoffButton } from "@/components/round/RoundHandoffButton";
import { useActivityStore, type ActivitySlice } from "@/store/mame/activitySlice";
import { useRoundStore } from "@/store/round/roundSlice";
import { useStore } from "zustand";
import { save } from "@tauri-apps/plugin-dialog";

const METHOD_LABELS: Record<DistributionStats["suggested_method"], string> = {
  median_minus_2sigma: "median − 2σ",
  p05: "p05",
  kneedle: "knee",
  fixed_50: "floor 50",
};

const INPUT_MODE_LABELS: Record<InputMode, string> = {
  consensus: "Consensus FASTA",
  sorted_barcode: "Sorted barcode files",
  raw_run: "MinKNOW raw run folder",
};

const BIMODAL_TOOLTIP =
  "Distribution looks bimodal. Recommended uses knee detection.";

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

function AmpliconLengthBadge({
  estimate,
}: {
  estimate: AmpliconLengthEstimate | null;
}) {
  if (!estimate) return null;
  const confidenceColor =
    estimate.confidence === "high"
      ? "text-green-600 dark:text-green-400"
      : estimate.confidence === "medium"
        ? "text-yellow-600 dark:text-yellow-400"
        : "text-muted-foreground";
  return (
    <span
      className={`inline-flex items-center gap-1 text-caption ${confidenceColor}`}
      aria-label={`Auto-detected amplicon length: ${estimate.detected_length} bp, confidence ${estimate.confidence}, sampled ${estimate.n_sample_reads.toLocaleString()} reads`}
    >
      <Dna size={11} aria-hidden="true" />
      Auto-detected: {estimate.detected_length.toLocaleString()} bp
      <span className="text-muted-foreground">
        (n={estimate.n_sample_reads.toLocaleString()}, {estimate.confidence})
      </span>
    </span>
  );
}

function RawRunParamPanel() {
  const rawRunParams = useMameAppStore((s) => s.rawRunParams);
  const isDemuxing = useMameAppStore((s) => s.isDemuxing);
  const demuxProgress = useMameAppStore((s) => s.demuxProgress);
  const demuxMessage = useMameAppStore((s) => s.demuxMessage);
  const demuxResult = useMameAppStore((s) => s.demuxResult);
  const ampliconLengthEstimate = useMameAppStore((s) => s.ampliconLengthEstimate);
  const setParams = useMameAppStore((s) => s.setParams);
  const runDemuxAndFilter = useMameAppStore((s) => s.runDemuxAndFilter);

  function updateRaw(partial: Partial<typeof rawRunParams>) {
    setParams({ rawRunParams: partial });
  }

  return (
    <fieldset
      className="mt-3 space-y-3 rounded-md border border-border p-3"
      aria-label="Raw run demux and filter options"
    >
      <legend className="px-1 text-caption font-semibold uppercase tracking-wide text-muted-foreground">
        Raw Run Options
      </legend>

      {/* Custom barcodes path */}
      <div className="space-y-1">
        <Label
          htmlFor="custom-barcodes-path"
          className="text-caption font-medium uppercase tracking-wide text-muted-foreground"
        >
          Custom Barcodes (xlsx or csv)
        </Label>
        <Input
          id="custom-barcodes-path"
          type="text"
          value={rawRunParams.customBarcodesPath}
          onChange={(e) => updateRaw({ customBarcodesPath: e.target.value })}
          placeholder="/path/to/reference.xlsx"
          className="h-8 min-w-0 text-xs"
          aria-label="Custom barcodes file path (xlsx or csv)"
          disabled={isDemuxing}
        />
      </div>

      {/* Sequencing summary path */}
      <div className="space-y-1">
        <Label
          htmlFor="seq-summary-path"
          className="text-caption font-medium uppercase tracking-wide text-muted-foreground"
        >
          Sequencing Summary (optional)
        </Label>
        <Input
          id="seq-summary-path"
          type="text"
          value={rawRunParams.sequencingSummaryPath}
          onChange={(e) => updateRaw({ sequencingSummaryPath: e.target.value })}
          placeholder="sequencing_summary_*.txt"
          className="h-8 min-w-0 text-xs"
          aria-label="Sequencing summary file path (optional)"
          disabled={isDemuxing}
        />
      </div>

      {/* Amplicon length — target + tolerance */}
      <div className="space-y-2">
        <div className="space-y-1">
          <Label
            htmlFor="target-amplicon-length"
            className="text-caption font-medium uppercase tracking-wide text-muted-foreground"
          >
            Target Amplicon Length (bp)
          </Label>
          <Input
            id="target-amplicon-length"
            type="number"
            step="1"
            value={rawRunParams.targetLength ?? ""}
            onChange={(e) => {
              const raw = e.target.value;
              updateRaw({
                targetLength: raw === "" ? null : Math.round(Number(raw)),
              });
            }}
            placeholder="Leave blank to auto-detect"
            className="h-8 min-w-0 text-xs"
            aria-label="Target amplicon length in bp; leave blank to auto-detect"
            disabled={isDemuxing}
          />
          {/* Show auto-detect result from previous run */}
          {rawRunParams.targetLength === null && (
            <AmpliconLengthBadge
              estimate={
                demuxResult?.amplicon_length_estimate ?? ampliconLengthEstimate
              }
            />
          )}
        </div>

        {/* Length tolerance slider */}
        <div className="space-y-1">
          <div className="flex items-center justify-between">
            <Label
              htmlFor="length-tolerance"
              className="text-caption font-medium uppercase tracking-wide text-muted-foreground"
            >
              Length Tolerance ± bp
            </Label>
            <span
              className="text-caption font-medium text-foreground"
              aria-label={`Length tolerance: ±${rawRunParams.lengthToleranceBp} bp`}
            >
              ±{rawRunParams.lengthToleranceBp}
            </span>
          </div>
          <input
            id="length-tolerance"
            type="range"
            min={5}
            max={200}
            step={5}
            value={rawRunParams.lengthToleranceBp}
            onChange={(e) => updateRaw({ lengthToleranceBp: Number(e.target.value) })}
            disabled={isDemuxing}
            className="w-full cursor-pointer accent-primary disabled:cursor-not-allowed disabled:opacity-50"
            aria-label={`Length tolerance: ±${rawRunParams.lengthToleranceBp} bp`}
          />
        </div>
      </div>

      {/* Quality thresholds */}
      <div className="grid gap-3 sm:grid-cols-2">
        <NumericField
          id="min-qscore"
          label="Min Q-score"
          value={rawRunParams.minQscore}
          step="0.5"
          onChange={(v) => updateRaw({ minQscore: v })}
          disabled={isDemuxing}
        />
        <NumericField
          id="min-barcode-score"
          label="Min Barcode Score"
          value={rawRunParams.minBarcodeScore}
          step="1"
          onChange={(v) => updateRaw({ minBarcodeScore: v })}
          disabled={isDemuxing}
        />
      </div>

      {/* Linked adapter trim toggle */}
      <div className="space-y-2 rounded-md bg-muted/50 p-2">
        <div className="flex items-center justify-between">
          <Label
            htmlFor="linked-trim-toggle"
            className="text-caption font-medium uppercase tracking-wide text-muted-foreground"
          >
            Trim Adapters
          </Label>
          <button
            id="linked-trim-toggle"
            type="button"
            role="switch"
            aria-checked={rawRunParams.linkedTrim}
            aria-label="Trim forward barcode and universal reverse primer from reads"
            disabled={isDemuxing}
            onClick={() => updateRaw({ linkedTrim: !rawRunParams.linkedTrim })}
            className={cn(
              "relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
              "disabled:cursor-not-allowed disabled:opacity-50",
              rawRunParams.linkedTrim ? "bg-primary" : "bg-input",
            )}
          >
            <span
              aria-hidden="true"
              className={cn(
                "pointer-events-none inline-block h-4 w-4 rounded-full bg-background shadow-sm ring-0 transition-transform",
                rawRunParams.linkedTrim ? "translate-x-4" : "translate-x-0",
              )}
            />
          </button>
        </div>
        {rawRunParams.linkedTrim && (
          <div className="space-y-1">
            <Label
              htmlFor="rev-primer"
              className="text-caption font-medium uppercase tracking-wide text-muted-foreground"
            >
              Universal Rev Primer (5′→3′)
            </Label>
            <Input
              id="rev-primer"
              type="text"
              value={rawRunParams.revPrimerUniversal}
              onChange={(e) =>
                updateRaw({ revPrimerUniversal: e.target.value.trim().toUpperCase() })
              }
              placeholder="ACGT..."
              className="h-8 min-w-0 font-mono text-xs"
              aria-label="Universal reverse primer sequence 5 prime to 3 prime"
              disabled={isDemuxing}
            />
          </div>
        )}
      </div>

      {/* Normalize headers toggle */}
      <div className="flex items-center justify-between">
        <Label
          htmlFor="normalize-headers-toggle"
          className="text-caption font-medium uppercase tracking-wide text-muted-foreground"
        >
          Normalize Headers
        </Label>
        <button
          id="normalize-headers-toggle"
          type="button"
          role="switch"
          aria-checked={rawRunParams.normalizeHeaders}
          aria-label="Write well name as FASTA header instead of ONT read ID"
          disabled={isDemuxing}
          onClick={() => updateRaw({ normalizeHeaders: !rawRunParams.normalizeHeaders })}
          className={cn(
            "relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
            "disabled:cursor-not-allowed disabled:opacity-50",
            rawRunParams.normalizeHeaders ? "bg-primary" : "bg-input",
          )}
        >
          <span
            aria-hidden="true"
            className={cn(
              "pointer-events-none inline-block h-4 w-4 rounded-full bg-background shadow-sm ring-0 transition-transform",
              rawRunParams.normalizeHeaders ? "translate-x-4" : "translate-x-0",
            )}
          />
        </button>
      </div>

      {/* Progress bar */}
      {isDemuxing && (
        <div role="status" aria-live="polite" className="space-y-1">
          <div
            className="h-1.5 w-full overflow-hidden rounded-full bg-muted"
            aria-label="Demux progress"
          >
            <div
              className="h-full bg-primary transition-all"
              style={{ width: `${demuxProgress}%` }}
              aria-valuenow={demuxProgress}
              aria-valuemin={0}
              aria-valuemax={100}
              role="progressbar"
            />
          </div>
          <p className="text-caption text-muted-foreground">{demuxMessage}</p>
        </div>
      )}

      {/* Demux result summary */}
      {!isDemuxing && demuxResult !== null && (
        <div
          role="status"
          aria-live="polite"
          className="space-y-1 rounded-md bg-muted px-3 py-2 text-caption text-muted-foreground"
        >
          <div>
            <span className="font-medium text-foreground">Demux complete:</span>{" "}
            {demuxResult.n_assigned.toLocaleString()} reads assigned /{" "}
            {demuxResult.n_input_reads.toLocaleString()} total (
            {demuxResult.backend})
          </div>
          {demuxResult.amplicon_length_estimate !== null && (
            <AmpliconLengthBadge estimate={demuxResult.amplicon_length_estimate} />
          )}
          <div className="text-caption text-muted-foreground">
            Length filter: {demuxResult.length_filter_mode.replace("_", " ")}
          </div>
        </div>
      )}

      {/* Run demux button */}
      <Button
        type="button"
        size="sm"
        className="w-full text-xs"
        onClick={() => void runDemuxAndFilter()}
        disabled={
          isDemuxing ||
          !rawRunParams.customBarcodesPath ||
          (rawRunParams.linkedTrim && !rawRunParams.revPrimerUniversal)
        }
        aria-busy={isDemuxing}
        aria-label="Run demux and quality filter on raw run folder"
      >
        {isDemuxing ? "Demuxing…" : "Run Demux & Filter"}
      </Button>
    </fieldset>
  );
}

function ActivityDataSection() {
  const activeRoundId = useRoundStore((s) => s.active_round_id);

  const activityStore = useActivityStore();
  const isMerging = useStore(activityStore, (s: ActivitySlice) => s.isMerging);
  const isExporting = useStore(activityStore, (s: ActivitySlice) => s.isExporting);
  const mergeError = useStore(activityStore, (s: ActivitySlice) => s.mergeError);
  const exportError = useStore(activityStore, (s: ActivitySlice) => s.exportError);
  const mergeActivity = useStore(activityStore, (s: ActivitySlice) => s.mergeActivity);
  const exportEvolveproCsv = useStore(activityStore, (s: ActivitySlice) => s.exportEvolveproCsv);

  async function handleExport() {
    if (!activeRoundId) return;
    const filePath = await save({
      filters: [{ name: "CSV files", extensions: ["csv"] }],
      defaultPath: "evolvepro_export.csv",
      title: "Export EVOLVEpro CSV",
    });
    if (!filePath) return;
    await exportEvolveproCsv(activeRoundId, filePath);
  }

  return (
    <section
      className="space-y-3 pt-3 border-t border-border"
      aria-label="Activity data section"
    >
      <header>
        <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Activity Data
        </h4>
      </header>

      <ActivityUploadPanel />
      <WtWellEditor />

      <div className="space-y-2 pt-1">
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="w-full text-xs"
          onClick={() => activeRoundId && void mergeActivity(activeRoundId)}
          disabled={!activeRoundId || isMerging}
          aria-busy={isMerging}
          aria-label="Merge activity data with genotype"
        >
          {isMerging ? "Merging…" : "Merge with genotype"}
        </Button>

        {mergeError && (
          <div role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-caption text-destructive">
            {mergeError}
          </div>
        )}

        <Button
          type="button"
          size="sm"
          variant="outline"
          className="w-full text-xs"
          onClick={() => void handleExport()}
          disabled={!activeRoundId || isExporting}
          aria-busy={isExporting}
          aria-label="Export EVOLVEpro CSV"
        >
          {isExporting ? "Exporting…" : "Export EVOLVEpro CSV"}
        </Button>

        {exportError && (
          <div role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-caption text-destructive">
            {exportError}
          </div>
        )}

        {activeRoundId && (
          <RoundHandoffButton round_id={activeRoundId} />
        )}
      </div>
    </section>
  );
}

export function ParameterPanel() {
  const mode = useMameAppStore((s) => s.mode);
  const ingestMode = useMameAppStore((s) => s.ingestMode);
  const inputMode = useMameAppStore((s) => s.inputMode);
  const cdsStart = useMameAppStore((s) => s.cdsStart);
  const cdsEnd = useMameAppStore((s) => s.cdsEnd);
  const minFileSizeKb = useMameAppStore((s) => s.minFileSizeKb);
  const minFilteredDepth = useMameAppStore((s) => s.minFilteredDepth);
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
        {/* Analysis mode (amplicon/plasmid) */}
        <div className="space-y-1">
          <Label
            htmlFor="mode-select"
            className="text-caption font-medium uppercase tracking-wide text-muted-foreground"
          >
            Mode
          </Label>
          <Select
            value={mode}
            onValueChange={(value) =>
              setParams({ mode: value as "amplicon" | "plasmid" })
            }
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

        {/* Ingest mode (barcode/amplicon) — only shown for non-raw_run */}
        {inputMode !== "raw_run" && (
          <div className="space-y-1">
            <Label
              htmlFor="ingest-mode-select"
              className="text-caption font-medium uppercase tracking-wide text-muted-foreground"
            >
              Ingest
            </Label>
            <Select
              value={ingestMode}
              onValueChange={(value) =>
                setParams({ ingestMode: value as "barcode" | "amplicon" })
              }
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
        )}

        {/* Input mode (consensus / sorted_barcode / raw_run) */}
        <div className="space-y-1 sm:col-span-2">
          <Label
            htmlFor="input-mode-select"
            className="text-caption font-medium uppercase tracking-wide text-muted-foreground"
          >
            Input Source
          </Label>
          <Select
            value={inputMode}
            onValueChange={(value) =>
              setParams({ inputMode: value as InputMode })
            }
          >
            <SelectTrigger id="input-mode-select" className="h-8 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="consensus">
                {INPUT_MODE_LABELS.consensus}
              </SelectItem>
              <SelectItem value="sorted_barcode">
                {INPUT_MODE_LABELS.sorted_barcode}
              </SelectItem>
              <SelectItem value="raw_run">
                {INPUT_MODE_LABELS.raw_run}
              </SelectItem>
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

        {/* Min filtered depth (reads) — primary depth-based cutoff */}
        <div className="space-y-1 sm:col-span-2">
          <Label
            htmlFor="min-filtered-depth"
            className="text-caption font-medium uppercase tracking-wide text-muted-foreground"
          >
            최소 Filtered Depth (reads)
          </Label>
          <Input
            id="min-filtered-depth"
            type="number"
            step="1"
            min={1}
            value={Number.isFinite(minFilteredDepth) ? minFilteredDepth : ""}
            onChange={(e) => {
              const raw = e.target.value;
              if (raw === "") return;
              const n = Math.round(Number(raw));
              if (Number.isFinite(n) && n > 0) setParams({ minFilteredDepth: n });
            }}
            className="h-8 text-xs"
            aria-label="최소 filtered depth (reads). Length-window-filtered read count. ONT R10.4.1 consensus reaches Q35+ around 15× depth."
            title="Length-window-filtered read count. ONT R10.4.1 consensus reaches Q35+ around 15× depth."
          />
          <p className="text-caption text-muted-foreground">
            Length-window-filtered read count. ONT R10.4.1 consensus: Q35+ ~15×
          </p>
        </div>

        {/* Min File KB — legacy proxy cutoff (강등: 보조 표시) */}
        <div className="space-y-1 sm:col-span-2 rounded-md border border-dashed border-border/60 p-2">
          <Label
            htmlFor="min-file-kb"
            className="text-caption font-medium uppercase tracking-wide text-muted-foreground/60"
          >
            Legacy KB Cutoff (proxy)
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
            className="h-7 text-xs opacity-70"
            aria-label="Legacy min file size KB cutoff (proxy for read depth)"
            title="파일 크기 기반 proxy cutoff. 압축률·길이분포·라이브러리 변동에 영향받음. 보조 참고용."
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

      {/* Conditional raw-run sub-panel */}
      {inputMode === "raw_run" && <RawRunParamPanel />}

      <ActivityDataSection />
    </div>
  );
}

function NumericField({
  id,
  label,
  value,
  onChange,
  step,
  disabled,
}: {
  id: string;
  label: string;
  value: number;
  onChange: (value: number) => void;
  step?: string;
  disabled?: boolean;
}) {
  return (
    <div className="space-y-1">
      <Label
        htmlFor={id}
        className="text-caption font-medium uppercase tracking-wide text-muted-foreground"
      >
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
        disabled={disabled}
      />
    </div>
  );
}
