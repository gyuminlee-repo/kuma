/**
 * WtWellEditor — 96-well plate WT well 지정 모달
 *
 * shadcn/ui Dialog 기반. 8×12 격자 표시.
 * 클릭으로 WT well 토글. 저장 시 setPlateMeta + updateRoundField 호출.
 * 384-well 지원은 v0.3 예정 (현재 96-well 고정).
 *
 * Spec: notes/specs/2026-05-04-mame-activity-integration.md §4.4
 */

import { useState } from "react";
import { useStore } from "zustand";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { useActivityStore, type ActivitySlice } from "@/store/mame/activitySlice";
import { useRoundStore } from "@/store/round/roundSlice";
import { cn } from "@/lib/utils";
import type { PlateMeta, PlateConfig } from "@/types/mame/activity";

/** 96-well plate의 row (A–H) × col (01–12) 생성 */
const ROWS = ["A", "B", "C", "D", "E", "F", "G", "H"] as const;
const COLS = Array.from({ length: 12 }, (_, i) => String(i + 1).padStart(2, "0"));

function makeWellId(row: string, col: string): string {
  return `${row}${col}`;
}

/** plate_meta에서 plate_id="P01"의 wt_wells를 Set으로 반환 */
function getWtWells(plateMeta: PlateMeta): Set<string> {
  const plate = plateMeta.plates.find((p) => p.plate_id === "P01");
  return new Set(plate?.wt_wells ?? []);
}

function buildPlateMeta(wtWells: Set<string>, controlWells: string[]): PlateMeta {
  const plate: PlateConfig = {
    plate_id: "P01",
    wt_wells: Array.from(wtWells).sort(),
    control_wells: controlWells,
  };
  return { plates: [plate] };
}

export function WtWellEditor() {
  const [open, setOpen] = useState(false);
  const [localWt, setLocalWt] = useState<Set<string>>(new Set());
  const [isSaving, setIsSaving] = useState(false);

  const activeRoundId = useRoundStore((s) => s.active_round_id);
  const activeRound = useRoundStore((s) =>
    s.rounds.find((r) => r.id === activeRoundId) ?? null
  );
  const updateRoundField = useRoundStore((s) => s.updateRoundField);

  const activityStore = useActivityStore();
  const setPlateMeta = useStore(activityStore, (s: ActivitySlice) => s.setPlateMeta);

  /** 모달 열릴 때 현재 plate_meta에서 WT wells를 로컬 상태로 복사 */
  function handleOpen() {
    const currentMeta = activeRound?.plate_meta ?? { plates: [] };
    setLocalWt(getWtWells(currentMeta));
    setOpen(true);
  }

  function toggleWell(wellId: string) {
    setLocalWt((prev) => {
      const next = new Set(prev);
      if (next.has(wellId)) {
        next.delete(wellId);
      } else {
        next.add(wellId);
      }
      return next;
    });
  }

  async function handleSave() {
    if (!activeRoundId) return;

    const currentMeta = activeRound?.plate_meta ?? { plates: [] };
    const existingPlate = currentMeta.plates.find((p) => p.plate_id === "P01");
    const newMeta = buildPlateMeta(localWt, existingPlate?.control_wells ?? []);

    setIsSaving(true);
    try {
      await setPlateMeta(activeRoundId, newMeta);
      // advisor 지적: setPlateMeta RPC만으로는 round store 상태가 갱신 안 되므로
      // updateRoundField로 직접 동기화
      updateRoundField(activeRoundId, "plate_meta", newMeta);
      setOpen(false);
    } finally {
      setIsSaving(false);
    }
  }

  const disabled = !activeRoundId;

  return (
    <>
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="w-full text-xs"
        onClick={handleOpen}
        disabled={disabled}
        aria-label="Set WT Wells — open plate map editor"
      >
        Set WT Wells
        {activeRound && activeRound.plate_meta.plates[0]?.wt_wells.length > 0 && (
          <span className="ml-1.5 text-muted-foreground">
            ({activeRound.plate_meta.plates[0].wt_wells.length} selected)
          </span>
        )}
      </Button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent
          className="max-w-md"
          aria-describedby={undefined}
        >
          <DialogHeader>
            <DialogTitle>Set WT Wells — Plate P01</DialogTitle>
          </DialogHeader>

          {/* Column headers */}
          <div
            className="overflow-auto"
            aria-label="96-well plate grid. Click to toggle WT designation."
          >
            <div className="grid grid-cols-[1.5rem_repeat(12,1.5rem)] gap-0.5">
              {/* top-left empty cell */}
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
                <>
                  {/* Row label */}
                  <div
                    key={`label-${row}`}
                    className="flex h-6 w-6 items-center justify-center text-caption font-medium text-muted-foreground"
                    aria-hidden="true"
                  >
                    {row}
                  </div>
                  {COLS.map((col) => {
                    const wellId = makeWellId(row, col);
                    const isWt = localWt.has(wellId);
                    return (
                      <button
                        key={wellId}
                        type="button"
                        role="button"
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
                </>
              ))}
            </div>
          </div>

          <p className="text-caption text-muted-foreground">
            {localWt.size} WT {localWt.size === 1 ? "well" : "wells"} selected
          </p>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setOpen(false)}
              className="text-xs"
            >
              Cancel
            </Button>
            <Button
              type="button"
              size="sm"
              onClick={() => void handleSave()}
              disabled={isSaving || !activeRoundId}
              aria-busy={isSaving}
              className="text-xs"
              aria-label="Save WT well selection"
            >
              {isSaving ? "Saving…" : "Save"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
