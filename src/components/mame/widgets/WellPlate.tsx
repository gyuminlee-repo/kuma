import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import type { WellEntry, VerdictClass } from "@/types/mame/models";

const ROWS = ["A", "B", "C", "D", "E", "F", "G", "H"] as const;
const COLS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12] as const;

const verdictFill: Record<VerdictClass, { bg: string; text: string; border: string }> = {
  PASS: { bg: "#2E7D32", text: "#FFFFFF", border: "#1B5E20" },
  AMBIGUOUS: { bg: "#F9A825", text: "#1A1200", border: "#F57F17" },
  WRONG_AA: { bg: "#C62828", text: "#FFFFFF", border: "#B71C1C" },
  FRAMESHIFT: { bg: "#AD1457", text: "#FFFFFF", border: "#880E4F" },
  MANY: { bg: "#E65100", text: "#FFFFFF", border: "#BF360C" },
  LOWDEPTH: { bg: "#9E9E9E", text: "#FFFFFF", border: "#757575" },
};

const emptyFill = { bg: "#F1F3F5", text: "#C1C8D0", border: "#DDE1E7" };

const cbPatterns: Partial<Record<VerdictClass, string>> = {
  PASS: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='6' height='6'%3E%3Cline x1='0' y1='6' x2='6' y2='0' stroke='rgba(255,255,255,0.20)' stroke-width='1'/%3E%3C/svg%3E")`,
  AMBIGUOUS: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='6' height='6'%3E%3Ccircle cx='3' cy='3' r='1' fill='rgba(0,0,0,0.15)'/%3E%3C/svg%3E")`,
  WRONG_AA: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='6' height='6'%3E%3Cline x1='0' y1='0' x2='6' y2='6' stroke='rgba(255,255,255,0.20)' stroke-width='1'/%3E%3Cline x1='0' y1='6' x2='6' y2='0' stroke='rgba(255,255,255,0.20)' stroke-width='1'/%3E%3C/svg%3E")`,
  FRAMESHIFT: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='4' height='4'%3E%3Crect x='0' y='0' width='2' height='2' fill='rgba(255,255,255,0.18)'/%3E%3C/svg%3E")`,
  MANY: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='6' height='6'%3E%3Cline x1='3' y1='0' x2='3' y2='6' stroke='rgba(255,255,255,0.20)' stroke-width='1'/%3E%3C/svg%3E")`,
};

const plateGridTemplate = "24px repeat(12, minmax(34px, 1fr))";
const plateGridGap = "4px";

function getPlateBadge(barcode: string): "NB01" | "NB02" | "NB03" | null {
  const match = barcode.match(/^([1-3])_/);
  if (!match) return null;
  return `NB0${match[1]}` as "NB01" | "NB02" | "NB03";
}

/** Color override: { bg, text, border } hex strings. null/undefined = use verdict default. */
export type WellColorOverride = { bg: string; text: string; border: string };

interface WellPlateProps {
  wells: WellEntry[];
  onWellClick?: (well: WellEntry) => void;
  selectedWellId?: string;
  colorblindMode?: boolean;
  /** Optional callback to override per-well fill colors. Default = verdict-mode. */
  wellColorOf?: (well: WellEntry) => WellColorOverride | null;
}

export function WellPlate({
  wells,
  onWellClick,
  selectedWellId,
  colorblindMode = false,
  wellColorOf,
}: WellPlateProps) {
  const { t } = useTranslation();
  const wellMap = new Map(wells.map((w) => [w.well, w]));

  return (
    <div className="w-full overflow-x-auto rounded-container border border-border/70 bg-card p-2.5" role="grid" aria-label={t("wellPlate.gridAriaLabel")}>
      <div
        className="grid items-center text-center"
        style={{ gridTemplateColumns: plateGridTemplate, gap: plateGridGap }}
      >
        <div className="font-display text-caption uppercase tracking-widest text-muted-foreground" aria-hidden="true">
          R
        </div>
        {COLS.map((col) => (
          <div
            key={col}
            className="rounded-full bg-muted/55 py-1 text-center text-caption font-semibold text-muted-foreground"
            aria-label={t("wellPlate.columnAriaLabel", { col })}
          >
            {col}
          </div>
        ))}
      </div>

      <div className="mt-1.5 space-y-1" role="rowgroup">
        {ROWS.map((row) => (
          <div
            key={row}
            className="grid items-center"
            style={{ gridTemplateColumns: plateGridTemplate, gap: plateGridGap }}
            role="row"
          >
            <div
              className="font-display text-center text-caption font-semibold text-muted-foreground"
              aria-label={t("wellPlate.rowAriaLabel", { row })}
              role="rowheader"
            >
              {row}
            </div>

            {COLS.map((col) => {
              const id = `${row}${col}`;
              const well = wellMap.get(id);
              const isFocused = selectedWellId === id;
              const plate = well ? getPlateBadge(well.barcode) : null;
              const fill = well
                ? (wellColorOf?.(well) ?? verdictFill[well.verdict])
                : emptyFill;
              const pattern = colorblindMode && well ? cbPatterns[well.verdict] : undefined;
              const isFallback = well?.is_fallback ?? false;

              return (
                <div
                  key={id}
                  role="gridcell"
                  aria-label={`Well ${id}${well ? `: ${well.verdict}${isFallback ? " (fallback)" : ""}` : " empty"}`}
                >
                  <button
                    type="button"
                    disabled={!well}
                    onClick={() => well && onWellClick?.(well)}
                    aria-pressed={isFocused}
                    title={well?.mutant_id || undefined}
                    className={cn(
                      "well-button relative flex aspect-square w-full flex-col items-stretch justify-between overflow-hidden rounded-md border text-center shadow-sm",
                      "text-plate font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-ring",
                      !well && "cursor-default",
                      isFocused && "well-button-selected",
                      well?.selected && "shadow-md",
                    )}
                    style={{
                      backgroundColor: fill.bg,
                      color: fill.text,
                      borderColor: isFocused ? "hsl(var(--ring))" : fill.border,
                      borderWidth: isFocused ? "2px" : "1px",
                      backgroundImage: pattern,
                    }}
                  >
                    {/* Well ID label (plate token 10px) */}
                    <span className="font-display text-caption font-semibold leading-tight">{id}</span>
                    {well && (
                      <span
                        className="min-w-0 flex-1 truncate px-0.5 text-plate-tiny leading-tight opacity-85"
                        title={well.mutant_id || undefined}
                      >
                        {well.mutant_id || "-"}
                      </span>
                    )}
                    {/* Badge row at bottom (flex, no absolute positioning) */}
                    {(well?.selected || isFallback || plate) && (
                      <div className="flex h-3 w-full items-center justify-between gap-0.5 px-0.5">
                        <div className="flex items-center gap-0.5">
                          {well?.selected && (
                            <span
                              className="inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-card"
                              aria-label="Pick"
                              title="Pick"
                            />
                          )}
                          {isFallback && (
                            <span
                              className="inline-flex shrink-0 items-center justify-center rounded-full bg-warning/80 p-[1px]"
                              aria-hidden="true"
                              title={t("wellPlate.fallbackReplicateTitle")}
                            >
                              <svg
                                width="7"
                                height="7"
                                viewBox="0 0 16 16"
                                fill="none"
                                xmlns="http://www.w3.org/2000/svg"
                                aria-hidden="true"
                              >
                                <path
                                  d="M8 2L14.928 14H1.072L8 2Z"
                                  fill="currentColor"
                                  className="text-warning-foreground"
                                />
                                <path d="M8 6v4M8 11v1" stroke="hsl(var(--warning-foreground, 0 0% 10%))" strokeWidth="1.5" strokeLinecap="round" />
                              </svg>
                            </span>
                          )}
                        </div>
                        {plate && (
                          <span
                            className="shrink-0 rounded-full px-0.5 text-[7px] font-bold leading-none"
                            style={{
                              backgroundColor: "rgba(0,0,0,0.25)",
                              color: fill.text,
                            }}
                            aria-hidden="true"
                          >
                            {plate}
                          </span>
                        )}
                      </div>
                    )}
                  </button>
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}
