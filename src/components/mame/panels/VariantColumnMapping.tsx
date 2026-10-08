/**
 * VariantColumnMapping, "which rows of this file are the variants".
 *
 * MAME used to accept only a KURO export as the expected list. It now reads a
 * plain variant list too, which means somebody has to say which sheet and which
 * column carry the labels. This is that control, sitting under the expected-list
 * file field.
 *
 * Follows the convention the KURO input step set in
 * `src/components/panels/InputPanel/SourceColumnPanel.tsx`: the auto-detected
 * choice is a first-class option in the same Select (`__auto__`), so "let the
 * backend decide" is visible and reversible rather than an empty field. Two
 * differences, both because the backend offers no more than this:
 *   - no ranking column. MAME reads labels, not scores.
 *   - no preview table and no Apply button. `inspect_variant_source` returns
 *     sheets, headers and a suggestion, no rows; and the chosen values travel
 *     with the next validate/analyze call, so there is nothing to apply.
 *
 * Hidden entirely for a KURO export: `is_kuro_export` means the reader knows
 * its own sheet and column, and offering a picker that changes nothing is worse
 * than offering none.
 */

import { useId } from "react";
import { useTranslation } from "react-i18next";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

/** Same sentinel the KURO panel uses for "let the backend detect it". */
const AUTO_SENTINEL = "__auto__";

/** csv has no sheets; `inspect_variant_source` keys its headers under "". */
const CSV_HEADER_KEY = "";

export function VariantColumnMapping() {
  const { t } = useTranslation();
  const info = useMameAppStore((s) => s.variantSourceInfo);
  const variantSheet = useMameAppStore((s) => s.variantSheet);
  const variantColumn = useMameAppStore((s) => s.variantColumn);
  const setVariantSheet = useMameAppStore((s) => s.setVariantSheet);
  const setVariantColumn = useMameAppStore((s) => s.setVariantColumn);

  const sheetId = useId();
  const columnId = useId();

  // Nothing inspected yet, or a file the backend reads on its own terms.
  if (info === null || info.is_kuro_export) return null;

  const activeSheet = variantSheet ?? info.sheets[0] ?? CSV_HEADER_KEY;
  const headers = (
    info.headers[activeSheet] ??
    info.headers[CSV_HEADER_KEY] ??
    []
  ).filter((header) => header !== "");

  return (
    <section
      data-testid="variant-column-mapping"
      aria-label={t("mame.inputPanel.variantMapping.heading")}
      className="space-y-2 rounded-control border border-border bg-muted/20 px-3 py-2.5"
    >
      <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {t("mame.inputPanel.variantMapping.heading")}
      </h4>

      {info.sheets.length > 1 && (
        <div className="space-y-1">
          <Label htmlFor={sheetId} className="text-xs font-medium">
            {t("mame.inputPanel.variantMapping.sheetLabel")}
          </Label>
          <Select value={activeSheet} onValueChange={setVariantSheet}>
            <SelectTrigger id={sheetId} className="h-7 min-w-0 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {info.sheets.map((sheet) => (
                <SelectItem key={sheet} value={sheet} className="text-xs">
                  {sheet}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}

      <div className="space-y-1">
        <Label htmlFor={columnId} className="text-xs font-medium">
          {t("mame.inputPanel.variantMapping.columnLabel")}
        </Label>
        <Select
          value={variantColumn ?? AUTO_SENTINEL}
          onValueChange={(value) =>
            setVariantColumn(value === AUTO_SENTINEL ? null : value)
          }
          disabled={headers.length === 0}
        >
          <SelectTrigger id={columnId} className="h-7 min-w-0 text-xs">
            <SelectValue
              placeholder={t("mame.inputPanel.variantMapping.columnAuto")}
            />
          </SelectTrigger>
          <SelectContent>
            <SelectItem
              value={AUTO_SENTINEL}
              className="text-xs text-muted-foreground"
            >
              {t("mame.inputPanel.variantMapping.columnAuto")}
            </SelectItem>
            {headers.map((header) => (
              <SelectItem key={header} value={header} className="font-mono text-xs">
                {header}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <p className="text-caption text-muted-foreground">
          {info.suggested_column
            ? t("mame.inputPanel.variantMapping.suggested", {
                column: info.suggested_column,
              })
            : t("mame.inputPanel.variantMapping.noSuggestion")}
        </p>
      </div>

      <p className="text-caption text-muted-foreground">
        {t("mame.inputPanel.variantMapping.helper")}
      </p>
    </section>
  );
}
