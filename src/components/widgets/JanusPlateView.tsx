import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import type { JanusCell } from "@/lib/echoJanusAdapter";
import { parseJanusName } from "@/lib/echoJanusAdapter";
import {
  PlateCellPopover,
  PlateColumnHeaderRow,
  PlateRowHeader,
  PlateWellCell,
} from "./PlatePreviewGrid";
import {
  PLATE_FILL_FORWARD,
  PLATE_FILL_REVERSE,
  PLATE_PREVIEW_FRAME,
  PLATE_PREVIEW_LABEL,
} from "@/lib/platePreviewStyles";

export type { JanusCell };

interface Props {
  rack1: JanusCell[];
  rack2: JanusCell[];
  className?: string;
}

const ROWS = ["A", "B", "C", "D", "E", "F", "G", "H"] as const;
const COLS = Array.from({ length: 12 }, (_, i) => i + 1);

/**
 * Resolve display mutation + F/R tag for a preview cell.
 *
 * The tag follows `JanusCell.rack`, which is the index of the panel the cell
 * is drawn in (1 = forward source, 2 = reverse source) and never a deck
 * position: the instrument addresses its plates by name (`asp_rack`), so a
 * number here would name nothing on the deck. Mutation prefers `cell.mutation`
 * (backend canonical key from Phase 2) and falls back to
 * `parseJanusName(cell.name)` for legacy fixtures lacking the field.
 */
function rackTag(rack: 1 | 2): "F" | "R" {
  return rack === 1 ? "F" : "R";
}

function Rack({
  rack,
  cells,
  label,
  labelTestId,
  tone,
}: {
  rack: 1 | 2;
  cells: JanusCell[];
  label: string;
  labelTestId: string;
  tone: "fwd" | "rev";
}) {
  const { t } = useTranslation();
  const byWell = new Map(cells.map((c) => [c.well, c]));
  const filledBg = tone === "fwd" ? PLATE_FILL_FORWARD : PLATE_FILL_REVERSE;
  const emptyBg =
    tone === "fwd"
      ? "bg-blue-50 dark:bg-blue-950/30"
      : "bg-orange-50 dark:bg-orange-950/30";

  return (
    <div className="plate-preview-grid min-w-[340px] flex-1 overflow-hidden">
      <div
        data-testid={labelTestId}
        className={PLATE_PREVIEW_LABEL}
      >
        {label}
      </div>
      {/* inline-grid + minmax(min,cap): see EchoPlateView.tsx for why 1fr was
          replaced. Cap is shared with Echo/Dest so a wide rack converges on
          the same well size instead of drifting from Dest's 12-column grid. */}
      <div
        role="grid"
        aria-label={t("exportPreview.janusGridAriaLabel", { label })}
        className="inline-grid gap-px"
        style={{
          gridTemplateColumns:
            "auto repeat(12, minmax(var(--plate-preview-cell-min-tiny), var(--plate-preview-cell-cap)))",
        }}
      >
        <PlateColumnHeaderRow cols={COLS} />
        {ROWS.map((r) => (
          <div key={r} role="row" className="contents">
            <PlateRowHeader row={r} />

            {COLS.map((c) => {
              const well = `${r}${c}`;
              const cell = byWell.get(well);
              const tip = cell
                ? `${cell.name} (${cell.volumeUl} µL), well ${well}`
                : well;

              if (!cell) {
                return (
                  <PlateWellCell
                    key={well}
                    testId="janus-cell"
                    row={r}
                    well={well}
                    rack={rack}
                    title={tip}
                    fillClassName={emptyBg}
                  />
                );
              }

              const mutation = cell.mutation || parseJanusName(cell.name).mutation;
              const tag = rackTag(cell.rack);

              return (
                <PlateWellCell
                  key={well}
                  testId="janus-cell"
                  row={r}
                  well={well}
                  rack={rack}
                  title={tip}
                  cellClassName="plate-preview-cell-narrow"
                  contentClassName="flex-col items-center"
                  fillClassName={filledBg}
                  popover={
                    <PlateCellPopover
                      title={cell.name}
                      rows={[
                        {
                          label: t("exportPreview.janusPopoverWellLabel"),
                          value: <span>{cell.well}</span>,
                        },
                        {
                          label: t("exportPreview.janusPopoverVolumeLabel"),
                          value: <span>{cell.volumeUl} µL</span>,
                        },
                      ]}
                    />
                  }
                >
                  {/* Mutation label matches DestPlateView's text-white on
                      a saturated fill. The F/R tag used text-muted-foreground,
                      a token meant for card backgrounds, on bg-blue-400/
                      bg-orange-400 it was nearly invisible (flagged from a
                      1900px screenshot). text-white/75 keeps it visibly
                      secondary to the mutation label while staying legible
                      on both fill colors in light and dark. */}
                  <span className="font-mono leading-none w-full text-center truncate text-white">
                    {mutation}
                  </span>
                  <span className="text-[0.85em] leading-none text-white/75 w-full text-center truncate">
                    {tag}
                  </span>
                </PlateWellCell>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}

export function JanusPlateView({ rack1, rack2, className }: Props) {
  const { t } = useTranslation();
  return (
    // No `plate-preview-grid` here on purpose: JANUS's container-type sits
    // on each Rack (index.css:225-237 tuned .plate-preview-cell-narrow
    // against a single rack's width, roughly half this row). Making the pair
    // a query container as well would re-anchor the racks to the wider box
    // and double every clamped font size.
    <div className={cn(PLATE_PREVIEW_FRAME, className)}>
      {/* min-w on the rack row, not on the scroller above it. */}
      <div className="flex gap-4 min-w-[700px]">
      <Rack
        rack={1}
        cells={rack1}
        label={t("exportPreview.forwardSourceLabel")}
        labelTestId="janus-forward-source-label"
        tone="fwd"
      />
      <Rack
        rack={2}
        cells={rack2}
        label={t("exportPreview.reverseSourceLabel")}
        labelTestId="janus-reverse-source-label"
        tone="rev"
      />
      </div>
    </div>
  );
}
