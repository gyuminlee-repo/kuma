import { useTranslation } from "react-i18next";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import { save } from "@tauri-apps/plugin-dialog";
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
import { ActivityUploadPanel } from "./ActivityUploadPanel";
import { WtWellEditor } from "@/components/mame/dialogs/WtWellEditor";
import { RoundHandoffButton } from "@/components/round/RoundHandoffButton";
import { RoundSummaryPanel } from "@/components/round/RoundSummaryPanel";
import { useActivityStore, type ActivitySlice } from "@/store/mame/activitySlice";
import type { RoundMetrics } from "@/types/round-metrics";
import type { MergeStats, SwapWarning } from "@/types/mame/activity";
import { useRoundStore } from "@/store/round/roundSlice";
import { useStore } from "zustand";
import { isExportBlockedError } from "@/lib/errors";
import { useKumaProject } from "@/state/projectContext";
import { useState } from "react";
import { checkMameInputSize, type InputSizeLevel } from "@/lib/inputThresholds";
import { InputSizeWarningDialog } from "@/components/dialogs/InputSizeWarningDialog";

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

      <p className="text-caption text-muted-foreground">
        {t("mame.parameters.barcodeRunsAutomatically")}
      </p>
    </fieldset>
  );
}


// ---------------------------------------------------------------------------
// ExportBlockedErrorDisplay — 라벨 교체 감지 시 강화 에러 표시.
// ---------------------------------------------------------------------------

function ExportBlockedErrorDisplay({
  warnings,
}: {
  warnings: SwapWarning[];
}) {
  const allVariants = Array.from(
    new Set(warnings.flatMap((w) => w.variants))
  );

  return (
    <div
      role="alert"
      className="rounded-md border border-red-200 bg-red-50 px-3 py-2.5 text-xs dark:border-red-800 dark:bg-red-950"
    >
      <p className="font-semibold text-red-800 dark:text-red-300">
        내보내기 차단 — 라벨 교체 감지
      </p>
      {allVariants.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {allVariants.map((v) => (
            <code
              key={v}
              className="rounded bg-red-100 px-1 py-0.5 font-mono text-[10px] text-red-700 dark:bg-red-900 dark:text-red-200"
            >
              {v}
            </code>
          ))}
        </div>
      )}
      <p className="mt-1.5 text-red-700 dark:text-red-400">
        이전 라운드 EVOLVEpro 결과와 비교해 같은 활성값을 가진 변이의 라벨 매핑을 확인하세요.
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Demo helper — builds a synthetic RoundMetrics from MergeStats.
// Used when no backend RPC is available (5/12 demo, Option B).
// Clearly labelled "(demo)" in the panel header to avoid confusion with real data.
// ---------------------------------------------------------------------------

function buildDemoMetrics(stats: MergeStats, roundId: string): RoundMetrics {
  const hitRate = stats.n_ngs_success > 0
    ? stats.n_ngs_success / stats.n_with_genotype
    : 0;
  const cumulativeBeneficial = Math.max(0, stats.n_ngs_success - stats.n_wt);
  const kThroughput = Math.ceil((-1 + Math.sqrt(1 + 8 * cumulativeBeneficial)) / 2);
  return {
    round_id: roundId,
    computed_at: new Date().toISOString(),
    cumulative_beneficial: cumulativeBeneficial,
    K_throughput: kThroughput,
    delta_best_ema: 0.05,
    sigma_assay: stats.n_wt >= 4 ? 0.03 : null,
    r: stats.n_wt >= 4 ? stats.n_wt : 1,
    hit_rates: [hitRate],
    top_k_positions_n: [],
    top_k_positions_n1: [],
    top_k_positions: [],
    active_residues: [],
    unused_beneficial_count: Math.max(0, cumulativeBeneficial - 1),
    T1: cumulativeBeneficial >= kThroughput,
    T2: false,
    T3: false,
    T4: false,
    T_active: false,
    T_unused: cumulativeBeneficial > 1,
  }
}

function ActivityDataSection() {
  const activeRoundId = useRoundStore((s) => s.active_round_id);

  const activityStore = useActivityStore();
  const isMerging = useStore(activityStore, (s: ActivitySlice) => s.isMerging);
  const isExporting = useStore(activityStore, (s: ActivitySlice) => s.isExporting);
  const mergeError = useStore(activityStore, (s: ActivitySlice) => s.mergeError);
  const lastMergeStats = useStore(activityStore, (s: ActivitySlice) => s.lastMergeStats);
  const lastReplicateStats = useStore(activityStore, (s: ActivitySlice) => s.lastReplicateStats);
  const exportError = useStore(activityStore, (s: ActivitySlice) => s.exportError);
  const mergeActivity = useStore(activityStore, (s: ActivitySlice) => s.mergeActivity);
  const mergeForEvolvepro = useStore(activityStore, (s: ActivitySlice) => s.mergeForEvolvepro);
  const exportEvolveproCsv = useStore(activityStore, (s: ActivitySlice) => s.exportEvolveproCsv);

  const hasActivity = useRoundStore(
    (s) =>
      (s.rounds.find((r) => r.id === activeRoundId)?.activity?.records?.length ?? 0) > 0
  );

  // §19 입력 크기 경고 상태
  const [mameSizeWarning, setMameSizeWarning] = useState<{
    level: InputSizeLevel;
    message: string;
    pendingAction: () => void;
  } | null>(null);

  const activityRowCount = useRoundStore(
    (s) => s.rounds.find((r) => r.id === activeRoundId)?.activity?.records?.length ?? 0
  );

  /** §19: 크기 검사 후 경고 모달 표시 또는 즉시 실행 */
  function guardedMerge(action: () => void) {
    const check = checkMameInputSize({ rowCount: activityRowCount });
    if (check.level !== "ok") {
      setMameSizeWarning({ level: check.level, message: check.message, pendingAction: action });
      return;
    }
    action();
  }
  const roundN = useRoundStore(
    (s) => s.rounds.find((r) => r.id === activeRoundId)?.n ?? null
  );
  const project = useKumaProject();

  async function handleExport() {
    if (!activeRoundId) return;
    let defaultPath = "evolvepro_export.csv";
    if (project && !project.scratch) {
      const dir = project.path.replace(/\\/g, "/").replace(/\/$/, "");
      const analysisDir = `${dir}/analysis`;
      defaultPath =
        roundN !== null
          ? `${analysisDir}/round${roundN}_evolvepro.csv`
          : `${analysisDir}/evolvepro_export.csv`;
    }
    const filePath = await save({
      filters: [{ name: "CSV files", extensions: ["csv"] }],
      defaultPath,
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
          onClick={() => activeRoundId && guardedMerge(() => void mergeActivity(activeRoundId))}
          disabled={!activeRoundId || isMerging}
          aria-busy={isMerging}
          aria-label="Merge activity data with genotype"
        >
          {isMerging ? "Merging…" : "Merge with genotype"}
        </Button>

        {/* v0.3 신규 병합 버튼 */}
        <p className="text-[10px] text-muted-foreground">
          v0.3: 라벨 교체 가드 + replicate 병합 통합. 5/12 데모는 기존 버튼 사용.
        </p>
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="w-full text-xs"
          onClick={() => activeRoundId && guardedMerge(() => void mergeForEvolvepro(activeRoundId))}
          disabled={!activeRoundId || isMerging || !hasActivity}
          aria-busy={isMerging}
          aria-label="v0.3 신규 RPC로 활성 데이터 병합 + 라벨 교체 가드 실행"
        >
          {isMerging ? "병합 중…" : "EVOLVEpro용 병합 (v0.3)"}
        </Button>

        {mergeError && (
          isExportBlockedError(mergeError) ? (
            <ExportBlockedErrorDisplay
              warnings={lastMergeStats?.warnings ?? []}
            />
          ) : (
            <div role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-caption text-destructive">
              {mergeError}
            </div>
          )
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
          isExportBlockedError(exportError) ? (
            <ExportBlockedErrorDisplay
              warnings={lastMergeStats?.warnings ?? []}
            />
          ) : (
            <div role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-caption text-destructive">
              {exportError}
            </div>
          )
        )}

        {activeRoundId && (
          <RoundHandoffButton round_id={activeRoundId} />
        )}
      </div>

      {/*
        RoundSummaryPanel — calibration mode signal display.
        5/12: metrics injected from lastMergeStats via buildDemoMetrics (Option B).
        v0.3: replace with backend strategy.compute_signals RPC.
        Spec: §12-A.5 (calibration mode), §12-A.6 (5/12 scope).
      */}
      <RoundSummaryPanel
        metrics={lastMergeStats && activeRoundId
          ? buildDemoMetrics(lastMergeStats, activeRoundId)
          : null}
        demoMode={lastMergeStats != null}
        mergeStats={lastMergeStats}
        replicateStats={lastReplicateStats}
        className="pt-2 border-t border-border"
      />

      {/* §19 Performance Guardrails: mame 입력 크기 사전 경고 */}
      {mameSizeWarning && (
        <InputSizeWarningDialog
          open={mameSizeWarning !== null}
          level={mameSizeWarning.level}
          message={mameSizeWarning.message}
          onContinue={() => {
            const action = mameSizeWarning.pendingAction;
            setMameSizeWarning(null);
            action();
          }}
          onCancel={() => setMameSizeWarning(null)}
        />
      )}
    </section>
  );
}

export function ParameterPanel() {
  const { t } = useTranslation();
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
            {t("mame.parameters.mode")}
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
              {t("mame.parameters.ingest")}
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
            {t("mame.parameters.inputSource")}
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

        {/* Min filtered depth (reads) — primary depth-based cutoff */}
        <div className="space-y-1 sm:col-span-2">
          <Label
            htmlFor="min-filtered-depth"
            className="text-caption font-medium uppercase tracking-wide text-muted-foreground"
          >
            <span className="inline-flex items-center gap-1.5">
              최소 Filtered Depth (reads)
              <InlineHelp text="Length-window filter를 통과한 read 수 기준 cutoff입니다. FASTA 파일 크기보다 직접적인 depth 지표지만, 현재 판정 backend에는 아직 legacy KB cutoff가 전달됩니다." />
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
            aria-label="최소 filtered depth (reads). Length-window-filtered read count. ONT R10.4.1 consensus reaches Q35+ around 15× depth."
            title="Length-window-filtered read count. ONT R10.4.1 consensus reaches Q35+ around 15× depth."
          />
          <p className="text-caption text-muted-foreground">
            Length-window-filtered read count. ONT R10.4.1 consensus: Q35+ ~15×. KB cutoff와 1:1 자동 변환되지 않습니다.
          </p>
        </div>

        {/* Min File KB — legacy proxy cutoff (강등: 보조 표시) */}
        <div className="space-y-1 sm:col-span-2 rounded-md border border-dashed border-border/60 p-2">
          <Label
            htmlFor="min-file-kb"
            className="text-caption font-medium uppercase tracking-wide text-muted-foreground/60"
          >
            <span className="inline-flex items-center gap-1.5">
              Legacy KB Cutoff (proxy)
              <InlineHelp text="FASTA 파일 크기를 read depth의 대리값으로 쓰는 기존 cutoff입니다. read 길이, header 길이, line wrapping, consensus/intermediate 산출 방식에 따라 같은 read 수라도 KB가 달라져 Filtered Depth와 자동 동기화할 수 없습니다." />
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
          label={t("mame.parameters.manyCutoff")}
          value={manyCutoff}
          onChange={(value) => setParams({ manyCutoff: value })}
          helpText={t("mame.parameters.manyCutoffHelp")}
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
