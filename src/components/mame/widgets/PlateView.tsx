import { useEffect, useState } from "react";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import { VerdictBadge } from "./VerdictBadge";
import { WellPlate } from "./WellPlate";
import type { VerdictClass } from "@/types/mame/models";

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

export function PlateView() {
  const verdicts = useMameAppStore((state) => state.verdicts);
  const wells = useMameAppStore((state) => state.wells);
  const selectedWell = useMameAppStore((state) => state.selectedWell);
  const setSelectedWell = useMameAppStore((state) => state.setSelectedWell);
  const loadPlateData = useMameAppStore((state) => state.loadPlateData);

  const [colorblindMode, setColorblindMode] = useState(false);
  const selectedCount = wells.filter((well) => well.selected).length;
  const filledCount = wells.length;

  useEffect(() => {
    if (verdicts.length > 0 && wells.length === 0) {
      void loadPlateData();
    }
  }, [loadPlateData, verdicts.length, wells.length]);

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <div className="flex items-center justify-between border-b border-border px-3 py-1.5">
        <div className="flex items-center gap-2 text-caption text-muted-foreground">
          <span>
            Plate:{" "}
            <span className="font-medium text-foreground">
              {getSelectedPlateLabel(selectedWell?.barcode ?? null)}
            </span>
          </span>
          <span className="rounded-full border border-border/70 bg-muted px-2 py-0.5 text-caption font-medium text-muted-foreground">
            {filledCount} wells
          </span>
          <span className="rounded-full border border-primary/15 bg-primary/10 px-2 py-0.5 text-caption font-medium text-primary">
            {selectedCount} picked
          </span>
        </div>
        <label className="flex items-center gap-1 text-caption text-muted-foreground">
          <input
            type="checkbox"
            checked={colorblindMode}
            onChange={(e) => setColorblindMode(e.target.checked)}
            className="h-3 w-3 rounded accent-primary"
            aria-label="Enable colorblind support pattern"
          />
          Color assist
        </label>
      </div>

      <div className="grid flex-1 min-h-0 grid-cols-[1fr_164px] gap-2 overflow-hidden p-2">
        <div className="min-h-0 overflow-auto">
          <WellPlate
            wells={wells}
            selectedWellId={selectedWell?.well}
            onWellClick={(well) => setSelectedWell(well)}
            colorblindMode={colorblindMode}
          />
          <div className="mt-2 flex flex-wrap gap-1" aria-label="Verdict color legend">
            {(
              [
                "PASS",
                "AMBIGUOUS",
                "WRONG_AA",
                "FRAMESHIFT",
                "MANY",
                "LOWDEPTH",
              ] as VerdictClass[]
            ).map((verdict) => (
              <VerdictBadge key={verdict} verdict={verdict} className="text-caption" />
            ))}
          </div>
        </div>

        <aside
          className="flex min-h-0 flex-col overflow-auto rounded-control border border-border bg-background p-2"
          aria-live="polite"
          aria-label="Selected well details"
        >
          {selectedWell ? (
            <div className="space-y-2">
              <div className="rounded-control border border-border bg-muted/20 px-2.5 py-2">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className="text-caption font-medium uppercase tracking-wide text-muted-foreground">
                      Selected Well
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
                      Selected replicate
                    </span>
                  )}
                </div>
              </div>

              <div className="space-y-0">
              <DetailRow label="Well" value={selectedWell.well} />
              <DetailRow label="Barcode" value={selectedWell.barcode} />
              <DetailRow label="Native BC" value={selectedWell.native_barcode} />
              <DetailRow label="Mutant" value={selectedWell.mutant_id || "—"} />
              <DetailRow label="Notes" value={selectedWell.notes || "—"} />
              </div>
            </div>
          ) : (
            <div className="flex flex-1 flex-col items-center justify-center text-center">
              <span className="mb-1 text-base text-muted-foreground" aria-hidden="true">◎</span>
              <p className="text-caption text-muted-foreground">
                Click a well to inspect.
              </p>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
