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

import { Fragment, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useStore } from "zustand";
import { toast } from "sonner";
import { useActivityStore, type ActivitySlice } from "@/store/mame/activitySlice";
import { useRoundStore } from "@/store/round/roundSlice";
import { cn } from "@/lib/utils";
import type { PlateMeta, PlateConfig } from "@/types/mame/activity";

const ROWS = ["A", "B", "C", "D", "E", "F", "G", "H"] as const;
const COLS = Array.from({ length: 12 }, (_, i) => String(i + 1).padStart(2, "0"));
const DEBOUNCE_MS = 400;

// Single-select: reduce backend wt_wells[] to one selection.
// Legacy multi-selection data picks first sorted to surface divergence
// rather than silently dropping data.
function getWtWell(plateMeta: PlateMeta): string | null {
  const plate = plateMeta.plates.find((p) => p.plate_id === "P01");
  const wells = plate?.wt_wells ?? [];
  if (wells.length === 0) return null;
  return [...wells].sort()[0];
}

function buildPlateMeta(wt: string | null, controlWells: string[]): PlateMeta {
  const plate: PlateConfig = {
    plate_id: "P01",
    wt_wells: wt ? [wt] : [],
    control_wells: controlWells,
  };
  return { plates: [plate] };
}

type SaveStatus = "idle" | "saving" | "saved" | "error";

export function WtWellGrid() {
  const { t } = useTranslation();
  const activeRoundId = useRoundStore((s) => s.active_round_id);
  const activeRound = useRoundStore((s) =>
    s.rounds.find((r) => r.id === s.active_round_id) ?? null,
  );
  const updateRoundField = useRoundStore((s) => s.updateRoundField);
  const activityStore = useActivityStore();
  const setPlateMeta = useStore(activityStore, (s: ActivitySlice) => s.setPlateMeta);

  const disabled = activeRoundId === null;

  const [localWt, setLocalWt] = useState<string | null>(() =>
    activeRound ? getWtWell(activeRound.plate_meta) : null,
  );
  const [status, setStatus] = useState<SaveStatus>("idle");
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const localWtRef = useRef<string | null>(localWt);
  const activeRoundRef = useRef(activeRound);
  const lastCommittedMetaRef = useRef<PlateMeta | null>(null);

  useEffect(() => {
    localWtRef.current = localWt;
  }, [localWt]);

  useEffect(() => {
    activeRoundRef.current = activeRound;
  }, [activeRound]);

  useEffect(() => {
    if (!activeRound) {
      setLocalWt(null);
      return;
    }
    // Self-echo skip: server snapshot equals what we just committed.
    if (
      lastCommittedMetaRef.current &&
      JSON.stringify(lastCommittedMetaRef.current) ===
        JSON.stringify(activeRound.plate_meta)
    ) {
      return;
    }
    setLocalWt(getWtWell(activeRound.plate_meta));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeRound?.id, activeRound?.plate_meta]);

  async function commit(
    wt: string | null,
    roundId: string | null,
    controlWells: string[],
  ) {
    if (!roundId) return;
    if (roundId !== useRoundStore.getState().active_round_id) return;
    const meta = buildPlateMeta(wt, controlWells);
    setStatus("saving");
    try {
      await setPlateMeta(roundId, meta);
      lastCommittedMetaRef.current = meta;
      updateRoundField(roundId, "plate_meta", meta);
      setStatus("saved");
      setTimeout(() => {
        setStatus((s) => (s === "saved" ? "idle" : s));
      }, 2000);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      toast.error(t("wtWellGrid.errorStatus", { reason: msg }));
      // Rollback localWt to the last known server snapshot.
      const r = useRoundStore.getState().rounds.find((x) => x.id === roundId);
      setLocalWt(r ? getWtWell(r.plate_meta) : null);
      setStatus("error");
      setTimeout(() => {
        setStatus((s) => (s === "error" ? "idle" : s));
      }, 3000);
    }
  }

  function scheduleSave(nextWt: string | null) {
    if (timerRef.current) clearTimeout(timerRef.current);
    const capturedRoundId = activeRound?.id ?? null;
    const capturedControl =
      activeRound?.plate_meta.plates.find((p) => p.plate_id === "P01")
        ?.control_wells ?? [];
    timerRef.current = setTimeout(() => {
      void commit(nextWt, capturedRoundId, capturedControl);
    }, DEBOUNCE_MS);
  }

  // Unmount flush: pending timer fires immediately with latest snapshot.
  // Empty deps + refs to capture latest state without re-binding cleanup.
  useEffect(() => {
    return () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
        const round = activeRoundRef.current;
        if (round) {
          const control =
            round.plate_meta.plates.find((p) => p.plate_id === "P01")
              ?.control_wells ?? [];
          void commit(localWtRef.current, round.id, control);
        }
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function selectWell(wellId: string) {
    setLocalWt((prev) => {
      // Click same well = deselect; click different = replace.
      const next = prev === wellId ? null : wellId;
      scheduleSave(next);
      return next;
    });
  }

  const statusText =
    status === "saving"
      ? t("wtWellGrid.savingStatus")
      : status === "saved"
        ? t("wtWellGrid.savedStatus")
        : "";

  return (
    <div className="space-y-2">
      <div
        aria-label={t("wtWellGrid.gridAriaLabel")}
        role="radiogroup"
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
                const isWt = localWt === wellId;
                return (
                  <button
                    key={wellId}
                    type="button"
                    role="radio"
                    aria-checked={isWt}
                    aria-label={wellId}
                    onClick={() => selectWell(wellId)}
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
          {statusText ? <span>{statusText} </span> : null}
          {localWt
            ? t("wtWellGrid.selectedSingle", { count: 1 })
            : t("wtWellGrid.selectedPlural", { count: 0 })}
        </p>
      )}
    </div>
  );
}
