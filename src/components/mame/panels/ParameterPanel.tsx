import { useState } from "react";
import { useTranslation } from "react-i18next";
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
import { InlineHelp } from "@/components/ui/InlineHelp";
import type { AmpliconLengthEstimate, DistributionStats } from "@/types/mame/models";
import type { InputMode } from "@/store/mame/slice-interfaces";

const METHOD_LABELS: Record<DistributionStats["suggested_method"], string> = {
  median_minus_2sigma: "median − 2σ",
  p05: "p05",
  kneedle: "knee",
  fixed_50: "floor 50",
};

const INPUT_MODE_I18N_KEYS: Record<InputMode, string> = {
  consensus: "mame.parameters.inputSourceConsensus",
  sorted_barcode: "mame.parameters.inputSourceSortedBarcode",
  raw_run: "mame.parameters.inputSourceRawRun",
};

function RecommendedCutoff({
  stats,
  onApply,
}: {
  stats: DistributionStats;
  onApply: (value: number) => void;
}) {
  const { t } = useTranslation();
  const methodLabel = METHOD_LABELS[stats.suggested_method];
  const bimodalTooltip = t("mame.parameters.bimodalTooltip");

  return (
    <div className="flex items-center gap-1.5">
      <span className="text-caption text-muted-foreground">
        {t("mame.parameters.recommendedCutoff", {
          value: stats.suggested_cutoff_kb.toFixed(1),
          method: methodLabel,
        })}
      </span>
      {stats.bimodal && (
        <span
          className="inline-flex cursor-help items-center text-warning"
          aria-label={bimodalTooltip}
          title={bimodalTooltip}
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
        aria-label={t("mame.parameters.applyCutoffAriaLabel", { kb: stats.suggested_cutoff_kb.toFixed(1) })}
      >
        {t("mame.parameters.useCutoffBtn")}
      </Button>
    </div>
  );
}

function AmpliconLengthBadge({
  estimate,
}: {
  estimate: AmpliconLengthEstimate | null;
}) {
  const { t } = useTranslation();
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
      aria-label={t("mame.parameters.autoDetectedAriaLabel", { length: estimate.detected_length, confidence: estimate.confidence, reads: estimate.n_sample_reads.toLocaleString() })}
    >
      <Dna size={11} aria-hidden="true" />
      {t("mame.parameters.autoDetected", { length: estimate.detected_length.toLocaleString() })}
      <span className="text-muted-foreground">
        (n={estimate.n_sample_reads.toLocaleString()}, {estimate.confidence})
      </span>
    </span>
  );
}

function RawRunParamPanel() {
  const { t } = useTranslation();
  const rawRunParams = useMameAppStore((s) => s.rawRunParams);
  const isDemuxing = useMameAppStore((s) => s.isDemuxing);
  const demuxProgress = useMameAppStore((s) => s.demuxProgress);
  const demuxMessage = useMameAppStore((s) => s.demuxMessage);
  const demuxResult = useMameAppStore((s) => s.demuxResult);
  const ampliconLengthEstimate = useMameAppStore((s) => s.ampliconLengthEstimate);
  const setParams = useMameAppStore((s) => s.setParams);

  function updateRaw(partial: Partial<typeof rawRunParams>) {
    setParams({ rawRunParams: partial });
  }

  return (
    <fieldset
      className="mt-3 space-y-3 rounded-md border border-border p-3"
      aria-label={t("mame.parameters.rawRunOptionsAriaLabel")}
    >
      <legend className="px-1 text-caption font-semibold uppercase tracking-wide text-muted-foreground">
        {t("mame.parameters.rawRunOptions")}
      </legend>

      {/* Amplicon length — target + tolerance */}
      <div className="space-y-2">
        <div className="space-y-1">
          <Label
            htmlFor="target-amplicon-length"
            className="text-caption font-medium uppercase tracking-wide text-muted-foreground"
          >
            <span className="inline-flex items-center gap-1.5">
              {t("mame.parameters.targetAmpliconLength")}
              <InlineHelp text={t("mame.parameters.targetAmpliconLengthHelp")} />
            </span>
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
            placeholder={t("mame.parameters.targetAmpliconLengthPlaceholder")}
            className="h-8 min-w-0 text-xs"
            aria-label={t("mame.parameters.targetAmpliconLengthAriaLabel")}
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
              <span className="inline-flex items-center gap-1.5">
                {t("mame.parameters.lengthTolerance")}
                <InlineHelp text={t("mame.parameters.lengthToleranceHelp")} />
              </span>
            </Label>
            <div className="flex items-center gap-1">
              <span className="text-caption font-medium text-foreground" aria-hidden="true">±</span>
              <Input
                type="number"
                min={5}
                max={200}
                step={1}
                value={rawRunParams.lengthToleranceBp}
                onChange={(e) => {
                  const raw = e.target.value;
                  if (raw === "") return;
                  const n = Number(raw);
                  if (!Number.isFinite(n)) return;
                  const clamped = Math.max(5, Math.min(200, Math.round(n)));
                  updateRaw({ lengthToleranceBp: clamped });
                }}
                disabled={isDemuxing}
                className="h-7 w-20 px-1.5 text-right text-xs"
                aria-label={t("mame.parameters.lengthToleranceAriaLabel", { bp: rawRunParams.lengthToleranceBp })}
              />
            </div>
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
            aria-label={t("mame.parameters.lengthToleranceAriaLabel", { bp: rawRunParams.lengthToleranceBp })}
          />
        </div>
      </div>

      {/* Quality thresholds */}
      <div className="grid gap-3 sm:grid-cols-2">
        <NumericField
          id="min-qscore"
          label={t("mame.parameters.minQscore")}
          value={rawRunParams.minQscore}
          step="0.5"
          onChange={(v) => updateRaw({ minQscore: v })}
          disabled={isDemuxing}
          helpText={t("mame.parameters.minQscoreHelp")}
        />
        <NumericField
          id="min-barcode-score"
          label={t("mame.parameters.minBarcodeScore")}
          value={rawRunParams.minBarcodeScore}
          step="1"
          onChange={(v) => updateRaw({ minBarcodeScore: v })}
          disabled={isDemuxing}
          helpText={t("mame.parameters.minBarcodeScoreHelp")}
        />
      </div>

      {/* Linked adapter trim toggle */}
      <div className="space-y-2 rounded-md bg-muted/50 p-2">
        <div className="flex items-center justify-between">
          <Label
            htmlFor="linked-trim-toggle"
            className="text-caption font-medium uppercase tracking-wide text-muted-foreground"
          >
            <span className="inline-flex items-center gap-1.5">
              {t("mame.parameters.trimAdapters")}
              <InlineHelp text={t("mame.parameters.trimAdaptersHelp")} />
            </span>
          </Label>
          <button
            id="linked-trim-toggle"
            type="button"
            role="switch"
            aria-checked={rawRunParams.linkedTrim}
            aria-label={t("mame.parameters.trimAdaptersAriaLabel")}
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
              <span className="inline-flex items-center gap-1.5">
                {t("mame.parameters.universalRevPrimer")}
                <InlineHelp text={t("mame.parameters.universalRevPrimerHelp")} />
              </span>
            </Label>
            <Input
              id="rev-primer"
              type="text"
              value={rawRunParams.revPrimerUniversal}
              onChange={(e) =>
                updateRaw({ revPrimerUniversal: e.target.value.trim().toUpperCase() })
              }
              placeholder={t("mame.parameters.revPrimerPlaceholder")}
              className="h-8 min-w-0 font-mono text-xs"
              aria-label={t("mame.parameters.universalRevPrimerAriaLabel")}
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
          <span className="inline-flex items-center gap-1.5">
            {t("mame.parameters.normalizeHeaders")}
            <InlineHelp text={t("mame.parameters.normalizeHeadersHelp")} />
          </span>
        </Label>
        <button
          id="normalize-headers-toggle"
          type="button"
          role="switch"
          aria-checked={rawRunParams.normalizeHeaders}
          aria-label={t("mame.parameters.normalizeHeadersAriaLabel")}
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
            aria-label={t("mame.parameters.demuxProgressAriaLabel")}
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
            <span className="font-medium text-foreground">{t("mame.parameters.demuxComplete")}</span>{" "}
            {t("mame.parameters.demuxCompleteReads", {
              assigned: demuxResult.n_assigned.toLocaleString(),
              total: demuxResult.n_input_reads.toLocaleString(),
              backend: demuxResult.backend,
            })}
          </div>
          {demuxResult.amplicon_length_estimate !== null && (
            <AmpliconLengthBadge estimate={demuxResult.amplicon_length_estimate} />
          )}
          <div className="text-caption text-muted-foreground">
            {t("mame.parameters.lengthFilter", { mode: demuxResult.length_filter_mode.replace("_", " ") })}
          </div>
        </div>
      )}

      <p className="text-caption text-muted-foreground">
        {t("mame.parameters.barcodeRunsAutomatically")}
      </p>
    </fieldset>
  );
}



export function ParameterPanel() {
  const { t } = useTranslation();
  const mode = useMameAppStore((s) => s.mode);
  const ingestMode = useMameAppStore((s) => s.ingestMode);
  const inputMode = useMameAppStore((s) => s.inputMode);
  const cdsStart = useMameAppStore((s) => s.cdsStart);
  const cdsEnd = useMameAppStore((s) => s.cdsEnd);
  const analyzeCdsCandidates = useMameAppStore((s) => s.analyzeCdsCandidates);
  const selectedAnalyzeCdsIndex = useMameAppStore((s) => s.selectedAnalyzeCdsIndex);
  const setSelectedAnalyzeCdsIndex = useMameAppStore((s) => s.setSelectedAnalyzeCdsIndex);
  const referencePath = useMameAppStore((s) => s.referencePath);
  const minFileSizeKb = useMameAppStore((s) => s.minFileSizeKb);
  const minFilteredDepth = useMameAppStore((s) => s.minFilteredDepth);
  const manyCutoff = useMameAppStore((s) => s.manyCutoff);
  const distributionStats = useMameAppStore((s) => s.distributionStats);
  const setParams = useMameAppStore((s) => s.setParams);
  const [showLegacyOptions, setShowLegacyOptions] = useState(false);

  return (
    <div className="rounded-lg border border-border bg-background p-4 space-y-3">
      <header>
        <h3 className="text-sm font-semibold text-foreground">{t("mame.parameters.title")}</h3>
        <p className="mt-1 text-xs text-muted-foreground">
          {t("mame.parameters.subtitle")}
        </p>
      </header>

      <div className="grid gap-3 sm:grid-cols-2">
        {/* Analysis mode (amplicon/plasmid) */}
        <div className="space-y-1">
          <Label
            htmlFor="mode-select"
            className="text-caption font-medium uppercase tracking-wide text-muted-foreground"
          >
            <span className="inline-flex items-center gap-1.5">
              {t("mame.parameters.mode")}
              <InlineHelp text={t("mame.parameters.modeHelp")} />
            </span>
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
              <SelectItem value="amplicon" title={t("mame.parameters.modeAmpliconTitle")}>amplicon</SelectItem>
              <SelectItem value="plasmid" title={t("mame.parameters.modePlasmidTitle")}>plasmid</SelectItem>
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
              <span className="inline-flex items-center gap-1.5">
                {t("mame.parameters.ingest")}
                <InlineHelp text={t("mame.parameters.ingestHelp")} />
              </span>
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
                <SelectItem value="barcode" title={t("mame.parameters.ingestBarcodeTitle")}>barcode</SelectItem>
                <SelectItem value="amplicon" title={t("mame.parameters.ingestAmpliconTitle")}>amplicon</SelectItem>
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
            <span className="inline-flex items-center gap-1.5">
              {t("mame.parameters.inputSource")}
              <InlineHelp text={t("mame.parameters.inputSourceHelp")} />
            </span>
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
              <SelectItem
                value="consensus"
                title={t("mame.parameters.inputModeConsensusTitle")}
              >
                {t(INPUT_MODE_I18N_KEYS.consensus)}
              </SelectItem>
              <SelectItem
                value="sorted_barcode"
                title={t("mame.parameters.inputModeSortedBarcodeTitle")}
              >
                {t(INPUT_MODE_I18N_KEYS.sorted_barcode)}
              </SelectItem>
              <SelectItem
                value="raw_run"
                title={t("mame.parameters.inputModeRawRunTitle")}
              >
                {t(INPUT_MODE_I18N_KEYS.raw_run)}
              </SelectItem>
            </SelectContent>
          </Select>
        </div>

        {analyzeCdsCandidates.length > 0 ? (
          <div className="space-y-1 sm:col-span-2">
            <Label
              htmlFor="analyze-cds-candidate"
              className="text-caption font-medium uppercase tracking-wide text-muted-foreground"
            >
              <span className="inline-flex items-center gap-1.5">
                {t("mame.parameters.cdsStart")} / {t("mame.parameters.cdsEnd")}
                <InlineHelp text={t("mame.parameters.cdsStartHelp")} />
              </span>
            </Label>
            <Select
              value={selectedAnalyzeCdsIndex === null ? "" : String(selectedAnalyzeCdsIndex)}
              onValueChange={(v) => {
                const i = Number(v);
                setSelectedAnalyzeCdsIndex(i);
                const cand = analyzeCdsCandidates[i];
                if (cand) {
                  setParams({ cdsStart: cand.start, cdsEnd: cand.end });
                }
              }}
            >
              <SelectTrigger id="analyze-cds-candidate" className="h-8 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {analyzeCdsCandidates.map((c, i) => {
                  const labelPart = c.label ? `[${c.label}] ` : "";
                  const tooltip = [
                    c.label ? `Label: ${c.label}` : "",
                    `Range: ${c.start}-${c.end}`,
                    `Length: ${c.aa_length} aa`,
                    `Source: ${c.source}`,
                  ]
                    .filter(Boolean)
                    .join("\n");
                  return (
                    <SelectItem key={i} value={String(i)} title={tooltip}>
                      {labelPart}{c.start}-{c.end} ({c.aa_length} aa)
                    </SelectItem>
                  );
                })}
              </SelectContent>
            </Select>
            <p className="text-caption text-muted-foreground/90">
              {referencePath
                ? `${analyzeCdsCandidates.length} CDS candidate(s) detected in reference`
                : ""}
            </p>
          </div>
        ) : (
          <>
            <NumericField
              id="cds-start"
              label={t("mame.parameters.cdsStart")}
              value={cdsStart}
              onChange={(value) => setParams({ cdsStart: value })}
              helpText={t("mame.parameters.cdsStartHelp")}
            />
            <NumericField
              id="cds-end"
              label={t("mame.parameters.cdsEnd")}
              value={cdsEnd}
              onChange={(value) => setParams({ cdsEnd: value })}
              helpText={t("mame.parameters.cdsEndHelp")}
            />
          </>
        )}

        {/* Min filtered depth (reads) — primary depth-based cutoff */}
        <div className="space-y-1 sm:col-span-2">
          <Label
            htmlFor="min-filtered-depth"
            className="text-caption font-medium uppercase tracking-wide text-muted-foreground"
          >
            <span className="inline-flex items-center gap-1.5">
              {t("mame.parameters.minFilteredDepth")}
              <InlineHelp text={t("mame.parameters.minFilteredDepthHelp")} />
            </span>
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
            aria-label={t("mame.parameters.minFilteredDepthAria")}
            title={t("mame.parameters.minFilteredDepthTitle")}
          />
          <p className="text-caption text-muted-foreground">
            {t("mame.parameters.minFilteredDepthFootnote")}
          </p>
        </div>

        {/* Legacy options toggle (deprecated KB cutoff hidden by default) */}
        <div className="sm:col-span-2">
          <button
            type="button"
            onClick={() => setShowLegacyOptions((v) => !v)}
            aria-expanded={showLegacyOptions}
            aria-controls="legacy-options-section"
            className="text-caption text-muted-foreground underline-offset-2 hover:text-foreground hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 rounded"
          >
            {showLegacyOptions ? "▾ " : "▸ "}
            {t("mame.parameters.legacyOptionsToggle")}
          </button>
          {showLegacyOptions && (
            <div
              id="legacy-options-section"
              className="mt-2 space-y-1 rounded-md border border-dashed border-border/60 p-2"
            >
              <p className="text-caption text-amber-700 dark:text-amber-400">
                {t("mame.parameters.legacyOptionsDeprecationWarning")}
              </p>
              <Label
                htmlFor="min-file-kb"
                className="text-caption font-medium uppercase tracking-wide text-muted-foreground/60"
              >
                <span className="inline-flex items-center gap-1.5">
                  {t("mame.parameters.legacyKbCutoff")}
                  <InlineHelp text={t("mame.parameters.legacyKbHelp")} />
                </span>
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
                aria-label={t("mame.parameters.legacyKbCutoffAriaLabel")}
                title={t("mame.parameters.legacyKbTooltip")}
              />
              {distributionStats !== null && (
                <RecommendedCutoff
                  stats={distributionStats}
                  onApply={(value) => setParams({ minFileSizeKb: value })}
                />
              )}
            </div>
          )}
        </div>

        <NumericField
          id="many-cutoff"
          label={t("mame.parameters.manyCutoff")}
          value={manyCutoff}
          onChange={(value) => setParams({ manyCutoff: value })}
          helpText={t("mame.parameters.manyCutoffHelp")}
        />
      </div>

      {/* Conditional raw-run sub-panel */}
      {inputMode === "raw_run" && <RawRunParamPanel />}
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
  helpText,
}: {
  id: string;
  label: string;
  value: number;
  onChange: (value: number) => void;
  step?: string;
  disabled?: boolean;
  helpText?: string;
}) {
  return (
    <div className="space-y-1">
      <Label
        htmlFor={id}
        className="text-caption font-medium uppercase tracking-wide text-muted-foreground"
      >
        <span className="inline-flex items-center gap-1.5">
          {label}
          {helpText && <InlineHelp text={helpText} />}
        </span>
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
