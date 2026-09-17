import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import type { EchoCell } from "@/lib/echoJanusAdapter";
import { PlatePreviewSelector, usePreviewPlate } from "./PlatePreviewSelector";
import {
  PlateCellPopover,
  PlateColumnHeaderRow,
  PlateRowHeader,
  PlateWellCell,
} from "./PlatePreviewGrid";
import {
  PLATE_FILL_FORWARD,
  PLATE_FILL_RESERVED,
  PLATE_FILL_REVERSE,
  PLATE_PREVIEW_FRAME,
} from "@/lib/platePreviewStyles";
import { isColumnInHalf, isForwardRow, otherHalves } from "@/lib/echoQuadrant";
import type { EchoQuadrant } from "@/types/models";

const ROWS = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N", "O", "P"] as const;
const COLS = Array.from({ length: 24 }, (_, i) => i + 1);

interface Props {
  cells: EchoCell[];
  /** Caption drawn above the grid, at the same level as JANUS rack labels. */
  title?: string;
  /**
   * Half of the plate this run fills, or null for the no-half layout the
   * mapper falls back to when nothing is selected (plate_mapper.py). Only a
   * selected half splits the empty wells into "this run leaves it empty" and
   * "the other round owns it"; with no half that is not a fact about the
   * plate, so nothing is marked.
   */
  quadrant?: EchoQuadrant | null;
  className?: string;
}

export function EchoPlateView({ cells, title, quadrant = null, className }: Props) {
  const { t } = useTranslation();
  const { plates, selected, setSelection } = usePreviewPlate(cells.map((c) => c.sourcePlate ?? ""));
  const byWell = new Map(cells.filter((c) => (c.sourcePlate ?? "") === selected).map((c) => [c.well, c]));
  // Name of the half a run on `quadrant` does not touch, for the reserved
  // wells' native tooltip (the only text an empty well carries).
  const otherPair = quadrant === null ? "" : otherHalves(quadrant).join(", ");
  return (
    // `plate-preview-grid` (container-type: inline-size) stays on the
    // scrolling frame, not on the inner min-w box: container-type implies
    // `contain: layout`, under which overflow of a `visible` box is ink
    // overflow, so a container on the inner box would clip a too-wide grid
    // instead of handing the overflow to this scroller. Keeping it here also
    // keeps the cqw basis this element's content width, which is what the
    // font clamps in index.css:188-238 were measured against (now narrower
    // by the 22px this frame's padding and border add, always in the
    // shrinking direction, so the 0%-truncation target still holds).
    <div className={cn("plate-preview-grid", PLATE_PREVIEW_FRAME, className)}>
      <PlatePreviewSelector title={title ?? t("exportPreview.echoSourcePlateLabel")} plates={plates} selected={selected} onChange={setSelection} />
      {/* min-w sits on the grid box, not on the scroller above it, so a
          viewport narrower than the plate scrolls this frame instead of the
          page (same shape as WellPlate.tsx:73). */}
      <div className="min-w-[700px]">
        {/* inline-grid + minmax(min,cap) instead of repeat(24,1fr): 1fr let a
          wide container stretch cells past what the 15px font ceiling could
          fill (77px cells at 1900px, 11% text coverage). minmax caps track
          width at --plate-preview-cell-cap (shared with Janus/Dest so a wide
          screen shows the same well size across all three), and inline-grid
          keeps the grid from being stretched to the wrapper's full width once
          the tracks stop growing (WellSelectionPanel.tsx:459 precedent). */}
      <div
        key={selected}
        role="grid"
        aria-label={t("exportPreview.echoGridAriaLabel")}
        className="inline-grid gap-px"
        style={{
          gridTemplateColumns:
            "auto repeat(24, minmax(var(--plate-preview-cell-min-tiny), var(--plate-preview-cell-cap)))",
        }}
      >
        <PlateColumnHeaderRow cols={COLS} />
        {ROWS.map((r, idx) => {
          // Row parity is direction under the half layout: a forward primer
          // sits at 2r and its reverse at 2r+1 in either half, so the half
          // shifts columns only. Only the empty stripe reads this: a filled
          // well takes its colour from `cell.isFwd`, the same field the
          // popover prints, so the two cannot disagree.
          const isFwdRow = isForwardRow(idx);
          return (
            <div key={r} role="row" className="contents">
              <PlateRowHeader row={r} />
              {COLS.map((c) => {
                const well = `${r}${String(c).padStart(2, "0")}`;
                const cell = byWell.get(well);
                if (!cell) {
                  // A half is a contiguous block of columns holding both the
                  // forward wells and their reverses, so the column range
                  // alone decides whether this well is one this run can reach.
                  // Testing the row as well would mark every reverse-primer
                  // well as belonging to the other round.
                  const reserved = quadrant !== null && !isColumnInHalf(c, quadrant);
                  return (
                    <PlateWellCell
                      key={well}
                      testId="echo-cell"
                      row={r}
                      // No half means the fallback layout, where "reserved"
                      // would be a claim about a plate the export does not
                      // divide; the attribute stays off entirely.
                      state={
                        quadrant === null ? undefined : reserved ? "reserved" : "free"
                      }
                      title={
                        reserved
                          ? t("exportPreview.echoReservedWellTitle", {
                              well,
                              quadrants: otherPair,
                            })
                          : well
                      }
                      fillClassName={
                        reserved
                          ? PLATE_FILL_RESERVED
                          : isFwdRow
                            ? "bg-blue-50 dark:bg-blue-950/30"
                            : "bg-orange-50 dark:bg-orange-950/30"
                      }
                    />
                  );
                }
                const fill = cell.isFwd ? PLATE_FILL_FORWARD : PLATE_FILL_REVERSE;
                const mutation = cell.mutation || cell.sourceWellName;
                const tip = `${cell.sourceWellName} → ${cell.destPlate} ${cell.destWell} (${cell.transferVolNl} nL)`;
                return (
                  <PlateWellCell
                    key={well}
                    testId="echo-cell"
                    row={r}
                    title={tip}
                    cellClassName="plate-preview-cell-tiny"
                    fillClassName={fill}
                    popover={
                      <PlateCellPopover
                        rows={[
                          {
                            label: t("exportPreview.echoPopoverPrimerLabel"),
                            value: <span className="font-mono">{cell.sourceWellName}</span>,
                          },
                          {
                            label: t("exportPreview.echoPopoverDirectionLabel"),
                            value: (
                              <span>
                                {cell.isFwd
                                  ? t("exportPreview.echoPopoverForward")
                                  : t("exportPreview.echoPopoverReverse")}
                              </span>
                            ),
                          },
                          {
                            label: t("exportPreview.echoPopoverSourceWellLabel"),
                            value: <span className="font-mono">{[cell.sourcePlate, cell.well].filter(Boolean).join(" ")}</span>,
                          },
                          {
                            label: t("exportPreview.echoPopoverDestinationLabel"),
                            value: (
                              <span className="font-mono">
                                {cell.destPlate} {cell.destWell}
                              </span>
                            ),
                          },
                          {
                            label: t("exportPreview.echoPopoverTransferLabel"),
                            value: <span>{cell.transferVolNl} nL</span>,
                          },
                        ]}
                      />
                    }
                  >
                    <span className="font-mono leading-none text-white truncate">{mutation}</span>
                  </PlateWellCell>
                );
              })}
            </div>
          );
        })}
        </div>
      </div>
    </div>
  );
}
