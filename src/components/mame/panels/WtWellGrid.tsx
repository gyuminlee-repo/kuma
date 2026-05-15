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

import { Fragment } from "react";
import { useTranslation } from "react-i18next";
import { useRoundStore } from "@/store/round/roundSlice";
import { cn } from "@/lib/utils";

const ROWS = ["A", "B", "C", "D", "E", "F", "G", "H"] as const;
const COLS = Array.from({ length: 12 }, (_, i) => String(i + 1).padStart(2, "0"));

export function WtWellGrid() {
  const { t } = useTranslation();
  const activeRoundId = useRoundStore((s) => s.active_round_id);
  const disabled = activeRoundId === null;

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
              {COLS.map((col) => (
                <button
                  key={`${row}${col}`}
                  type="button"
                  aria-label={`${row}${col}`}
                  className="flex h-6 w-6 items-center justify-center rounded-sm bg-muted text-muted-foreground text-[9px] font-medium"
                />
              ))}
            </Fragment>
          ))}
        </div>
      </div>
      {disabled && (
        <p className="text-caption text-muted-foreground">
          {t("wtWellGrid.noActiveRound")}
        </p>
      )}
    </div>
  );
}
