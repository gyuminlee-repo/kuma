/**
 * ActivityPanel — Top-level "3. Activity" phase
 *
 * Splits the previous ActivityDataSection (used inside Analyze phase sidebar)
 * into 3 sub-tabs that mirror the actual workflow timing:
 *   - Ingest:  long CSV/Excel upload + WT well annotation
 *   - Merge:   join activity ↔ genotype, replicate priority merge, WT normalisation
 *   - Export:  EVOLVEpro CSV save + round handoff
 *
 * Rationale: ingest → merge → export are temporally separated (days–weeks).
 * Sub-tabs let the user see exactly which step is pending without scrolling
 * through a single stacked section.
 */

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { save } from "@tauri-apps/plugin-dialog";
import { toast } from "sonner";
import { useStore } from "zustand";
import { validateMergeActivity } from "@/store/validation";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
} from "@/components/ui/dropdown-menu";
import { ChevronDown } from "lucide-react";
import { ActivityUploadPanel } from "./ActivityUploadPanel";
import { WtWellGrid } from "@/components/mame/panels/WtWellGrid";
import { RoundHandoffButton } from "@/components/round/RoundHandoffButton";
import { RoundSummaryPanel } from "@/components/round/RoundSummaryPanel";
import { useActivityStore, type ActivitySlice } from "@/store/mame/activitySlice";
import { useRoundStore } from "@/store/round/roundSlice";
import { useKumaProject } from "@/state/projectContext";
import { isExportBlockedError } from "@/lib/errors";
import { checkMameInputSize, type InputSizeLevel } from "@/lib/inputThresholds";
import { InputSizeWarningDialog } from "@/components/dialogs/InputSizeWarningDialog";
import type { MergeStats, SwapWarning } from "@/types/mame/activity";
import type { RoundMetrics } from "@/types/round-metrics";

// ---------------------------------------------------------------------------
// ExportBlockedErrorDisplay — 라벨 교체 감지 시 강화 에러 표시
// ---------------------------------------------------------------------------
function ExportBlockedErrorDisplay({ warnings }: { warnings: SwapWarning[] }) {
  const { t } = useTranslation();
  const allVariants = Array.from(new Set(warnings.flatMap((w) => w.variants)));
  return (
    <div
      role="alert"
      className="rounded-md border border-red-200 bg-red-50 px-3 py-2.5 text-xs dark:border-red-800 dark:bg-red-950"
    >
      <p className="font-semibold text-red-800 dark:text-red-300">
        {t("mame.activity.exportBlocked.title")}
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
        {t("mame.activity.exportBlocked.body")}
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Demo helper — builds synthetic RoundMetrics from MergeStats
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
  };
}

// ---------------------------------------------------------------------------
// Section: Ingest (upload + WT annotation)
// ---------------------------------------------------------------------------
export function IngestSection() {
  const { t } = useTranslation();
  const activeRoundId = useRoundStore((s) => s.active_round_id);
  const recordCount = useRoundStore(
    (s) => s.rounds.find((r) => r.id === activeRoundId)?.activity?.records?.length ?? 0,
  );
  return (
    <section className="space-y-4" aria-label={t("mame.activity.tabIngest")}>
      <div className="space-y-2">
        <h3 className="text-sm font-semibold text-foreground">{t("mame.activity.ingest.uploadHeading")}</h3>
        <p className="text-xs text-muted-foreground">{t("mame.activity.ingest.uploadDesc")}</p>
        <ActivityUploadPanel />
      </div>

      <div className="space-y-2 border-t border-border pt-4">
        <WtWellGrid />
      </div>

      {recordCount > 0 && (
        <p className="text-caption text-muted-foreground" aria-live="polite">
          {t("mame.activity.ingest.loaded", { count: recordCount })}
        </p>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Section: Merge
// ---------------------------------------------------------------------------
export function MergeSection() {
  const { t } = useTranslation();
  const activeRoundId = useRoundStore((s) => s.active_round_id);
  const activityStore = useActivityStore();
  const isMerging = useStore(activityStore, (s: ActivitySlice) => s.isMerging);
  const mergeError = useStore(activityStore, (s: ActivitySlice) => s.mergeError);
  const lastMergeStats = useStore(activityStore, (s: ActivitySlice) => s.lastMergeStats);
  const lastReplicateStats = useStore(activityStore, (s: ActivitySlice) => s.lastReplicateStats);
  const mergeActivity = useStore(activityStore, (s: ActivitySlice) => s.mergeActivity);
  const mergeForEvolvepro = useStore(activityStore, (s: ActivitySlice) => s.mergeForEvolvepro);

  const hasActivity = useRoundStore(
    (s) => (s.rounds.find((r) => r.id === activeRoundId)?.activity?.records?.length ?? 0) > 0,
  );
  const activityRowCount = useRoundStore(
    (s) => s.rounds.find((r) => r.id === activeRoundId)?.activity?.records?.length ?? 0,
  );

  const [mameSizeWarning, setMameSizeWarning] = useState<{
    level: InputSizeLevel;
    message: string;
    pendingAction: () => void;
  } | null>(null);

  function guardedMerge(action: () => void, requireActivity: boolean) {
    // PI 2026-05-15 (Item 2): activeRound·activity 누락 시 toast.warning.
    const check = validateMergeActivity({
      activeRoundId,
      hasActivity: requireActivity ? hasActivity : true,
    });
    if (!check.ok) {
      toast.warning(t("validation.actionBlockedTitle"), {
        description: check.missing.map((k) => t(k)).join("\n"),
      });
      return;
    }
    const sizeCheck = checkMameInputSize({ rowCount: activityRowCount });
    if (sizeCheck.level !== "ok") {
      setMameSizeWarning({ level: sizeCheck.level, message: sizeCheck.message, pendingAction: action });
      return;
    }
    action();
  }

  return (
    <section className="space-y-3 border-t border-border pt-4" aria-label={t("mame.activity.tabMerge")}>
      <header>
        <h3 className="text-sm font-semibold text-foreground">{t("mame.activity.merge.heading")}</h3>
        <p className="text-xs text-muted-foreground">{t("mame.activity.merge.desc")}</p>
      </header>

      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="w-full text-xs"
            disabled={isMerging}
            aria-busy={isMerging}
            aria-label={t("mame.activity.merge.btnCombined")}
          >
            <span className="flex w-full items-center justify-between gap-2">
              <span>
                {isMerging
                  ? t("mame.activity.merge.btnCombinedBusy")
                  : t("mame.activity.merge.btnCombined")}
              </span>
              <ChevronDown size={12} aria-hidden="true" />
            </span>
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="w-[var(--radix-dropdown-menu-trigger-width)]">
          <DropdownMenuItem
            onClick={() =>
              guardedMerge(
                () => activeRoundId && void mergeActivity(activeRoundId),
                false,
              )
            }
            disabled={isMerging}
            aria-label={t("mame.activity.merge.btnLegacy")}
          >
            {t("mame.activity.merge.menuLegacy")}
          </DropdownMenuItem>
          <DropdownMenuItem
            onClick={() =>
              guardedMerge(
                () => activeRoundId && void mergeForEvolvepro(activeRoundId),
                true,
              )
            }
            disabled={isMerging}
            aria-label={t("mame.activity.merge.btnEvolveproAria")}
          >
            {t("mame.activity.merge.menuEvolvepro")}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      {mergeError && (
        isExportBlockedError(mergeError) ? (
          <ExportBlockedErrorDisplay warnings={lastMergeStats?.warnings ?? []} />
        ) : (
          <div role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-caption text-destructive">
            {mergeError}
          </div>
        )
      )}

      <RoundSummaryPanel
        metrics={lastMergeStats && activeRoundId
          ? buildDemoMetrics(lastMergeStats, activeRoundId)
          : null}
        demoMode={lastMergeStats != null}
        mergeStats={lastMergeStats}
        replicateStats={lastReplicateStats}
        className="pt-2 border-t border-border"
      />

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

// ---------------------------------------------------------------------------
// Section: Export
// ---------------------------------------------------------------------------
export function ExportSection() {
  const { t } = useTranslation();
  const activeRoundId = useRoundStore((s) => s.active_round_id);
  const roundN = useRoundStore(
    (s) => s.rounds.find((r) => r.id === activeRoundId)?.n ?? null,
  );
  const activityStore = useActivityStore();
  const isExporting = useStore(activityStore, (s: ActivitySlice) => s.isExporting);
  const exportError = useStore(activityStore, (s: ActivitySlice) => s.exportError);
  const lastMergeStats = useStore(activityStore, (s: ActivitySlice) => s.lastMergeStats);
  const exportEvolveproXlsx = useStore(activityStore, (s: ActivitySlice) => s.exportEvolveproXlsx);
  const project = useKumaProject();

  const hasActivity = useRoundStore(
    (s) => (s.rounds.find((r) => r.id === activeRoundId)?.activity?.records?.length ?? 0) > 0,
  );

  async function handleExport() {
    // PI 2026-05-15 (Item 2): round/activity 누락 시 toast.warning.
    const check = validateMergeActivity({ activeRoundId, hasActivity });
    if (!check.ok) {
      toast.warning(t("validation.actionBlockedTitle"), {
        description: check.missing.map((k) => t(k)).join("\n"),
      });
      return;
    }
    if (!activeRoundId) return;
    let defaultPath = "evolvepro_export.xlsx";
    if (project && !project.scratch) {
      const dir = project.path.replace(/\\/g, "/").replace(/\/$/, "");
      const analysisDir = `${dir}/analysis`;
      defaultPath =
        roundN !== null
          ? `${analysisDir}/round${roundN}_evolvepro.xlsx`
          : `${analysisDir}/evolvepro_export.xlsx`;
    }
    const filePath = await save({
      filters: [{ name: "Excel files", extensions: ["xlsx"] }],
      defaultPath,
      title: "Export EVOLVEpro xlsx",
    });
    if (!filePath) return;
    await exportEvolveproXlsx(activeRoundId, filePath);
  }

  return (
    <section className="space-y-3 border-t border-border pt-4" aria-label={t("mame.activity.tabExport")}>
      <header>
        <h3 className="text-sm font-semibold text-foreground">{t("mame.activity.export.heading")}</h3>
        <p className="text-xs text-muted-foreground">{t("mame.activity.export.desc")}</p>
      </header>

      <Button
        type="button"
        size="sm"
        variant="outline"
        className="w-full text-xs"
        onClick={() => void handleExport()}
        disabled={isExporting}
        aria-busy={isExporting}
        aria-label={t("mame.activity.export.btn")}
      >
        {isExporting ? t("mame.activity.export.btnBusy") : t("mame.activity.export.btn")}
      </Button>

      {exportError && (
        isExportBlockedError(exportError) ? (
          <ExportBlockedErrorDisplay warnings={lastMergeStats?.warnings ?? []} />
        ) : (
          <div role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-caption text-destructive">
            {exportError}
          </div>
        )
      )}

      {activeRoundId && <RoundHandoffButton round_id={activeRoundId} />}
    </section>
  );
}

// ---------------------------------------------------------------------------
// ActivityPanel — top-level phase wrapper (single linear flow)
// ---------------------------------------------------------------------------
export function ActivityPanel() {
  const { t } = useTranslation();

  // Auto-create a round when entering the Activity phase if none exists.
  // Without this, uploadActivityFile is permanently disabled because
  // active_round_id stays null until something calls addRound.
  const activeRoundId = useRoundStore((s) => s.active_round_id);
  const addRound = useRoundStore((s) => s.addRound);
  useEffect(() => {
    if (activeRoundId === null) {
      addRound({ plate_meta: { plates: [] } });
    }
  }, [activeRoundId, addRound]);

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-2xl space-y-6 p-4">
        <header>
          <h2 className="text-base font-semibold text-foreground">{t("mame.activity.title")}</h2>
          <p className="mt-1 text-xs text-muted-foreground">{t("mame.activity.subtitle")}</p>
        </header>

        <IngestSection />
        <MergeSection />
        <ExportSection />
      </div>
    </div>
  );
}
