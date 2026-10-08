/**
 * Adjacent LOWDEPTH / NO_CALL wells are a cue to review the pipetting history,
 * never proof of a cause. Each native barcode is a separate physical plate:
 * pooling its coordinates with another copy invents neighbours on neither.
 */
import { useId, useState } from "react";
import { AlertTriangle, ChevronDown, ChevronRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import type { WellEntry } from "@/types/mame/models";

const CLUSTER_VERDICTS: ReadonlySet<WellEntry["verdict"]> = new Set(["LOWDEPTH", "NO_CALL"]);
const MIN_CLUSTER_WELLS = 3;

export type ClusterGroup = {
  nativeBarcode: string;
  direction: "row" | "column";
  wells: string[];
};

type WellCoord = { row: number; col: number };

/** Accept only complete 96-well coordinates, with optional zero padding. */
function parseWellCoord(well: string): WellCoord | null {
  const match = /^([A-H])(0?[1-9]|1[0-2])$/.exec(well.trim().toUpperCase());
  return match ? { row: match[1].charCodeAt(0) - 65, col: Number(match[2]) } : null;
}

function wellName({ row, col }: WellCoord): string {
  return `${String.fromCharCode(65 + row)}${String(col).padStart(2, "0")}`;
}

/** Maximal horizontal/vertical runs, grouped by source plate before geometry. */
export function detectFailClusters(wells: WellEntry[]): ClusterGroup[] {
  const byPlate = new Map<string, Map<string, WellCoord>>();
  for (const well of wells) {
    // Legacy/malformed rows without a plate identity cannot establish that
    // they were neighbours. Do not pool them under a synthetic "unknown" plate.
    if (typeof well.native_barcode !== "string" || !well.native_barcode.trim()) continue;
    if (!CLUSTER_VERDICTS.has(well.verdict)) continue;
    const coord = parseWellCoord(well.well);
    if (coord === null) continue;
    const plate = byPlate.get(well.native_barcode) ?? new Map<string, WellCoord>();
    plate.set(wellName(coord), coord);
    byPlate.set(well.native_barcode, plate);
  }

  const clusters: ClusterGroup[] = [];
  for (const [nativeBarcode, plate] of byPlate) {
    for (const direction of ["row", "column"] as const) {
      const lines = new Map<number, number[]>();
      for (const { row, col } of plate.values()) {
        const fixed = direction === "row" ? row : col;
        const moving = direction === "row" ? col : row;
        const values = lines.get(fixed) ?? [];
        values.push(moving);
        lines.set(fixed, values);
      }
      for (const [fixed, values] of [...lines].sort(([a], [b]) => a - b)) {
        const sorted = values.sort((a, b) => a - b);
        let start = 0;
        while (start < sorted.length) {
          let end = start + 1;
          while (end < sorted.length && sorted[end] === sorted[end - 1] + 1) end++;
          if (end - start >= MIN_CLUSTER_WELLS) {
            clusters.push({
              nativeBarcode,
              direction,
              wells: sorted.slice(start, end).map((moving) => wellName(
                direction === "row" ? { row: fixed, col: moving } : { row: moving, col: fixed },
              )),
            });
          }
          start = end;
        }
      }
    }
  }
  return clusters;
}

export function PlateClusterAlert() {
  const { t } = useTranslation();
  const wells = useMameAppStore((s) => s.wells);
  const [open, setOpen] = useState(false);
  const detailsId = useId();
  const clusters = detectFailClusters(wells);
  if (clusters.length === 0) return null;

  return (
    <div
      role="note"
      aria-label={t("mame.qc.plate.clusterAlertAriaLabel")}
      className="rounded border border-warning/40 bg-warning/8 text-xs"
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls={detailsId}
        className="flex w-full items-center gap-2 px-3 py-1.5 text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring"
      >
        <AlertTriangle size={13} className="shrink-0 text-warning" aria-hidden="true" />
        <span className="min-w-0 flex-1 font-semibold text-warning">
          {t("mame.qc.plate.clusterAlertTitle")}
          <span className="ml-1 font-normal text-muted-foreground">({clusters.length})</span>
        </span>
        {open ? (
          <ChevronDown size={13} className="shrink-0 text-muted-foreground" aria-hidden="true" />
        ) : (
          <ChevronRight size={13} className="shrink-0 text-muted-foreground" aria-hidden="true" />
        )}
      </button>
      {open && (
        <div id={detailsId} className="space-y-1 px-3 pb-2 pl-8">
          {clusters.map((group) => (
            <p key={`${group.nativeBarcode}-${group.direction}-${group.wells[0]}`} className="break-words text-muted-foreground">
              {t("mame.qc.plate.clusterAlertDesc", {
                barcode: group.nativeBarcode,
                wells: `${group.wells[0]}-${group.wells[group.wells.length - 1]}`,
              })}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}
