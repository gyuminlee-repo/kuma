import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { buildPositionColorMap } from "./resultTableColumns";

export interface EvolveproSelectRow {
  variant: string;
  yPred: number;
  aaPosition: number | null;
  selected: boolean;
}

interface EvolveproSelectTableProps {
  rows: EvolveproSelectRow[];
  onToggle: (variant: string, checked: boolean) => void;
}

/**
 * Pre-design candidate selection table for EVOLVEpro.
 * Rows are sorted by y_pred descending (stable on ties).
 * Duplicate aa-position variants receive a coloured Pos{n} badge.
 */
export function EvolveproSelectTable({ rows, onToggle }: EvolveproSelectTableProps) {
  const { t } = useTranslation();

  const sorted = useMemo(
    () => [...rows].sort((a, b) => b.yPred - a.yPred),
    [rows],
  );

  const colorMap = useMemo(
    () => buildPositionColorMap(sorted.map((r) => r.aaPosition)),
    [sorted],
  );

  if (sorted.length === 0) {
    return (
      <div className="flex items-center justify-center py-8 text-muted-foreground text-sm">
        No candidates to display.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="border-b border-border">
            <th
              scope="col"
              className="w-10 px-2 py-2 text-left font-medium text-muted-foreground"
            >
              #
            </th>
            <th
              scope="col"
              className="px-2 py-2 text-left font-medium text-muted-foreground"
            >
              Mutation
            </th>
            <th
              scope="col"
              className="w-20 px-2 py-2 text-right font-medium text-muted-foreground"
            >
              y_pred
            </th>
            <th
              scope="col"
              className="w-16 px-2 py-2 text-center font-medium text-muted-foreground"
            >
              {t("resultTable.includeHeader")}
            </th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((row, index) => {
            const badgeColor =
              row.aaPosition != null ? colorMap.get(row.aaPosition) : undefined;
            return (
              <tr
                key={row.variant}
                className={`border-b border-border last:border-0 hover:bg-muted/30 transition-colors${
                  row.selected ? "" : " opacity-55"
                }`}
                aria-label={
                  row.selected
                    ? undefined
                    : t("resultTable.excludedRowAriaLabel", { mutation: row.variant })
                }
              >
                <td className="px-2 py-1.5 text-muted-foreground tabular-nums">
                  {index + 1}
                </td>
                <td className="px-2 py-1.5 min-w-0">
                  <span className="font-mono font-medium flex items-center gap-1 flex-wrap">
                    <span>{row.variant}</span>
                    {badgeColor && (
                      <span
                        className="inline-block px-1 rounded-control text-plate-tiny font-semibold text-white align-middle"
                        style={{ backgroundColor: badgeColor }}
                      >
                        Pos{row.aaPosition}
                      </span>
                    )}
                  </span>
                </td>
                <td className="px-2 py-1.5 text-right text-muted-foreground tabular-nums">
                  {row.yPred.toFixed(3)}
                </td>
                <td className="px-2 py-1.5 text-center">
                  <input
                    type="checkbox"
                    className="h-4 w-4 rounded-control accent-primary"
                    checked={row.selected}
                    aria-label={t("resultTable.includeAriaLabel", { mutation: row.variant })}
                    title={
                      row.selected
                        ? t("resultTable.excludeTitle")
                        : t("resultTable.includeTitle")
                    }
                    onChange={(e) => onToggle(row.variant, e.currentTarget.checked)}
                  />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
