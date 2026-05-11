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

import { useState } from "react";
import { save } from "@tauri-apps/plugin-dialog";
import { useStore } from "zustand";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { ActivityUploadPanel } from "./ActivityUploadPanel";
import { WtWellEditor } from "@/components/mame/dialogs/WtWellEditor";
import { RoundHandoffButton } from "@/components/round/RoundHandoffButton";
import { RoundSummaryPanel } from "@/components/round/RoundSummaryPanel";
import { useActivityStore, type ActivitySlice } from "@/store/mame/activitySlice";
import { useRoundStore } from "@/store/round/roundSlice";
import { useMameAppStore } from "@/store/mame/mameAppStore";
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
  const allVariants = Array.from(new Set(warnings.flatMap((w) => w.variants)));
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
// Sub-tab: Ingest
// ---------------------------------------------------------------------------
function IngestTab() {
  const activeRoundId = useRoundStore((s) => s.active_round_id);
  const recordCount = useRoundStore(
    (s) => s.rounds.find((r) => r.id === activeRoundId)?.activity?.records?.length ?? 0,
  );
  return (
    <div className="space-y-4">
      <section className="space-y-2">
        <h3 className="text-sm font-semibold text-foreground">Upload activity data</h3>
        <p className="text-xs text-muted-foreground">
          Long-format CSV/Excel (well, replicate, value 컬럼)을 현재 Round에 적재합니다.
        </p>
        <ActivityUploadPanel />
      </section>

      <section className="space-y-2 border-t border-border pt-4">
        <h3 className="text-sm font-semibold text-foreground">WT well annotation</h3>
        <p className="text-xs text-muted-foreground">
          정규화 기준이 되는 wild-type well 위치를 지정합니다. Merge 전에 설정해야 합니다.
        </p>
        <WtWellEditor />
      </section>

      {recordCount > 0 && (
        <p className="text-caption text-muted-foreground" aria-live="polite">
          ✓ {recordCount} wells loaded
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-tab: Merge
// ---------------------------------------------------------------------------
function MergeTab() {
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

  function guardedMerge(action: () => void) {
    const check = checkMameInputSize({ rowCount: activityRowCount });
    if (check.level !== "ok") {
      setMameSizeWarning({ level: check.level, message: check.message, pendingAction: action });
      return;
    }
    action();
  }

  return (
    <div className="space-y-3">
      <header>
        <h3 className="text-sm font-semibold text-foreground">Merge activity with genotype</h3>
        <p className="text-xs text-muted-foreground">
          업로드된 activity와 Round의 genotype을 조인하고 WT로 정규화합니다.
        </p>
      </header>

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
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-tab: Export
// ---------------------------------------------------------------------------
function ExportTab() {
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

  async function handleExport() {
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
    <div className="space-y-3">
      <header>
        <h3 className="text-sm font-semibold text-foreground">Export EVOLVEpro xlsx</h3>
        <p className="text-xs text-muted-foreground">
          병합 결과를 EVOLVEpro 학습 입력 xlsx (data 시트: variant, y_pred, round_n, plate_id, well_id, activity_raw_mean, activity_raw_sd · excluded 시트: 제외 사유 포함)로 저장합니다.
        </p>
      </header>

      <Button
        type="button"
        size="sm"
        variant="outline"
        className="w-full text-xs"
        onClick={() => void handleExport()}
        disabled={!activeRoundId || isExporting}
        aria-busy={isExporting}
        aria-label="Export EVOLVEpro xlsx"
      >
        {isExporting ? "Exporting…" : "Export EVOLVEpro xlsx"}
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
    </div>
  );
}

// ---------------------------------------------------------------------------
// ActivityPanel — top-level phase wrapper
// ---------------------------------------------------------------------------
export function ActivityPanel() {
  const activityTab = useMameAppStore((s) => s.activityTab);
  const setActivityTab = useMameAppStore((s) => s.setActivityTab);

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-2xl space-y-4 p-4">
        <header>
          <h2 className="text-base font-semibold text-foreground">Activity data</h2>
          <p className="mt-1 text-xs text-muted-foreground">
            실험에서 측정한 well-level activity를 적재 → genotype과 병합 → EVOLVEpro 학습용 CSV로 내보냅니다. 각 단계는 시간상 분리되어 진행됩니다.
          </p>
        </header>

        <Tabs value={activityTab} onValueChange={(v) => setActivityTab(v as "ingest" | "merge" | "export")}>
          <TabsList>
            <TabsTrigger value="ingest">1. Ingest</TabsTrigger>
            <TabsTrigger value="merge">2. Merge</TabsTrigger>
            <TabsTrigger value="export">3. Export</TabsTrigger>
          </TabsList>
          <TabsContent value="ingest" className="mt-4">
            <IngestTab />
          </TabsContent>
          <TabsContent value="merge" className="mt-4">
            <MergeTab />
          </TabsContent>
          <TabsContent value="export" className="mt-4">
            <ExportTab />
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
