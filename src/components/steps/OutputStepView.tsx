/**
 * OutputStepView — "output" major step (Phase G #12).
 *
 * [source: spec Phase G — Report → Output rename + Plate Map 병합 (#12)]
 * [source: spec Phase G — Output 좌우 split: Summary(좌) + PlateMap(우) (#10, #11)]
 * [source: spec Phase G — 통계 4 카드는 단순 텍스트 라인으로 축소 (#10/#11)]
 * [source: spec Phase G — Output maxWidth="full" (#4)]
 * [source: spec patch-260514 #7 — primer/plate 영역 drag resize + sidebar toggle]
 *
 * Layout: drag-resizable horizontal split — 좌=Summary, 우=PlateMap.
 * - persist split ratio at `localStorage["kuro.output.split"]` (0–100 left%)
 * - persist plate panel collapsed state at `localStorage["kuro.output.plateCollapsed"]`
 *
 * Self-built splitter (no react-resizable-panels dep) — keeps WSL/Windows Tauri
 * build matrix clean (avoid Linux-format node_modules symlink breakage).
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useShallow } from "zustand/react/shallow";
import { useAppStore } from "@/store/appStore";
import { ResultTable } from "@/components/widgets/ResultTable";
import { PlateMap } from "@/components/widgets/PlateMap";
import { SidebarToggleButton } from "@/components/widgets/SidebarToggleButton";
import { WizardContainer } from "./WizardContainer";
import { StateView } from "@/components/ui/StateView";
import { KURO_STEP_INDEX, TOTAL_KURO_STEPS } from "./constants";
import { Selection3DPanel } from "@/components/panels/Selection3DPanel";


const SPLIT_KEY = "kuro.output.split";
const COLLAPSED_KEY = "kuro.output.plateCollapsed";

const DEFAULT_SPLIT = 50;
const MIN_SPLIT = 20;
const MAX_SPLIT = 80;

function readSplit(): number {
  try {
    const raw = typeof window !== "undefined" ? window.localStorage.getItem(SPLIT_KEY) : null;
    if (!raw) return DEFAULT_SPLIT;
    const n = Number.parseFloat(raw);
    if (!Number.isFinite(n)) return DEFAULT_SPLIT;
    return Math.min(MAX_SPLIT, Math.max(MIN_SPLIT, n));
  } catch {
    return DEFAULT_SPLIT;
  }
}

function readCollapsed(): boolean {
  try {
    const raw = typeof window !== "undefined" ? window.localStorage.getItem(COLLAPSED_KEY) : null;
    return raw === "1" || raw === "true";
  } catch {
    return false;
  }
}



export function OutputStepView() {
  const { t } = useTranslation();
  const goToNextStep = useAppStore((s) => s.goToNextStep);
  const goToPrevStep = useAppStore((s) => s.goToPrevStep);

  const { designResults, plateMappings, failedMutations, rescueStats } = useAppStore(
    useShallow((s) => ({
      designResults: s.designResults,
      plateMappings: s.plateMappings,
      failedMutations: s.failedMutations,
      rescueStats: s.rescueStats,
    })),
  );

  const primerCount = designResults.length;
  const plateCount =
    Math.ceil(plateMappings.filter((m) => m.primer_type === "forward").length / 96) || 0;
  const failedCount = failedMutations.length;
  const rescueCount =
    (rescueStats?.pool_cascade ?? 0) + (rescueStats?.auto_relax ?? 0);

  const hasResults = designResults.length > 0;

  const [splitPct, setSplitPct] = useState<number>(() => readSplit());
  const [plateCollapsed, setPlateCollapsed] = useState<boolean>(() => readCollapsed());

  const containerRef = useRef<HTMLDivElement | null>(null);
  const draggingRef = useRef(false);

  // Persist
  useEffect(() => {
    try {
      window.localStorage.setItem(SPLIT_KEY, String(splitPct));
    } catch {
      // ignore
    }
  }, [splitPct]);

  useEffect(() => {
    try {
      window.localStorage.setItem(COLLAPSED_KEY, plateCollapsed ? "1" : "0");
    } catch {
      // ignore
    }
  }, [plateCollapsed]);


  const handlePointerDown = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    if (plateCollapsed) return;
    draggingRef.current = true;
    e.currentTarget.setPointerCapture(e.pointerId);
  }, [plateCollapsed]);

  const handlePointerMove = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    if (!draggingRef.current) return;
    const el = containerRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    if (rect.width <= 0) return;
    const pct = ((e.clientX - rect.left) / rect.width) * 100;
    const clamped = Math.min(MAX_SPLIT, Math.max(MIN_SPLIT, pct));
    setSplitPct(clamped);
  }, []);

  const handlePointerUp = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    if (!draggingRef.current) return;
    draggingRef.current = false;
    try {
      e.currentTarget.releasePointerCapture(e.pointerId);
    } catch {
      // ignore
    }
  }, []);

  const togglePlate = useCallback(() => {
    setPlateCollapsed((v) => !v);
  }, []);

  const leftStyle = plateCollapsed
    ? { width: "100%" }
    : { width: `${splitPct}%` };
  const rightStyle = plateCollapsed
    ? { width: "0%", display: "none" as const }
    : { width: `${100 - splitPct}%` };

  return (
    <WizardContainer
      stepIndex={KURO_STEP_INDEX["output.summary"]}
      stepTotal={TOTAL_KURO_STEPS}
      titleKey="phaseC.subSteps.output.summary"
      descriptionKey="phaseE.descriptions.output.summary"
      maxWidth="full"
      onPrev={() => goToPrevStep()}
      onNext={() => goToNextStep()}
    >
      {!hasResults ? (
        <div className="flex h-48 items-center justify-center">
          <StateView
            variant="empty"
            title={t("report.noResultsTitle")}
            description={t("report.noResultsDesc")}
          />
        </div>
      ) : (
        <div
          ref={containerRef}
          className="flex h-full min-h-0"
          data-testid="output-split-container"
        >
          {/* 좌: Summary (ResultTable + 텍스트 통계) */}
          <section
            data-testid="output-primer-panel"
            className="flex min-w-0 flex-col gap-3 overflow-y-auto"
            style={leftStyle}
            aria-label={t("phaseC.subSteps.output.summary")}
          >
            {/* 통계 — 4 카드 대신 단순 텍스트 라인 (Phase G #10/#11) */}
            <dl className="flex flex-wrap gap-x-6 gap-y-1 text-sm text-muted-foreground">
              <div className="flex gap-1.5">
                <dt>{t("report.stats.primers")}:</dt>
                <dd className="font-semibold tabular-nums text-success">{primerCount}</dd>
              </div>
              <div className="flex gap-1.5">
                <dt>{t("report.stats.plates")}:</dt>
                <dd className="font-semibold tabular-nums text-info">{plateCount}</dd>
              </div>
              <div className="flex gap-1.5">
                <dt>{t("report.stats.failed")}:</dt>
                <dd
                  className={`font-semibold tabular-nums ${failedCount > 0 ? "text-error" : "text-muted-foreground"}`}
                >
                  {failedCount}
                </dd>
              </div>
              <div className="flex gap-1.5">
                <dt>{t("report.stats.rescued")}:</dt>
                <dd
                  className={`font-semibold tabular-nums ${rescueCount > 0 ? "text-warning" : "text-muted-foreground"}`}
                >
                  {rescueCount}
                </dd>
              </div>
            </dl>

            {/* Result table — bounded viewport; the whole Summary column scrolls
                so the 3D analysis below is reachable without splitting the space. */}
            <div className="h-[55vh] min-h-[320px] shrink-0 overflow-hidden rounded border border-border">
              <ResultTable />
            </div>

            {/* Current-candidate 3D analysis — stacked below the table, open by default. */}
            <div className="shrink-0">
              <Selection3DPanel defaultOpen />
            </div>
          </section>

          {/* drag handle (hidden when collapsed) */}
          {!plateCollapsed && (
            <div
              role="separator"
              aria-orientation="vertical"
              aria-label="Resize primer and plate panels"
              data-testid="output-split-handle"
              onPointerDown={handlePointerDown}
              onPointerMove={handlePointerMove}
              onPointerUp={handlePointerUp}
              onPointerCancel={handlePointerUp}
              className="mx-1 w-1.5 shrink-0 cursor-col-resize rounded bg-border hover:bg-primary/40"
            />
          )}

          {/* 우: PlateMap */}
          <section
            data-testid="output-plate-panel"
            className="flex min-w-0 flex-col"
            style={rightStyle}
            aria-label={t("phaseC.subSteps.plate.layout", "Plate Map")}
            aria-hidden={plateCollapsed}
          >
            <div className="mb-2 flex items-center justify-end">
              <SidebarToggleButton
                collapsed={plateCollapsed}
                onToggle={togglePlate}
                side="right"
                ariaLabel={plateCollapsed ? "Show plate map" : "Hide plate map"}
              />
            </div>
            <div className="flex-1 min-h-0 overflow-auto">
              <PlateMap />
            </div>
          </section>

          {/* When collapsed, render a floating toggle so user can re-open */}
          {plateCollapsed && (
            <div className="absolute right-4 top-4 z-10">
              <SidebarToggleButton
                collapsed={plateCollapsed}
                onToggle={togglePlate}
                side="right"
                ariaLabel="Show plate map"
              />
            </div>
          )}
        </div>
      )}
    </WizardContainer>
  );
}
