import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import type { EchoCell } from "@/lib/echoJanusAdapter";
import { Popover, PopoverTrigger, PopoverContent } from "@/components/ui/popover";

const ROWS = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N", "O", "P"] as const;
const COLS = Array.from({ length: 24 }, (_, i) => i + 1);

interface Props {
  cells: EchoCell[];
  className?: string;
}

export function EchoPlateView({ cells, className }: Props) {
  const { t } = useTranslation();
  const byWell = new Map(cells.map((c) => [c.well, c]));
  return (
    <div className={cn("plate-preview-grid min-w-[700px] overflow-x-auto", className)}>
      {/* inline-grid + minmax(min,cap) instead of repeat(24,1fr): 1fr let a
          wide container stretch cells past what the 15px font ceiling could
          fill (77px cells at 1900px, 11% text coverage). minmax caps track
          width at --plate-preview-cell-cap (shared with Janus/Dest so a wide
          screen shows the same well size across all three), and inline-grid
          keeps the grid from being stretched to the wrapper's full width once
          the tracks stop growing (WellSelectionPanel.tsx:459 precedent). */}
      <div
        role="grid"
        aria-label={t("exportPreview.echoGridAriaLabel")}
        className="inline-grid gap-px"
        style={{
          gridTemplateColumns:
            "auto repeat(24, minmax(var(--plate-preview-cell-min-tiny), var(--plate-preview-cell-cap)))",
        }}
      >
        <div role="row" className="contents">
          <div />
          {COLS.map((c) => (
            <div key={c} role="columnheader" className="text-caption text-center text-muted-foreground">
              {c}
            </div>
          ))}
        </div>
        {ROWS.map((r, idx) => {
          const isFwdRow = idx % 2 === 0;
          return (
            <div key={r} role="row" className="contents">
              <div role="rowheader" className="text-caption text-muted-foreground text-right pr-1">{r}</div>
              {COLS.map((c) => {
                const well = `${r}${String(c).padStart(2, "0")}`;
                const cell = byWell.get(well);
                if (!cell) {
                  return (
                    <div
                      key={well}
                      role="gridcell"
                      data-testid="echo-cell"
                      data-row={r}
                      title={well}
                      className={cn(
                        "aspect-square rounded-[2px] border border-border/50",
                        isFwdRow ? "bg-blue-50 dark:bg-blue-950/30" : "bg-orange-50 dark:bg-orange-950/30",
                      )}
                    />
                  );
                }
                const mutation = cell.mutation || cell.sourceWellName;
                const tip = `${cell.sourceWellName} → ${cell.destPlate} ${cell.destWell} (${cell.transferVolNl} nL)`;
                return (
                  <Popover key={well}>
                    <PopoverTrigger asChild>
                      <button
                        type="button"
                        data-testid="echo-cell"
                        data-row={r}
                        title={tip}
                        className={cn(
                          "plate-preview-cell-tiny aspect-square rounded-[2px] border border-border/50 flex items-center justify-center overflow-hidden p-0",
                          "focus:outline-none focus:ring-1 focus:ring-ring",
                          isFwdRow ? "bg-blue-400 dark:bg-blue-500" : "bg-orange-400 dark:bg-orange-500",
                        )}
                      >
                        <span className="font-mono leading-none text-white truncate">
                          {mutation}
                        </span>
                      </button>
                    </PopoverTrigger>
                    <PopoverContent className="w-auto text-xs space-y-1">
                      <div>
                        <span className="text-muted-foreground">{t("exportPreview.echoPopoverPrimerLabel")} </span>
                        <span className="font-mono">{cell.sourceWellName}</span>
                      </div>
                      <div>
                        <span className="text-muted-foreground">{t("exportPreview.echoPopoverDirectionLabel")} </span>
                        <span>{cell.isFwd ? t("exportPreview.echoPopoverForward") : t("exportPreview.echoPopoverReverse")}</span>
                      </div>
                      <div>
                        <span className="text-muted-foreground">{t("exportPreview.echoPopoverSourceWellLabel")} </span>
                        <span className="font-mono">{cell.well}</span>
                      </div>
                      <div>
                        <span className="text-muted-foreground">{t("exportPreview.echoPopoverDestinationLabel")} </span>
                        <span className="font-mono">{cell.destPlate} {cell.destWell}</span>
                      </div>
                      <div>
                        <span className="text-muted-foreground">{t("exportPreview.echoPopoverTransferLabel")} </span>
                        <span>{cell.transferVolNl} nL</span>
                      </div>
                    </PopoverContent>
                  </Popover>
                );
              })}
            </div>
          );
        })}
      </div>
    </div>
  );
}
