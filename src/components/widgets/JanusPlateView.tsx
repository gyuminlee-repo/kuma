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
 * Resolve display mutation + F/R tag for a rack cell.
 *
 * Tag comes from rack number (Rack 1 = forward source, Rack 2 = reverse
 * source, per Phase 1 layout). Mutation prefers `cell.mutation` (backend
 * canonical key from Phase 2) and falls back to `parseJanusName(cell.name)`
 * for legacy fixtures lacking the field.
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
    <div className="min-w-[340px] flex-1 overflow-hidden">
      <div
        data-testid={labelTestId}
        className="text-caption text-muted-foreground mb-1"
      >
        {label}
      </div>
      <div className="grid grid-cols-[auto_repeat(12,1fr)] gap-px">
        <div />
        {COLS.map((c) => (
          <div
            key={c}
            className="text-caption text-center text-muted-foreground"
          >
            {c}
          </div>
        ))}
        {ROWS.map((r) => (
          <div key={r} className="contents">
            <div
              data-row-label={r}
              aria-label={`Row ${r}`}
              className="text-caption text-muted-foreground text-right pr-1 before:content-[attr(data-row-label)]"
            />

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
              const cellNode = (
                <div
                  data-testid="janus-cell"
                  data-rack={rack}
                  data-well={well}
                  data-row={r}
                  title={tip}
                  className={cn(
                    "aspect-square rounded-[2px] border border-border/50 flex flex-col items-center justify-center overflow-hidden p-0",
                    cell ? filledBg : emptyBg,
                    cell ? "cursor-pointer" : "",
                  )}
                >
                  {cell ? (
                    <>
                      <span className="text-[10px] font-mono leading-none w-full text-center truncate">
                        {mutation}
                      </span>
                      {tag ? (
                        <span className="text-[9px] leading-none text-muted-foreground w-full text-center truncate">
                          {tag}
                        </span>
                      ) : null}
                    </>
                  ) : null}
                </div>
              );
              if (!cell) {
                return <div key={well}>{cellNode}</div>;
              }
              return (
                <Popover key={well}>
                  <PopoverTrigger asChild>{cellNode}</PopoverTrigger>
                  <PopoverContent className="w-auto text-xs">
                    <div className="space-y-1">
                      <div className="font-mono font-medium">{cell.name}</div>
                      <div>Well: {cell.well}</div>
                      <div>Rack: {cell.rack}</div>
                      <div>Volume: {cell.volumeUl} µL</div>
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
        label={t("exportPreview.rack1Label")}
        labelTestId="janus-rack1-label"
        tone="fwd"
      />
      <Rack
        rack={2}
        cells={rack2}
        label={t("exportPreview.rack2Label")}
        labelTestId="janus-rack2-label"
        tone="rev"
      />
    </div>
  );
}
