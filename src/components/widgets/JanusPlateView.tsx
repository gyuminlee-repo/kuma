import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import {
  Popover,
  PopoverTrigger,
  PopoverContent,
} from "@/components/ui/popover";
import type { JanusCell } from "@/lib/echoJanusAdapter";
import { parseJanusName } from "@/lib/echoJanusAdapter";

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
  const filledBg =
    tone === "fwd"
      ? "bg-blue-400 dark:bg-blue-500"
      : "bg-orange-400 dark:bg-orange-500";
  const emptyBg =
    tone === "fwd"
      ? "bg-blue-50 dark:bg-blue-950/30"
      : "bg-orange-50 dark:bg-orange-950/30";

  return (
    <div className="plate-preview-grid min-w-[340px] flex-1 overflow-hidden">
      <div
        data-testid={labelTestId}
        className="text-caption text-muted-foreground mb-1"
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
        <div role="row" className="contents">
          <div />
          {COLS.map((c) => (
            <div
              key={c}
              role="columnheader"
              className="text-caption text-center text-muted-foreground"
            >
              {c}
            </div>
          ))}
        </div>
        {ROWS.map((r) => (
          <div key={r} role="row" className="contents">
            <div
              role="rowheader"
              aria-label={t("exportPreview.rowAriaLabel", { row: r })}
              className="text-caption text-muted-foreground text-right pr-1"
            >
              {r}
            </div>

            {COLS.map((c) => {
              const well = `${r}${c}`;
              const cell = byWell.get(well);
              const tip = cell
                ? `${cell.name} (${cell.volumeUl} µL), well ${well}`
                : well;
              const mutation = cell
                ? cell.mutation || parseJanusName(cell.name).mutation
                : "";
              const tag = cell ? rackTag(cell.rack) : null;

              if (!cell) {
                return (
                  <div
                    key={well}
                    role="gridcell"
                    data-testid="janus-cell"
                    data-rack={rack}
                    data-well={well}
                    data-row={r}
                    title={tip}
                    className={cn(
                      "aspect-square rounded-[2px] border border-border/50 flex flex-col items-center justify-center overflow-hidden p-0",
                      emptyBg,
                    )}
                  />
                );
              }

              return (
                <Popover key={well}>
                  <PopoverTrigger asChild>
                    <button
                      type="button"
                      role="gridcell"
                      data-testid="janus-cell"
                      data-rack={rack}
                      data-well={well}
                      data-row={r}
                      title={tip}
                      className={cn(
                        "plate-preview-cell-narrow aspect-square rounded-[2px] border border-border/50 flex flex-col items-center justify-center overflow-hidden p-0 cursor-pointer",
                        "focus:outline-none focus:ring-1 focus:ring-ring",
                        filledBg,
                      )}
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
                      {tag ? (
                        <span className="text-[0.85em] leading-none text-white/75 w-full text-center truncate">
                          {tag}
                        </span>
                      ) : null}
                    </button>
                  </PopoverTrigger>
                  <PopoverContent className="w-auto text-xs">
                    <div className="space-y-1">
                      <div className="font-mono font-medium">{cell.name}</div>
                      <div>
                        {t("exportPreview.janusPopoverWellLabel")} {cell.well}
                      </div>
                      <div>
                        {t("exportPreview.janusPopoverVolumeLabel")} {cell.volumeUl} µL
                      </div>
                    </div>
                  </PopoverContent>
                </Popover>
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
    <div className={cn("flex gap-4 min-w-[700px] overflow-x-auto", className)}>
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
  );
}
