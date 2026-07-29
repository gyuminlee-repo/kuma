/**
 * JanusMappingDialog — Export final cell-stock Janus mapping (K4 spec).
 *
 * Provides:
 *  - CSV / XLSX format selection (radio group)
 *  - Destination layout selection (source position vs compact from A1)
 *  - Row preview via the `export_janus_mapping_dry_run` RPC, refreshed when the
 *    dialog opens and whenever the destination layout changes
 *  - Output path with Browse button
 *  - Export button that calls sidecar `export_janus_mapping` RPC, blocked while
 *    the preview reports a plate-layout problem
 *  - Success / error feedback inline
 *
 * Entered via: File > Export Janus Mapping… in MenuBar.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { save } from "@tauri-apps/plugin-dialog";
import { AlertCircle, CheckCircle2, Download, FolderOpen } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useKumaProject } from "@/state/projectContext";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { JanusDeckPreview } from "@/components/mame/widgets/JanusDeckPreview";
import {
  buildJanusDefaultPath,
  fetchMameJanusPreview,
  handleExportMameJanusMapping,
} from "@/lib/mame/janus";
import { fileExists, requestOverwriteConfirm } from "@/lib/overwriteConfirm";
import type {
  JanusDestLayout,
  JanusExportFormat,
  JanusPreviewResult,
} from "@/types/mame/models";

interface JanusMappingDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function JanusMappingDialog({ open, onOpenChange }: JanusMappingDialogProps) {
  const { t } = useTranslation();
  const project = useKumaProject();

  const storeIsExporting = useMameAppStore((s) => s.isExporting);
  const [format, setFormat] = useState<JanusExportFormat>("csv");
  const [destLayout, setDestLayout] = useState<JanusDestLayout>("source");
  const [outputPath, setOutputPath] = useState<string>("");
  const [isExporting, setIsExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const [lastExportPath, setLastExportPath] = useState<string | null>(null);

  const [preview, setPreview] = useState<JanusPreviewResult | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewFailure, setPreviewFailure] = useState<string | null>(null);
  // Monotonic request id: a fast layout toggle can resolve out of order, and a
  // stale response would show the other layout dest wells.
  const previewSeq = useRef(0);

  const loadPreview = useCallback(async (layout: JanusDestLayout) => {
    const seq = ++previewSeq.current;
    setPreviewLoading(true);
    setPreviewFailure(null);
    try {
      const result = await fetchMameJanusPreview(layout);
      if (previewSeq.current !== seq) return;
      setPreview(result);
    } catch (err) {
      if (previewSeq.current !== seq) return;
      setPreview(null);
      setPreviewFailure(err instanceof Error ? err.message : String(err));
    } finally {
      if (previewSeq.current === seq) setPreviewLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!open) {
      // Drop stale rows so a reopen never flashes the previous run.
      previewSeq.current += 1;
      setPreview(null);
      setPreviewFailure(null);
      setPreviewLoading(false);
      return;
    }
    void loadPreview(destLayout);
  }, [open, destLayout, loadPreview]);

  const previewErrors = preview?.errors ?? [];
  const hasPreviewErrors = previewErrors.length > 0;

  function deriveDefaultPath(fmt: JanusExportFormat): string {
    if (!project) return "";
    return buildJanusDefaultPath(project.path, project.name, fmt);
  }

  function handleFormatChange(next: JanusExportFormat) {
    setFormat(next);
    // Update path extension when format toggles if path is still the auto-generated default.
    if (outputPath === "" || outputPath === deriveDefaultPath(format)) {
      setOutputPath(deriveDefaultPath(next));
    }
  }

  async function browseOutput() {
    const ext = format === "xlsx" ? "xlsx" : "csv";
    const selected = await save({
      filters: [{ name: ext.toUpperCase(), extensions: [ext] }],
      defaultPath: outputPath || deriveDefaultPath(format) || undefined,
    });
    if (selected) setOutputPath(selected);
  }

  async function doExport() {
    const target = outputPath || deriveDefaultPath(format);
    if (!target) {
      setExportError(t("mame.dialogs.janusMapping.exportErrorPathRequired"));
      return;
    }
    // §5 overwrite confirm (auto-derived 경로로 조용히 덮어쓰는 것을 막는다)
    if (await fileExists(target)) {
      const decision = await requestOverwriteConfirm(target);
      if (decision === "cancel") return;
    }
    setIsExporting(true);
    setExportError(null);
    try {
      const result = await handleExportMameJanusMapping(target, format, destLayout);
      setLastExportPath(result.output_path);
      setOutputPath(result.output_path);
    } catch (err) {
      setExportError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsExporting(false);
    }
  }

  const resolvedPath = outputPath || deriveDefaultPath(format);

  return (
    <Dialog open={open} onOpenChange={(next) => !isExporting && onOpenChange(next)}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{t("mame.dialogs.janusMapping.title")}</DialogTitle>
          <DialogDescription>
            {t("mame.dialogs.janusMapping.description")}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* Deck preview (PI hmk4 slide 5) */}
          <JanusDeckPreview />

          {/* Format selection */}
          <fieldset className="space-y-1.5">
            <legend className="text-xs font-medium text-muted-foreground">
              {t("mame.dialogs.janusMapping.formatLabel")}
            </legend>
            <div className="flex gap-4" role="radiogroup" aria-label={t("mame.dialogs.janusMapping.formatAriaLabel")}>
              {(["csv", "xlsx"] as const).map((fmt) => (
                <label
                  key={fmt}
                  className="flex cursor-pointer items-center gap-2 text-sm"
                >
                  <input
                    type="radio"
                    name="janus-format"
                    value={fmt}
                    checked={format === fmt}
                    onChange={() => handleFormatChange(fmt)}
                    className="accent-primary"
                    aria-label={fmt.toUpperCase()}
                  />
                  <span className="font-medium uppercase">{fmt}</span>
                </label>
              ))}
            </div>
          </fieldset>

          <fieldset className="space-y-1.5">
            <legend className="text-xs font-medium text-muted-foreground">
              {t("mame.dialogs.janusMapping.destLayoutLabel")}
            </legend>
            <div
              className="flex gap-4"
              role="radiogroup"
              aria-label={t("mame.dialogs.janusMapping.destLayoutAriaLabel")}
            >
              {(["source", "compact"] as const).map((layout) => (
                <label
                  key={layout}
                  className="flex cursor-pointer items-center gap-2 text-sm"
                >
                  <input
                    type="radio"
                    name="janus-dest-layout"
                    value={layout}
                    checked={destLayout === layout}
                    onChange={() => setDestLayout(layout)}
                    className="accent-primary"
                    aria-label={t(`mame.dialogs.janusMapping.destLayoutOption.${layout}`)}
                  />
                  <span className="font-medium">
                    {t(`mame.dialogs.janusMapping.destLayoutOption.${layout}`)}
                  </span>
                </label>
              ))}
            </div>
            <p className="text-xs text-muted-foreground leading-relaxed">
              {t(`mame.dialogs.janusMapping.destLayoutHint.${destLayout}`)}
            </p>
          </fieldset>

          {/* Row preview, what the export would write, before it writes it. */}
          <section className="space-y-1.5" aria-label={t("mame.dialogs.janusMapping.previewHeading")}>
            <div className="flex items-baseline justify-between gap-2">
              <h3 className="text-xs font-medium text-muted-foreground">
                {t("mame.dialogs.janusMapping.previewHeading")}
              </h3>
              {preview && (
                <span className="text-caption tabular-nums text-muted-foreground">
                  {t("mame.dialogs.janusMapping.previewCount", {
                    count: preview.row_count,
                  })}
                </span>
              )}
            </div>

            {/* Validation problems block the export; this is the point of the preview. */}
            {hasPreviewErrors && (
              <div
                className="space-y-1 rounded-control border border-error/40 bg-error/8 px-3 py-2"
                role="alert"
                aria-live="assertive"
              >
                <p className="text-caption font-medium text-error">
                  {t("mame.dialogs.janusMapping.previewBlocked")}
                </p>
                <ul className="space-y-1">
                  {previewErrors.map((e) => (
                    <li key={e.code} className="flex items-start gap-2">
                      <AlertCircle
                        size={13}
                        className="mt-0.5 flex-shrink-0 text-error"
                        aria-hidden="true"
                      />
                      <span className="text-caption text-error">{e.message}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {previewLoading && (
              <p className="text-caption text-muted-foreground" aria-live="polite">
                {t("mame.dialogs.janusMapping.previewLoading")}
              </p>
            )}

            {/* A dry-run failure is not a validation failure: it leaves Export
                enabled, since the export path has its own fail-fast guards. */}
            {previewFailure && !previewLoading && (
              <div className="flex items-start gap-2 rounded-control border border-warning/40 bg-warning/8 px-3 py-2">
                <AlertCircle
                  size={13}
                  className="mt-0.5 flex-shrink-0 text-warning"
                  aria-hidden="true"
                />
                <div className="space-y-1">
                  <p className="text-caption text-warning">
                    {t("mame.dialogs.janusMapping.previewFailed", {
                      message: previewFailure,
                    })}
                  </p>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="h-7 px-2 text-caption"
                    onClick={() => void loadPreview(destLayout)}
                  >
                    {t("mame.dialogs.janusMapping.previewRetry")}
                  </Button>
                </div>
              </div>
            )}

            {preview && !previewLoading && preview.rows.length === 0 && (
              <p className="text-caption text-muted-foreground">
                {t("mame.dialogs.janusMapping.previewEmpty")}
              </p>
            )}

            {preview && preview.rows.length > 0 && (
              <div className="max-h-56 overflow-y-auto rounded-control border border-border">
                {/* Column labels are the literal export header row, so they stay
                    untranslated to match the produced file byte-for-byte. */}
                <table className="w-full border-collapse text-caption">
                  <thead className="sticky top-0 bg-muted">
                    <tr className="text-left">
                      <th scope="col" className="px-2 py-1 font-medium">name</th>
                      <th scope="col" className="px-2 py-1 font-medium">source_plate</th>
                      <th scope="col" className="px-2 py-1 font-medium">source_well</th>
                      <th scope="col" className="px-2 py-1 font-medium">dest_well</th>
                      <th scope="col" className="px-2 py-1 text-right font-medium">
                        priority_score
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {preview.rows.map((row, idx) => (
                      <tr
                        key={`${row.name}-${row.source_plate}-${row.source_well}-${idx}`}
                        className="border-t border-border/60"
                      >
                        <td className="px-2 py-1 font-mono">{row.name}</td>
                        <td className="px-2 py-1 font-mono">{row.source_plate}</td>
                        <td className="px-2 py-1 font-mono">{row.source_well}</td>
                        <td className="px-2 py-1 font-mono">{row.dest_well}</td>
                        <td className="px-2 py-1 text-right font-mono tabular-nums">
                          {row.priority_score}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          {/* Output path */}
          <div className="space-y-1.5">
            <Label
              htmlFor="janus-output-path"
              className="text-xs font-medium text-muted-foreground"
            >
              {t("mame.dialogs.janusMapping.outputPathLabel")}
            </Label>
            <div className="flex gap-2">
              <Input
                id="janus-output-path"
                value={resolvedPath}
                onChange={(e) => setOutputPath(e.target.value)}
                placeholder={t("mame.dialogs.janusMapping.outputPathPlaceholder", { ext: format })}
                className="h-9 flex-1 min-w-0 text-sm font-mono"
                aria-label={t("mame.dialogs.janusMapping.outputPathAriaLabel")}
                disabled={isExporting}
              />
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => void browseOutput()}
                className="h-9 gap-1.5 px-3 flex-shrink-0"
                aria-label={t("mame.dialogs.janusMapping.browseAriaLabel")}
                disabled={isExporting}
              >
                <FolderOpen size={14} aria-hidden="true" />
              </Button>
            </div>
          </div>

          {/* Column info note */}
          <p className="text-xs text-muted-foreground leading-relaxed">
            {t("mame.dialogs.janusMapping.columnsNote")}
            <br />
            <span className="text-warning">
              {t("mame.dialogs.janusMapping.phase1Note")}
            </span>
          </p>

          {/* Error */}
          {exportError && (
            <div
              className="flex items-start gap-2 rounded-control border border-error/40 bg-error/8 px-3 py-2"
              role="alert"
              aria-live="assertive"
            >
              <AlertCircle size={14} className="mt-0.5 flex-shrink-0 text-error" aria-hidden="true" />
              <p className="text-caption text-error">{exportError}</p>
            </div>
          )}

          {/* Success */}
          {lastExportPath && !exportError && (
            <div className="rounded-control border border-success/40 bg-success/8 px-3 py-2">
              <div className="flex items-center gap-2">
                <CheckCircle2 size={13} className="text-success" aria-hidden="true" />
                <span className="text-caption font-medium text-success">
                  {t("mame.dialogs.janusMapping.exported")}
                </span>
              </div>
              <p className="mt-1 text-caption font-mono text-foreground break-all">
                {lastExportPath}
              </p>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            size="sm"
            onClick={() => onOpenChange(false)}
            disabled={isExporting}
          >
            {t("common.close")}
          </Button>
          <Button
            size="sm"
            onClick={() => void doExport()}
            disabled={
              isExporting || storeIsExporting || !resolvedPath || hasPreviewErrors
            }
            className="gap-2"
          >
            <Download size={14} aria-hidden="true" />
            {isExporting ? t("mame.dialogs.janusMapping.exporting") : t("mame.dialogs.janusMapping.exportJanus")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
