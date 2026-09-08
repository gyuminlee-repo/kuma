import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import type { DestCell } from "@/lib/echoJanusAdapter";
import {
  PlateCellPopover,
  PlateColumnHeaderRow,
  PlateRowHeader,
  PlateWellCell,
} from "./PlatePreviewGrid";
import {
  PLATE_FILL_DEST_COMPLETE,
  PLATE_FILL_DEST_PARTIAL,
  PLATE_PREVIEW_FRAME,
  PLATE_PREVIEW_LABEL,
} from "@/lib/platePreviewStyles";

const ROWS = ["A", "B", "C", "D", "E", "F", "G", "H"] as const;
const COLS = Array.from({ length: 12 }, (_, i) => i + 1);

interface Props {
  cells: DestCell[];
  sourceMethod: "echo" | "janus";
  title?: string;
  className?: string;
}

/**
 * Compute well key `${row}${col}` consistent with adapter output:
 * - Echo dest_well from sidecar: "A1".."H12" (no zero padding)
 * - Janus dsp_posi from sidecar: "A1".."H12"
 * Adapter stores well as-is in DestCell.well, so we match the same format.
 */
function wellKey(row: string, col: number): string {
  return `${row}${col}`;
}

/**
 * DestPlateView
 *
 * 96-well destination plate (8 rows A-H × 12 cols 1-12). Each cell represents
 * one mutation. Color encodes F/R completeness:
 *  - emerald: both F and R primers landed
 *  - amber:   only one of F/R landed (partial)
 *  - gray:    empty well
 *
 * sourceMethod determines volume unit (Echo nL vs Janus µL) used in popover.
 */
export function DestPlateView({ cells, sourceMethod, title, className }: Props) {
  const { t } = useTranslation();
  const unit = sourceMethod === "echo" ? "nL" : "µL";
  const byWell = new Map<string, DestCell>();
  for (const c of cells) {
    if (c.well) byWell.set(c.well, c);
  }

  return (
    // container-type stays on this scrolling frame rather than the inner
    // min-w box: see EchoPlateView.tsx for why (contain: layout would turn
    // the inner box's overflow into clipping) and for why the cqw basis is
    // unchanged apart from this frame's 22px of padding and border.
    <div className={cn("plate-preview-grid", PLATE_PREVIEW_FRAME, className)}>
      {/* min-w on the grid box, not on the scroller: WellPlate.tsx:73 shape. */}
      <div className="min-w-[400px]">
      {title ? <div className={PLATE_PREVIEW_LABEL}>{title}</div> : null}
      {/* inline-grid + minmax(min,cap): see EchoPlateView.tsx for why 1fr was
          replaced (was 156px cells at 1900px, 10% text coverage). Cap is
          shared with Echo/Janus. */}
      <div
        role="grid"
        aria-label={t("exportPreview.destGridAriaLabel")}
        className="inline-grid gap-px"
        style={{
          gridTemplateColumns:
            "auto repeat(12, minmax(var(--plate-preview-cell-min), var(--plate-preview-cell-cap)))",
        }}
      >
        <PlateColumnHeaderRow cols={COLS} />
        {ROWS.map((r) => (
          <div key={r} role="row" className="contents">
            <PlateRowHeader row={r} />
            {COLS.map((c) => {
              const well = wellKey(r, c);
              const cell = byWell.get(well);

              if (!cell) {
                return (
                  <PlateWellCell
                    key={well}
                    testId="dest-cell"
                    row={r}
                    well={well}
                    state="empty"
                    title={well}
                    fillClassName="bg-muted/40 dark:bg-muted/20"
                  />
                );
              }

              const complete = cell.hasF && cell.hasR;
              const state = complete ? "complete" : "partial";
              const bg = complete ? PLATE_FILL_DEST_COMPLETE : PLATE_FILL_DEST_PARTIAL;
              const tip = `${cell.mutation} (${well}): F=${cell.hasF ? "✓" : "✗"} R=${cell.hasR ? "✓" : "✗"}`;
              const missing = (
                <span className="text-amber-600 dark:text-amber-400">
                  {t("exportPreview.missing", { defaultValue: "missing" })}
                </span>
              );

              return (
                <PlateWellCell
                  key={well}
                  testId="dest-cell"
                  row={r}
                  well={well}
                  state={state}
                  title={tip}
                  cellClassName="plate-preview-cell"
                  fillClassName={bg}
                  popover={
                    <PlateCellPopover
                      title={cell.mutation}
                      rows={[
                        {
                          label: `${t("exportPreview.destWell", { defaultValue: "Dest well" })}:`,
                          value: <span className="font-mono">{well}</span>,
                        },
                        {
                          label: "F:",
                          value: cell.hasF ? (
                            <span className="font-mono">
                              {cell.fwdSource ?? "?"} · {cell.fwdVol ?? "?"} {unit}
                            </span>
                          ) : (
                            missing
                          ),
                        },
                        {
                          label: "R:",
                          value: cell.hasR ? (
                            <span className="font-mono">
                              {cell.revSource ?? "?"} · {cell.revVol ?? "?"} {unit}
                            </span>
                          ) : (
                            missing
                          ),
                        },
                      ]}
                    />
                  }
                >
                  <span className="font-mono leading-none text-white truncate px-0.5">
                    {cell.mutation}
                  </span>
                </PlateWellCell>
              );
            })}
          </div>
        ))}
      </div>
      </div>
    </div>
  );
}
