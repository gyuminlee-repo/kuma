import { useEffect, useState } from "react";
import { AlertTriangle } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import { VerdictBadge } from "./VerdictBadge";
import { WellPlate } from "./WellPlate";
import type { WellColorOverride } from "./WellPlate";
import { cn } from "@/lib/utils";
import type { VerdictClass, WellEntry } from "@/types/mame/models";

function getSelectedPlateLabel(barcode: string | null): string {
  if (!barcode) return "None";
  const match = barcode.match(/^([1-3])_/);
  return match ? `NB0${match[1]}` : "Unknown";
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-3 border-b border-border/50 py-1 last:border-0">
      <span className="flex-shrink-0 text-caption text-muted-foreground">{label}</span>
      <span className="break-all text-right text-caption font-medium text-foreground">{value}</span>
    </div>
  );
}

interface PlateViewProps {
  /** Optional callback to override per-well fill colors. Default = verdict-mode (mame). */
  wellColorOf?: (well: WellEntry) => WellColorOverride | null;
  /**
   * Optional external wells array. When provided, mameAppStore wells are NOT used
   * and loadPlateData is NOT triggered. mame callers omit this prop — default store behavior preserved.
   */
  wells?: WellEntry[];
}

export function PlateView({ wellColorOf, wells: externalWells }: PlateViewProps = {}) {
  const { t } = useTranslation();
  const verdicts = useMameAppStore((state) => state.verdicts);
  const storeWells = useMameAppStore((state) => state.wells);
  const selectedWell = useMameAppStore((state) => state.selectedWell);
  const setSelectedWell = useMameAppStore((state) => state.setSelectedWell);
  const loadPlateData = useMameAppStore((state) => state.loadPlateData);

  // Use external wells if provided (kuro mode), otherwise fall back to mame store wells
  const wells = externalWells ?? storeWells;

  const [colorblindMode, setColorblindMode] = useState(false);
  // Legend-class filter: clicking a verdict class dims non-matching wells.
  // Single-select toggle; resets when the underlying wells change.
  const [activeClass, setActiveClass] = useState<VerdictClass | null>(null);
  useEffect(() => {
    setActiveClass(null);
  }, [wells]);
  const selectedCount = wells.filter((well) => well.selected).length;
  const filledCount = wells.length;

  useEffect(() => {
    // Only trigger mame store load when external wells are NOT provided
    if (externalWells !== undefined) return;
    if (verdicts.length > 0 && storeWells.length === 0) {
      void loadPlateData();
    }
  }, [externalWells, loadPlateData, verdicts.length, storeWells.length]);

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <div className="flex items-center justify-between border-b border-border px-3 py-1.5">
        <div className="flex items-center gap-2 text-caption text-muted-foreground">
          <span>
            {t("mame.plateView.plate")}:{" "}
            <span className="font-medium text-foreground">
              {getSelectedPlateLabel(selectedWell?.barcode ?? null)}
            </span>
          </span>
          <span className="rounded-full border border-border/70 bg-muted px-2 py-0.5 text-caption font-medium text-muted-foreground">
            {t("mame.plateView.wells", { count: filledCount })}
          </span>
          <span className="rounded-full border border-primary/15 bg-primary/10 px-2 py-0.5 text-caption font-medium text-primary">
            {t("mame.plateView.picked", { count: selectedCount })}
          </span>
        </div>
        <label className="flex items-center gap-1 text-caption text-muted-foreground">
          <input
            type="checkbox"
            checked={colorblindMode}
            onChange={(e) => setColorblindMode(e.target.checked)}
            className="h-3 w-3 rounded accent-primary"
            aria-label={t("mame.plateView.colorAssistAriaLabel")}
          />
          {t("mame.plateView.colorAssist")}
        </label>
      </div>

      <div className="grid flex-1 min-h-0 grid-cols-[1fr_164px] gap-2 overflow-hidden p-2">
        <div className="min-h-0 overflow-auto">
          <WellPlate
            wells={wells}
            selectedWellId={selectedWell?.well}
            onWellClick={(well) => setSelectedWell(well)}
            colorblindMode={colorblindMode}
            wellColorOf={wellColorOf}
            dimmedOf={(w) => activeClass !== null && w.verdict !== activeClass}
          />
          <div
            className="mt-2 flex flex-wrap gap-1"
            role="group"
            aria-label={t("mame.plateView.verdictLegendAriaLabel")}
          >
            {(
              [
                "PASS",
                "AMBIGUOUS",
                "MIXED",
                "WRONG_AA",
                "FRAMESHIFT",
                "MANY",
                "LOWDEPTH",
              ] as VerdictClass[]
            ).map((verdict) => {
              const active = activeClass === verdict;
              const hasData = wells.some((w) => w.verdict === verdict);
              return (
                <button
                  key={verdict}
                  type="button"
                  disabled={!hasData}
                  onClick={() =>
                    setActiveClass((prev) => (prev === verdict ? null : verdict))
                  }
                  aria-pressed={active}
                  aria-label={t("mame.plateView.verdictFilterAriaLabel", { verdict })}
                  className={cn(
                    "rounded-control border px-0.5 transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-ring",
                    active
                      ? "border-primary bg-primary/10"
                      : "border-transparent",
                    hasData ? "hover:bg-muted/60" : "cursor-not-allowed opacity-40",
                  )}
                >
                  <VerdictBadge verdict={verdict} className="text-caption" />
                </button>
              );
            })}
          </div>
        </div>

        <aside
          className="flex min-h-0 flex-col overflow-auto rounded-control border border-border bg-background p-2"
          aria-live="polite"
          aria-label={t("mame.plateView.selectedWellAriaLabel")}
        >
          {selectedWell ? (
            <div className="space-y-2">
              <div className="rounded-control border border-border bg-muted/20 px-2.5 py-2">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className="text-caption font-medium uppercase tracking-wide text-muted-foreground">
                      {t("mame.plateView.selectedWellLabel")}
                    </p>
                    <p className="font-display text-lg font-semibold leading-none text-foreground">
                      {selectedWell.well}
                    </p>
                  </div>
                  <VerdictBadge verdict={selectedWell.verdict} />
                </div>
                <div className="mt-2 flex flex-wrap gap-1">
                  <span className="rounded-full border border-border/70 bg-muted px-2 py-0.5 text-caption font-medium text-muted-foreground">
                    {getSelectedPlateLabel(selectedWell.barcode)}
                  </span>
                  {selectedWell.selected && (
                    <span className="rounded-full border border-primary/15 bg-primary/10 px-2 py-0.5 text-caption font-medium text-primary">
                      {t("mame.plateView.selectedReplicate")}
                    </span>
                  )}
                </div>
              </div>

              <div className="space-y-0">
              <DetailRow label={t("mame.plateView.detailWell")} value={selectedWell.well} />
              <DetailRow label={t("mame.plateView.detailBarcode")} value={selectedWell.barcode} />
              <DetailRow label={t("mame.plateView.detailNativeBc")} value={selectedWell.native_barcode} />
              <DetailRow label={t("mame.plateView.detailMutant")} value={selectedWell.mutant_id || "—"} />
              <DetailRow label={t("mame.plateView.detailNotes")} value={selectedWell.notes || "—"} />
              </div>
              {selectedWell.is_fallback && (
                <div
                  className="mt-2 flex items-start gap-1.5 rounded-control border border-warning/40 bg-warning/10 px-2.5 py-2"
                  role="note"
                  aria-label={t("mame.plateView.fallbackNoticeAriaLabel")}
                >
                  <AlertTriangle
                    size={12}
                    className="mt-0.5 shrink-0 text-warning"
                    aria-hidden="true"
                  />
                  <div className="space-y-0.5">
                    <p className="text-caption font-semibold text-warning">
                      {t("mame.plateView.fallbackTitle")}
                    </p>
                    <p className="text-caption text-muted-foreground">
                      {t("mame.plateView.fallbackDesc")}
                    </p>
                    {selectedWell.fallback_reason && (
                      <p className="text-caption text-muted-foreground">
                        {selectedWell.fallback_reason}
                      </p>
                    )}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="flex flex-1 flex-col items-center justify-center text-center">
              <span className="mb-1 text-base text-muted-foreground" aria-hidden="true">◎</span>
              <p className="text-caption text-muted-foreground">
                {t("mame.plateView.clickWellHint")}
              </p>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
