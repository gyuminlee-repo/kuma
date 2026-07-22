import { useCallback, useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAppStore } from "../../../store/appStore";
import { sendRequest } from "../../../lib/ipc-kuro";
import type { PreviewEvolveproSourceParams } from "../../../types/models.generated";
import { Button } from "../../ui/button";
import { Label } from "../../ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../../ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../../ui/table";

const PREVIEW_MAX_ROWS = 5;

/**
 * Column mapping panel for the single EVOLVEpro/Others file loader.
 * Always rendered once a file is selected, column overrides are optional;
 * leaving both at "auto" (__auto__ / null) delegates detection to the
 * backend's VARIANT_COLUMNS/SCORE_COLUMNS alias matching
 * (kuma_core/kuro/evolvepro.py:_load_evolvepro_rows).
 */
export function SourceColumnPanel() {
  const { t } = useTranslation();

  const evolveproCsvPath = useAppStore((s) => s.evolveproCsvPath);
  const evolveproPreview = useAppStore((s) => s.evolveproPreview);
  const evolveproVariantColumn = useAppStore((s) => s.evolveproVariantColumn);
  const evolveproScoreColumn = useAppStore((s) => s.evolveproScoreColumn);
  const evolveproScoreOrder = useAppStore((s) => s.evolveproScoreOrder);
  const evolveproSheetName = useAppStore((s) => s.evolveproSheetName);
  const evolveproUsedVariantColumn = useAppStore((s) => s.evolveproUsedVariantColumn);
  const evolveproUsedScoreColumn = useAppStore((s) => s.evolveproUsedScoreColumn);
  const setEvolveproPreview = useAppStore((s) => s.setEvolveproPreview);
  const setEvolveproVariantColumn = useAppStore((s) => s.setEvolveproVariantColumn);
  const setEvolveproScoreColumn = useAppStore((s) => s.setEvolveproScoreColumn);
  const setEvolveproScoreOrder = useAppStore((s) => s.setEvolveproScoreOrder);
  const setEvolveproSheetName = useAppStore((s) => s.setEvolveproSheetName);
  const loadEvolveproCsv = useAppStore((s) => s.loadEvolveproCsv);

  const [previewLoading, setPreviewLoading] = useState(false);
  const [applyLoading, setApplyLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [applyError, setApplyError] = useState<string | null>(null);

  const scoreOrderId = useId();
  const variantColId = useId();
  const scoreColId = useId();
  const sheetId = useId();
  const previewStatusId = useId();

  const isXlsx =
    evolveproCsvPath.toLowerCase().endsWith(".xlsx") ||
    evolveproCsvPath.toLowerCase().endsWith(".xls");

  const showSheetPicker =
    isXlsx && evolveproPreview !== null && evolveproPreview.sheets.length > 1;

  const headers = evolveproPreview?.headers ?? [];
  const hasHeaders = headers.length > 0;
  const canApply = Boolean(evolveproCsvPath);
  const noFileLoaded = !evolveproCsvPath;

  const handlePreview = useCallback(async () => {
    if (!evolveproCsvPath) return;
    setPreviewLoading(true);
    setPreviewError(null);
    try {
      const params: PreviewEvolveproSourceParams = {
        filepath: evolveproCsvPath,
        max_rows: PREVIEW_MAX_ROWS,
        sheet_name: evolveproSheetName ?? null,
      };
      const preview = await sendRequest("preview_evolvepro_source", params);
      setEvolveproPreview(preview);
      setEvolveproVariantColumn(null);
      setEvolveproScoreColumn(null);
    } catch (err) {
      setPreviewError(err instanceof Error ? err.message : String(err));
      setEvolveproPreview(null);
    } finally {
      setPreviewLoading(false);
    }
  }, [
    evolveproCsvPath,
    evolveproSheetName,
    setEvolveproPreview,
    setEvolveproVariantColumn,
    setEvolveproScoreColumn,
  ]);

  const handleSheetChange = useCallback(
    (value: string) => {
      setEvolveproSheetName(value === "__first__" ? null : value);
      setEvolveproPreview(null);
      setEvolveproVariantColumn(null);
      setEvolveproScoreColumn(null);
    },
    [setEvolveproSheetName, setEvolveproPreview, setEvolveproVariantColumn, setEvolveproScoreColumn],
  );

  const handleApply = useCallback(async () => {
    if (!canApply) return;
    setApplyLoading(true);
    setApplyError(null);
    try {
      await loadEvolveproCsv(evolveproCsvPath);
    } catch (err) {
      setApplyError(err instanceof Error ? err.message : String(err));
    } finally {
      setApplyLoading(false);
    }
  }, [canApply, loadEvolveproCsv, evolveproCsvPath]);

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <Button
          variant="outline"
          size="sm"
          disabled={noFileLoaded || previewLoading}
          onClick={() => void handlePreview()}
          aria-describedby={previewStatusId}
          className="flex-shrink-0"
        >
          {t("mutationInput.othersPreviewBtn")}
        </Button>
        <span
          id={previewStatusId}
          className="text-xs text-muted-foreground"
          aria-live="polite"
          aria-busy={previewLoading}
        >
          {previewLoading && t("mutationInput.othersPreviewLoading")}
          {!previewLoading && previewError && (
            <span className="text-destructive">
              {t("mutationInput.othersPreviewError", { message: previewError })}
            </span>
          )}
          {!previewLoading && !previewError && evolveproPreview === null && !noFileLoaded && (
            <span>{t("mutationInput.othersPreviewEmpty")}</span>
          )}
        </span>
      </div>

      {showSheetPicker && (
        <div className="space-y-1">
          <Label htmlFor={sheetId} className="text-xs font-medium">
            {t("mutationInput.othersSheetName")}
          </Label>
          <Select
            value={evolveproSheetName ?? "__first__"}
            onValueChange={handleSheetChange}
          >
            <SelectTrigger id={sheetId} className="h-7 text-xs">
              <SelectValue placeholder={t("mutationInput.othersSheetNamePlaceholder")} />
            </SelectTrigger>
            <SelectContent>
              {evolveproPreview.sheets.map((sheet) => (
                <SelectItem key={sheet} value={sheet} className="text-xs">
                  {sheet}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {evolveproUsedVariantColumn && (
            <div className="text-caption text-muted-foreground">
              {t("mutationInput.othersUsedColumn", { column: evolveproUsedVariantColumn })}
            </div>
          )}
        </div>
      )}

      <div className="space-y-2">
        <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          {t("mutationInput.othersColumnMapping")}
        </div>

        <div className="space-y-1">
          <Label htmlFor={variantColId} className="text-xs font-medium">
            {t("mutationInput.othersVariantColumn")}
          </Label>
          <Select
            value={evolveproVariantColumn ?? "__auto__"}
            onValueChange={(v) =>
              setEvolveproVariantColumn(v === "__auto__" ? null : v)
            }
            disabled={!hasHeaders}
          >
            <SelectTrigger id={variantColId} className="h-7 text-xs">
              <SelectValue
                placeholder={t("mutationInput.othersVariantColumnPlaceholder")}
              />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__auto__" className="text-xs text-muted-foreground">
                {t("mutationInput.othersVariantColumnPlaceholder")}
              </SelectItem>
              {headers.map((h) => (
                <SelectItem key={h} value={h} className="text-xs font-mono">
                  {h}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {evolveproUsedScoreColumn && (
            <div className="text-caption text-muted-foreground">
              {t("mutationInput.othersUsedColumn", { column: evolveproUsedScoreColumn })}
            </div>
          )}
        </div>

        <div className="space-y-1">
          <Label htmlFor={scoreColId} className="text-xs font-medium">
            {t("mutationInput.othersScoreColumn")}
          </Label>
          <Select
            value={evolveproScoreColumn ?? "__auto__"}
            onValueChange={(v) =>
              setEvolveproScoreColumn(v === "__auto__" ? null : v)
            }
            disabled={!hasHeaders}
          >
            <SelectTrigger id={scoreColId} className="h-7 text-xs">
              <SelectValue
                placeholder={t("mutationInput.othersScoreColumnPlaceholder")}
              />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__auto__" className="text-xs text-muted-foreground">
                {t("mutationInput.othersScoreColumnPlaceholder")}
              </SelectItem>
              {headers.map((h) => (
                <SelectItem key={h} value={h} className="text-xs font-mono">
                  {h}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div
          role="radiogroup"
          aria-labelledby={scoreOrderId}
          className="space-y-0.5"
        >
          <div id={scoreOrderId} className="text-xs font-medium">
            {t("mutationInput.othersScoreOrder")}
          </div>
          <label className="flex items-center gap-1.5 cursor-pointer text-xs">
            <input
              type="radio"
              name="evolveproScoreOrder"
              className="w-3 h-3"
              checked={evolveproScoreOrder === "desc"}
              onChange={() => setEvolveproScoreOrder("desc")}
            />
            <span className="text-foreground">
              {t("mutationInput.othersScoreOrderDesc")}
            </span>
          </label>
          <label className="flex items-center gap-1.5 cursor-pointer text-xs">
            <input
              type="radio"
              name="evolveproScoreOrder"
              className="w-3 h-3"
              checked={evolveproScoreOrder === "asc"}
              onChange={() => setEvolveproScoreOrder("asc")}
            />
            <span className="text-foreground">
              {t("mutationInput.othersScoreOrderAsc")}
            </span>
          </label>
        </div>
      </div>

      {applyError && (
        <div className="text-xs text-destructive">
          {t("mutationInput.othersApplyError", { message: applyError })}
        </div>
      )}

      <Button
        variant="secondary"
        size="sm"
        disabled={!canApply || applyLoading}
        onClick={() => void handleApply()}
      >
        {applyLoading ? t("common.loading") : t("mutationInput.othersApplyBtn")}
      </Button>

      {evolveproPreview !== null && evolveproPreview.rows.length > 0 && (
        <div className="overflow-auto rounded-xl border border-border">
          <Table>
            <caption className="sr-only">
              {t("mutationInput.othersPreviewBtn")}
            </caption>
            <TableHeader>
              <TableRow>
                {evolveproPreview.headers.map((h) => (
                  <TableHead
                    key={h}
                    scope="col"
                    className="text-xs font-mono py-1 px-2 h-auto"
                  >
                    {h}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {evolveproPreview.rows.map((row, ri) => (
                <TableRow key={ri}>
                  {row.map((cell, ci) => (
                    <TableCell
                      key={ci}
                      className="text-xs font-mono py-1 px-2"
                    >
                      {cell}
                    </TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
