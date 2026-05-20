import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import type { DestCell } from "@/lib/echoJanusAdapter";
import {
  Popover,
  PopoverTrigger,
  PopoverContent,
} from "@/components/ui/popover";

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
    <div className={cn("min-w-[400px] overflow-x-auto", className)}>
      {title ? (
        <div className="text-caption text-muted-foreground mb-1">{title}</div>
      ) : null}
      <div className="grid grid-cols-[auto_repeat(12,1fr)] gap-px">
        <div />
        {COLS.map((c) => (
          <div key={c} className="text-caption text-center text-muted-foreground">
            {c}
          </div>
        ))}
        {ROWS.map((r) => (
          <div key={r} className="contents">
            <div
              data-row-label={r}
              aria-label={`Row ${r}`}
              className="text-caption text-muted-foreground text-right pr-1"
            >
              {r}
            </div>
            {COLS.map((c) => {
              const well = wellKey(r, c);
              const cell = byWell.get(well);

              if (!cell) {
                return (
                  <div
                    key={well}
                    data-testid="dest-cell"
                    data-row={r}
                    data-well={well}
                    data-state="empty"
                    title={well}
                    className={cn(
                      "aspect-square rounded-[2px] border border-border/50",
                      "bg-muted/40 dark:bg-muted/20",
                    )}
                  />
                );
              }

              const complete = cell.hasF && cell.hasR;
              const state = complete ? "complete" : "partial";
              const bg = complete
                ? "bg-emerald-400 dark:bg-emerald-500"
                : "bg-amber-400 dark:bg-amber-500";
              const tip = `${cell.mutation} (${well}): F=${cell.hasF ? "✓" : "✗"} R=${cell.hasR ? "✓" : "✗"}`;

              return (
                <Popover key={well}>
                  <PopoverTrigger asChild>
                    <button
                      type="button"
                      data-testid="dest-cell"
                      data-row={r}
                      data-well={well}
                      data-state={state}
                      title={tip}
                      className={cn(
                        "aspect-square rounded-[2px] border border-border/50 flex items-center justify-center overflow-hidden p-0 cursor-pointer focus:outline-none focus:ring-1 focus:ring-ring",
                        bg,
                      )}
                    >
                      <span className="text-[8px] font-mono leading-none text-white truncate px-0.5">
                        {cell.mutation}
                      </span>
                    </button>
                  </PopoverTrigger>
                  <PopoverContent className="w-auto text-xs space-y-1">
                    <div className="font-mono font-medium">{cell.mutation}</div>
                    <div>
                      <span className="text-muted-foreground">
                        {t("exportPreview.destWell", { defaultValue: "Dest well" })}:{" "}
                      </span>
                      <span className="font-mono">{well}</span>
                    </div>
                    <div>
                      <span className="text-muted-foreground">F: </span>
                      {cell.hasF ? (
                        <span className="font-mono">
                          {cell.fwdSource ?? "?"} · {cell.fwdVol ?? "?"} {unit}
                        </span>
                      ) : (
                        <span className="text-amber-600 dark:text-amber-400">
                          {t("exportPreview.missing", { defaultValue: "missing" })}
                        </span>
                      )}
                    </div>
                    <div>
                      <span className="text-muted-foreground">R: </span>
                      {cell.hasR ? (
                        <span className="font-mono">
                          {cell.revSource ?? "?"} · {cell.revVol ?? "?"} {unit}
                        </span>
                      ) : (
                        <span className="text-amber-600 dark:text-amber-400">
                          {t("exportPreview.missing", { defaultValue: "missing" })}
                        </span>
                      )}
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
