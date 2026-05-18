import { cn } from "@/lib/utils";
import type { EchoCell } from "@/lib/echoJanusAdapter";

const ROWS = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N", "O", "P"] as const;
const COLS = Array.from({ length: 24 }, (_, i) => i + 1);

interface Props {
  cells: EchoCell[];
  className?: string;
}

export function EchoPlateView({ cells, className }: Props) {
  const byWell = new Map(cells.map((c) => [c.well, c]));
  return (
    <div className={cn("min-w-[700px] overflow-x-auto", className)}>
      <div className="grid grid-cols-[auto_repeat(24,1fr)] gap-px">
        <div />
        {COLS.map((c) => (
          <div key={c} className="text-caption text-center text-muted-foreground">
            {c}
          </div>
        ))}
        {ROWS.map((r, idx) => {
          const isFwdRow = idx % 2 === 0;
          return (
            <div key={r} className="contents">
              <div className="text-caption text-muted-foreground text-right pr-1">{r}</div>
              {COLS.map((c) => {
                const well = `${r}${String(c).padStart(2, "0")}`;
                const cell = byWell.get(well);
                const tip = cell
                  ? `${cell.sourceWellName} → ${cell.destPlate} ${cell.destWell} (${cell.transferVolNl} nL)`
                  : well;
                return (
                  <div
                    key={well}
                    data-testid="echo-cell"
                    data-row={r}
                    title={tip}
                    className={cn(
                      "aspect-square rounded-[2px] border border-border/50",
                      isFwdRow ? "bg-blue-50 dark:bg-blue-950/30" : "bg-orange-50 dark:bg-orange-950/30",
                      cell && (isFwdRow ? "bg-blue-400" : "bg-orange-400"),
                    )}
                  />
                );
              })}
            </div>
          );
        })}
      </div>
    </div>
  );
}
