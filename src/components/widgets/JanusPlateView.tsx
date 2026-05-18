import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";

// Inline type until T1 adapter (src/lib/echoJanusAdapter.ts) is added.
// Keep in sync with the JanusCell interface defined in the plan
// (docs/plans/2026-05-18-echo-janus-export-preview.md).
export interface JanusCell {
  well: string;
  rowLetter: string;
  colNumber: number;
  rack: 1 | 2;
  name: string;
  volumeUl: number;
}

interface Props {
  rack1: JanusCell[];
  rack2: JanusCell[];
  className?: string;
}

const ROWS = ["A", "B", "C", "D", "E", "F", "G", "H"] as const;
const COLS = Array.from({ length: 12 }, (_, i) => i + 1);

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
  tone: "fwd" | "dest";
}) {
  const byWell = new Map(cells.map((c) => [c.well, c]));
  const filledBg =
    tone === "fwd"
      ? "bg-blue-400 dark:bg-blue-500"
      : "bg-emerald-400 dark:bg-emerald-500";
  const emptyBg =
    tone === "fwd"
      ? "bg-blue-50 dark:bg-blue-950/30"
      : "bg-emerald-50 dark:bg-emerald-950/30";

  return (
    <div className="min-w-[340px] flex-1">
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
          <>
            <div
              key={`label-${r}`}
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
              return (
                <div
                  key={well}
                  data-testid="janus-cell"
                  data-rack={rack}
                  data-well={well}
                  data-row={r}
                  title={tip}
                  className={cn(
                    "aspect-square rounded-[2px] border border-border/50",
                    cell ? filledBg : emptyBg,
                  )}
                />
              );
            })}
          </>
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
        tone="dest"
      />
    </div>
  );
}
