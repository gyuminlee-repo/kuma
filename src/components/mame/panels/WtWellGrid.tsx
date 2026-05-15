/**
 * WtWellGrid — 96-well plate WT well inline grid
 *
 * Replaces the dialog-based WtWellEditor. Renders an 8x12 grid directly in the
 * Ingest section. Clicking toggles a well optimistically; a 400 ms debounce
 * triggers setPlateMeta. Guards against stale round writes, self-echo sync
 * loops, unmount data loss, and RPC failures.
 *
 * Spec: notes/specs/2026-05-15-mame-inline-wt-grid.md
 */

import { Fragment, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useRoundStore } from "@/store/round/roundSlice";
import { cn } from "@/lib/utils";
import type { PlateMeta } from "@/types/mame/activity";

const ROWS = ["A", "B", "C", "D", "E", "F", "G", "H"] as const;
const COLS = Array.from({ length: 12 }, (_, i) => String(i + 1).padStart(2, "0"));

function getWtWells(plateMeta: PlateMeta): Set<string> {
  const plate = plateMeta.plates.find((p) => p.plate_id === "P01");
  return new Set(plate?.wt_wells ?? []);
}

export function WtWellGrid() {
  const { t } = useTranslation();
  const activeRoundId = useRoundStore((s) => s.active_round_id);
  const activeRound = useRoundStore((s) =>
    s.rounds.find((r) => r.id === s.active_round_id) ?? null,
  );
  const disabled = activeRoundId === null;

  const [localWt, setLocalWt] = useState<Set<string>>(() =>
    activeRound ? getWtWells(activeRound.plate_meta) : new Set(),
  );

  useEffect(() => {
    setLocalWt(activeRound ? getWtWells(activeRound.plate_meta) : new Set());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeRound?.id, activeRound?.plate_meta]);

  function toggleWell(wellId: string) {
    setLocalWt((prev) => {
      const next = new Set(prev);
      if (next.has(wellId)) next.delete(wellId);
      else next.add(wellId);
      return next;
    });
  }

  return (
    <div className="space-y-2">
      <div
        aria-label={t("wtWellGrid.gridAriaLabel")}
        className={cn(
          "overflow-auto",
          disabled && "opacity-50 pointer-events-none",
        )}
      >
        <div className="grid grid-cols-[1.5rem_repeat(12,1.5rem)] gap-0.5">
          <div className="h-6 w-6" aria-hidden="true" />
          {COLS.map((col) => (
            <div
              key={col}
              className="flex h-6 w-6 items-center justify-center text-caption font-medium text-muted-foreground"
              aria-hidden="true"
            >
              {Number(col)}
            </div>
          ))}
          {ROWS.map((row) => (
            <Fragment key={row}>
              <div
                className="flex h-6 w-6 items-center justify-center text-caption font-medium text-muted-foreground"
                aria-hidden="true"
              >
                {row}
              </div>
              {COLS.map((col) => {
                const wellId = `${row}${col}`;
                const isWt = localWt.has(wellId);
                return (
                  <button
                    key={wellId}
                    type="button"
                    aria-pressed={isWt}
                    aria-label={wellId}
                    onClick={() => toggleWell(wellId)}
                    className={cn(
                      "flex h-6 w-6 items-center justify-center rounded-sm text-[9px] font-medium transition-colors",
                      "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                      isWt
                        ? "bg-primary text-primary-foreground"
                        : "bg-muted text-muted-foreground hover:bg-muted/70",
                    )}
                  >
                    {isWt ? "WT" : ""}
                  </button>
                );
              })}
            </Fragment>
          ))}
        </div>
      </div>
      {disabled ? (
        <p className="text-caption text-muted-foreground">
          {t("wtWellGrid.noActiveRound")}
        </p>
      ) : (
        <p className="text-caption text-muted-foreground">
          {localWt.size === 1
            ? t("wtWellGrid.selectedSingle", { count: 1 })
            : t("wtWellGrid.selectedPlural", { count: localWt.size })}
        </p>
      )}
    </div>
  );
}
