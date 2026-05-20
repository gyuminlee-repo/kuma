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

export function EvolveproOthersPanel() {
  const { t } = useTranslation();

  const othersSourcePath = useAppStore((s) => s.othersSourcePath);
  const othersPreview = useAppStore((s) => s.othersPreview);
  const othersVariantColumn = useAppStore((s) => s.othersVariantColumn);
  const othersScoreColumn = useAppStore((s) => s.othersScoreColumn);
  const othersScoreOrder = useAppStore((s) => s.othersScoreOrder);
  const othersSheetName = useAppStore((s) => s.othersSheetName);
  const setOthersPreview = useAppStore((s) => s.setOthersPreview);
  const setOthersVariantColumn = useAppStore((s) => s.setOthersVariantColumn);
  const setOthersScoreColumn = useAppStore((s) => s.setOthersScoreColumn);
  const setOthersScoreOrder = useAppStore((s) => s.setOthersScoreOrder);
  const setOthersSheetName = useAppStore((s) => s.setOthersSheetName);
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
    othersSourcePath.toLowerCase().endsWith(".xlsx") ||
    othersSourcePath.toLowerCase().endsWith(".xls");

  const showSheetPicker =
    isXlsx && othersPreview !== null && othersPreview.sheets.length > 1;

  const headers = othersPreview?.headers ?? [];
  const hasHeaders = headers.length > 0;
  const canApply = Boolean(othersSourcePath && othersVariantColumn && othersScoreColumn);

  const handlePreview = useCallback(async () => {
    if (!othersSourcePath) return;
    setPreviewLoading(true);
    setPreviewError(null);
    try {
      const params: PreviewEvolveproSourceParams = {
        filepath: othersSourcePath,
        max_rows: PREVIEW_MAX_ROWS,
        sheet_name: othersSheetName ?? null,
      };
      const preview = await sendRequest("preview_evolvepro_source", params);
      setOthersPreview(preview);
      setOthersVariantColumn(null);
      setOthersScoreColumn(null);
    } catch (err) {
      setPreviewError(err instanceof Error ? err.message : String(err));
      setOthersPreview(null);
    } finally {
      setPreviewLoading(false);
    }
  }, [
    othersSourcePath,
    othersSheetName,
    setOthersPreview,
    setOthersVariantColumn,
    setOthersScoreColumn,
  ]);

  const handleSheetChange = useCallback(
    (value: string) => {
      setOthersSheetName(value === "__first__" ? null : value);
      setOthersPreview(null);
      setOthersVariantColumn(null);
      setOthersScoreColumn(null);
    },
    [setOthersSheetName, setOthersPreview, setOthersVariantColumn, setOthersScoreColumn],
  );

  const handleApply = useCallback(async () => {
    if (!canApply) return;
    setApplyLoading(true);
    setApplyError(null);
    try {
      await loadEvolveproCsv(othersSourcePath);
    } catch (err) {
      setApplyError(err instanceof Error ? err.message : String(err));
    } finally {
      setApplyLoading(false);
    }
  }, [canApply, loadEvolveproCsv, othersSourcePath]);

  const noFileLoaded = !othersSourcePath;

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
          {!previewLoading && !previewError && othersPreview === null && !noFileLoaded && (
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
            value={othersSheetName ?? "__first__"}
            onValueChange={handleSheetChange}
          >
            <SelectTrigger id={sheetId} className="h-7 text-xs">
              <SelectValue placeholder={t("mutationInput.othersSheetNamePlaceholder")} />
            </SelectTrigger>
            <SelectContent>
              {othersPreview.sheets.map((sheet) => (
                <SelectItem key={sheet} value={sheet} className="text-xs">
                  {sheet}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
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
            value={othersVariantColumn ?? "__auto__"}
            onValueChange={(v) =>
              setOthersVariantColumn(v === "__auto__" ? null : v)
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
        </div>

        <div className="space-y-1">
          <Label htmlFor={scoreColId} className="text-xs font-medium">
            {t("mutationInput.othersScoreColumn")}
          </Label>
          <Select
            value={othersScoreColumn ?? "__auto__"}
            onValueChange={(v) =>
              setOthersScoreColumn(v === "__auto__" ? null : v)
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
              name="othersScoreOrder"
              className="w-3 h-3"
              checked={othersScoreOrder === "desc"}
              onChange={() => setOthersScoreOrder("desc")}
            />
            <span className="text-foreground">
              {t("mutationInput.othersScoreOrderDesc")}
            </span>
          </label>
          <label className="flex items-center gap-1.5 cursor-pointer text-xs">
            <input
              type="radio"
              name="othersScoreOrder"
              className="w-3 h-3"
              checked={othersScoreOrder === "asc"}
              onChange={() => setOthersScoreOrder("asc")}
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

      {othersPreview !== null && othersPreview.rows.length > 0 && (
        <div className="overflow-auto rounded-xl border border-border">
          <Table>
            <caption className="sr-only">
              {t("mutationInput.othersPreviewBtn")}
            </caption>
            <TableHeader>
              <TableRow>
                {othersPreview.headers.map((h) => (
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
              {othersPreview.rows.map((row, ri) => (
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
