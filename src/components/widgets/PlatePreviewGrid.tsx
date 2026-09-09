import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import { Popover, PopoverTrigger, PopoverContent } from "@/components/ui/popover";

/**
 * Markup shared by the three Kuro step-6 plate previews (EchoPlateView,
 * JanusPlateView, DestPlateView).
 *
 * Why this module exists: the header row, the empty cell, the Popover-wrapped
 * filled cell and the popover body were copied into all three views, and the
 * copies drifted. The three views answered the same question three ways
 * (gridcell role on the button in JANUS only, `aria-label` on the row header
 * everywhere except Echo, three different popover layouts). One definition
 * here means one answer.
 *
 * What is deliberately *not* shared: the per-view cell size class
 * (`plate-preview-cell-tiny` / `-narrow` / plain), which is a prop, and the
 * `plate-preview-grid` container-query element, which stays in each view
 * because the element that carries it differs (frame for Echo/Dest, one rack
 * for JANUS) and index.css:188-238 measured its clamps against those exact
 * elements.
 */

/**
 * gridcell decision (unifying the three views on one shape).
 *
 * A cell is a `<div role="gridcell">` wrapper holding the interactive element,
 * which is WellPlate.tsx:127-134's shape and the WAI-ARIA grid pattern (a
 * gridcell containing one focusable widget). The alternative JANUS used,
 * `role="gridcell"` directly on the `<button>`, overrides the button's native
 * role so assistive tech no longer announces it as a button. Empty cells use
 * the same wrapper so `role="row"`'s direct children are gridcells in both
 * states and one component renders both.
 *
 * Data attributes and `title` stay on the inner element, never on the wrapper:
 * the view tests count cells through `[data-testid='<view>-cell']` and read the
 * fill class off the first match, so duplicating them onto the wrapper would
 * double the counts and point the class assertions at an unstyled box.
 */

const CELL_BASE = "aspect-square rounded-[2px] border border-border/50";
const CELL_INTERACTIVE =
  "flex justify-center overflow-hidden p-0 cursor-pointer focus:outline-none focus:ring-1 focus:ring-ring";

const HEADER_CLASS = "text-caption text-muted-foreground";

/** Header row: empty corner cell followed by one `columnheader` per column. */
export function PlateColumnHeaderRow({ cols }: { cols: readonly number[] }) {
  return (
    <div role="row" className="contents">
      <div />
      {cols.map((c) => (
        <div key={c} role="columnheader" className={cn(HEADER_CLASS, "text-center")}>
          {c}
        </div>
      ))}
    </div>
  );
}

/** Row label cell. Carries the localized `aria-label` all three views now share. */
export function PlateRowHeader({ row }: { row: string }) {
  const { t } = useTranslation();
  return (
    <div
      role="rowheader"
      data-row-label={row}
      aria-label={t("exportPreview.rowAriaLabel", { row })}
      className={cn(HEADER_CLASS, "text-right pr-1")}
    >
      {row}
    </div>
  );
}

interface PlateWellCellProps {
  /** `data-testid` on the inner element; the view's existing cell test id. */
  testId: string;
  /** `data-row`; row letter. */
  row: string;
  /** `data-well`, when the view addresses cells by well (JANUS, Dest). */
  well?: string;
  /** `data-rack`, JANUS only. */
  rack?: 1 | 2;
  /**
   * `data-state`: what the view says this well is. Dest uses
   * "empty" | "partial" | "complete"; Echo marks an empty well "free" (this
   * run's quadrant pair leaves it empty) or "reserved" (the other pair owns
   * it). Views that make no such statement leave it off.
   */
  state?: string;
  /** Native tooltip text. */
  title: string;
  /** Background fill, from platePreviewStyles. */
  fillClassName: string;
  /**
   * Per-view cell size class (`plate-preview-cell-tiny` / `-narrow` /
   * `plate-preview-cell`). Filled cells only; index.css clamps font size
   * through it and the three grids need three different clamps.
   */
  cellClassName?: string;
  /** Extra layout classes on the filled cell (JANUS stacks two lines). */
  contentClassName?: string;
  /** Popover content; absent means an empty well (no interaction). */
  popover?: ReactNode;
  children?: ReactNode;
}

/** One well: `<div role="gridcell">` wrapping either a static box or a button. */
export function PlateWellCell({
  testId,
  row,
  well,
  rack,
  state,
  title,
  fillClassName,
  cellClassName,
  contentClassName,
  popover,
  children,
}: PlateWellCellProps) {
  const dataAttrs = {
    "data-testid": testId,
    "data-row": row,
    ...(well !== undefined ? { "data-well": well } : {}),
    ...(rack !== undefined ? { "data-rack": rack } : {}),
    ...(state !== undefined ? { "data-state": state } : {}),
  };

  if (!popover) {
    return (
      <div role="gridcell">
        <div {...dataAttrs} title={title} className={cn(CELL_BASE, "w-full", fillClassName)} />
      </div>
    );
  }

  return (
    <div role="gridcell">
      <Popover>
        <PopoverTrigger asChild>
          <button
            type="button"
            {...dataAttrs}
            title={title}
            className={cn(
              CELL_BASE,
              CELL_INTERACTIVE,
              // w-full: the wrapper is the grid item now, and a bare button
              // would shrink-to-fit inside it (WellPlate.tsx does the same).
              "w-full",
              contentClassName ?? "items-center",
              cellClassName,
              fillClassName,
            )}
          >
            {children}
          </button>
        </PopoverTrigger>
        {popover}
      </Popover>
    </div>
  );
}

/** One `label: value` line of a cell popover. */
export interface PlatePopoverRow {
  /** Localized label, colon included. */
  label: ReactNode;
  /** Value node. Keep a value in a single node: the view tests match on the
   *  whole value string (e.g. "Destination [1] A1"). */
  value: ReactNode;
}

/**
 * Cell popover body. Optional monospace title line, then label/value rows.
 *
 * The rows differ per view because the views hold different information; the
 * shape does not. `data-testid` lets the tests assert all three go through
 * this component.
 */
export function PlateCellPopover({
  title,
  rows,
}: {
  title?: ReactNode;
  rows: PlatePopoverRow[];
}) {
  return (
    <PopoverContent className="w-auto text-xs space-y-1" data-testid="plate-popover-body">
      {title !== undefined ? <div className="font-mono font-medium">{title}</div> : null}
      {rows.map((r, i) => (
        <div key={i}>
          <span className="text-muted-foreground">{r.label} </span>
          {r.value}
        </div>
      ))}
    </PopoverContent>
  );
}
