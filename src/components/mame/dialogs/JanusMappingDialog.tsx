/**
 * JanusMappingDialog — Export final cell-stock Janus mapping (K4 spec).
 *
 * Provides:
 *  - CSV / XLSX format selection (radio group)
 *  - Output schema selection (instrument-native 9 columns vs kuma 5 columns)
 *  - Destination layout selection (compact from A1 vs source position)
 *  - Instrument settings: volume, type, liquid class, and the four rack numbers
 *  - Row preview via the `export_janus_mapping_dry_run` RPC, refreshed when the
 *    dialog opens and whenever any setting changes
 *  - The clones left out of the pick, with the reason for each
 *  - Output path with Browse button
 *  - Export button that calls sidecar `export_janus_mapping` RPC, blocked while
 *    the preview reports a problem
 *  - Success / error feedback inline
 *
 * Preview and export send the same settings object, so what the operator
 * approves here is what the exported file describes. The object lives in the
 * mame store (persisted), because an analyze run writes its own mapping with
 * these very settings: keeping them local here would leave every run without a
 * liquid class and therefore without a file.
 *
 * Entered via: the "Janus instrument settings" button on step 2.1 (inputs, where
 * the values can be prepared before a run) and the "Open JANUS export" CTA on
 * step 3. The File menu item was removed in v0.14.7, so no text may point there.
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
import { DEFAULT_JANUS_SETTINGS } from "@/lib/mame/janusSettings";
import { fileExists, requestOverwriteConfirm } from "@/lib/overwriteConfirm";
import type {
  JanusDestLayout,
  JanusExclusionReason,
  JanusExportFormat,
  JanusExportSettings,
  JanusOutputSchema,
  JanusPreviewResult,
} from "@/types/mame/models";

/**
 * Source plates the deck map has to cover, named as the sidecar names them.
 *
 * Taken from the preview rows rather than a fixed list: the sidecar labels a
 * plate with `nb_label` (`sort_barcode07` -> `NB07`), so which labels exist is a
 * property of the run, and a fixed list left a native-barcode run's plates with
 * no rack number and the export refusing to write. The preview is produced by
 * the very function that validates the rack map, so the labels shown here are
 * the keys that get checked, and no label conversion is duplicated in TS
 * (`src/lib/mame/nbLabel.ts` holds the JS equivalent where one is needed).
 *
 * Before a run there are no plate names to show (they come from the barcodes of
 * that run), so the fallback is whatever the operator already stored, and the
 * shipped default only when even that is empty.
 */
function sourcePlatesFromPreview(
  preview: JanusPreviewResult | null,
  settings: JanusExportSettings,
): string[] {
  const fromRun = [
    ...new Set((preview?.rows ?? []).map((row) => row.source_plate).filter(Boolean)),
  ];
  if (fromRun.length > 0) return fromRun.sort();
  const stored = Object.keys(settings.sourceRacks);
  if (stored.length > 0) return stored.sort();
  return Object.keys(DEFAULT_JANUS_SETTINGS.sourceRacks).sort();
}

/** Preview refresh delay, so typing into a text field is one RPC, not one per key. */
const PREVIEW_DEBOUNCE_MS = 300;

function previewMatchesSettings(
  preview: JanusPreviewResult | null,
  settings: JanusExportSettings,
): boolean {
  if (!preview) return false;
  const resolved = preview.settings;
  return (
    resolved.dest_layout === settings.destLayout &&
    resolved.output_schema === settings.outputSchema &&
    resolved.include_fallback === settings.includeFallback &&
    resolved.volume === settings.volume &&
    resolved.sample_type === settings.sampleType &&
    resolved.liquid_class === settings.liquidClass &&
    resolved.dest_rack === settings.destRack &&
    JSON.stringify(resolved.include_verdicts) ===
      JSON.stringify(settings.includeVerdicts) &&
    JSON.stringify(resolved.source_racks) === JSON.stringify(settings.sourceRacks)
  );
}

function previewCellValue(
  row: JanusPreviewResult["rows"][number],
  rowIdx: number,
  idx: number,
  column: string,
  settings: JanusPreviewResult["settings"],
): string {
  if (settings.output_schema === "legacy5") {
    if (column === "priority_score") return String(row.priority_score);
    return String(row[column as keyof typeof row] ?? "");
  }
  switch (`${idx}:${column}`) {
    case "0:name":
      return row.name;
    case "1:type":
      return settings.sample_type;
    case "2:Dsp. Rack":
      return settings.liquid_class;
    case "3:no":
      return String(rowIdx + 1);
    case "4:Asp. Rack":
      return String(settings.source_racks[row.source_plate] ?? "");
    case "5:Asp. Posi":
      return row.source_well;
    case "6:Dsp. Rack":
      return String(settings.dest_rack);
    case "7:Dsp. Posi":
      return row.dest_well;
    case "8:volume":
      return String(settings.volume);
    default:
      return "";
  }
}

function parsePositiveIntegerInput(raw: string): number | null {
  if (!/^[1-9]\d*$/.test(raw)) return null;
  return Number.parseInt(raw, 10);
}

interface JanusMappingDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function JanusMappingDialog({ open, onOpenChange }: JanusMappingDialogProps) {
  const { t } = useTranslation();
  const project = useKumaProject();

  const storeIsExporting = useMameAppStore((s) => s.isExporting);
  const settings = useMameAppStore((s) => s.janusSettings);
  const setSettings = useMameAppStore((s) => s.setJanusSettings);
  const [format, setFormat] = useState<JanusExportFormat>("csv");
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

  const loadPreview = useCallback(async (next: JanusExportSettings) => {
    const seq = ++previewSeq.current;
    setPreviewLoading(true);
    setPreviewFailure(null);
    try {
      const result = await fetchMameJanusPreview(next);
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
    // Debounced: text fields would otherwise fire one request per keystroke.
    const timer = setTimeout(() => void loadPreview(settings), PREVIEW_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [open, settings, loadPreview]);

  const previewErrors = preview?.errors ?? [];
  const hasPreviewErrors = previewErrors.length > 0;
  const excluded = preview?.excluded ?? [];
  const isDevice9 = settings.outputSchema === "device9";
  const sourcePlates = sourcePlatesFromPreview(preview, settings);
  const platesComeFromRun = (preview?.rows.length ?? 0) > 0;
  const resolvedPath = outputPath || deriveDefaultPath(format);
  const isPreviewCurrent = previewMatchesSettings(preview, settings);
  const previewColumns =
    preview?.settings.columns && preview.settings.columns.length > 0
      ? preview.settings.columns
      : ["name", "source_plate", "source_well", "dest_well", "priority_score"];
  const canExport =
    Boolean(resolvedPath) &&
    !isExporting &&
    !storeIsExporting &&
    !hasPreviewErrors &&
    isPreviewCurrent &&
    !previewLoading;

  /** Excluded clones grouped by reason, so a retry plan reads at a glance. */
  const excludedByReason = excluded.reduce<Partial<Record<JanusExclusionReason, string[]>>>(
    (acc, entry) => {
      (acc[entry.reason] ??= []).push(entry.mutant_id);
      return acc;
    },
    {},
  );

  function patchSettings(partial: Partial<JanusExportSettings>) {
    setSettings({ ...settings, ...partial });
  }

  function patchSourceRack(plate: string, raw: string) {
    const parsed = parsePositiveIntegerInput(raw);
    if (parsed === null) return;
    setSettings({
      ...settings,
      sourceRacks: { ...settings.sourceRacks, [plate]: parsed },
    });
  }

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
      const result = await handleExportMameJanusMapping(target, format, settings);
      setLastExportPath(result.output_path);
      setOutputPath(result.output_path);
    } catch (err) {
      setExportError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsExporting(false);
    }
  }

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
              {(["compact", "source"] as const).map((layout: JanusDestLayout) => (
                <label
                  key={layout}
                  className="flex cursor-pointer items-center gap-2 text-sm"
                >
                  <input
                    type="radio"
                    name="janus-dest-layout"
                    value={layout}
                    checked={settings.destLayout === layout}
                    onChange={() => patchSettings({ destLayout: layout })}
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
              {t(`mame.dialogs.janusMapping.destLayoutHint.${settings.destLayout}`)}
            </p>
          </fieldset>

          <fieldset className="space-y-1.5">
            <legend className="text-xs font-medium text-muted-foreground">
              {t("mame.dialogs.janusMapping.schemaLabel")}
            </legend>
            <div
              className="flex gap-4"
              role="radiogroup"
              aria-label={t("mame.dialogs.janusMapping.schemaAriaLabel")}
            >
              {(["device9", "legacy5"] as const).map((schema: JanusOutputSchema) => (
                <label
                  key={schema}
                  className="flex cursor-pointer items-center gap-2 text-sm"
                >
                  <input
                    type="radio"
                    name="janus-output-schema"
                    value={schema}
                    checked={settings.outputSchema === schema}
                    onChange={() => patchSettings({ outputSchema: schema })}
                    className="accent-primary"
                    aria-label={t(`mame.dialogs.janusMapping.schemaOption.${schema}`)}
                  />
                  <span className="font-medium">
                    {t(`mame.dialogs.janusMapping.schemaOption.${schema}`)}
                  </span>
                </label>
              ))}
            </div>
            <p className="text-xs text-muted-foreground leading-relaxed">
              {t(`mame.dialogs.janusMapping.schemaHint.${settings.outputSchema}`)}
            </p>
          </fieldset>

          {isDevice9 && (
            <fieldset className="space-y-2 rounded-control border border-border px-3 py-2.5">
              <legend className="px-1 text-xs font-medium text-muted-foreground">
                {t("mame.dialogs.janusMapping.instrumentHeading")}
              </legend>

              <div className="flex gap-2">
                <div className="flex-1 min-w-0 space-y-1">
                  <Label
                    htmlFor="janus-volume"
                    className="text-xs font-medium text-muted-foreground"
                  >
                    {t("mame.dialogs.janusMapping.volumeLabel")}
                  </Label>
                  <Input
                    id="janus-volume"
                    type="number"
                    min={0}
                    step="any"
                    value={settings.volume}
                    onChange={(e) => {
                      const parsed = Number.parseFloat(e.target.value);
                      if (!Number.isNaN(parsed)) patchSettings({ volume: parsed });
                    }}
                    className="h-9 w-full text-sm"
                    disabled={isExporting}
                  />
                </div>
                <div className="flex-1 min-w-0 space-y-1">
                  <Label
                    htmlFor="janus-liquid-class"
                    className="text-xs font-medium text-muted-foreground"
                  >
                    {t("mame.dialogs.janusMapping.liquidClassLabel")}
                  </Label>
                  <Input
                    id="janus-liquid-class"
                    value={settings.liquidClass}
                    onChange={(e) => patchSettings({ liquidClass: e.target.value })}
                    placeholder={t("mame.dialogs.janusMapping.liquidClassPlaceholder")}
                    className="h-9 w-full min-w-0 text-sm"
                    aria-required="true"
                    disabled={isExporting}
                  />
                </div>
              </div>
              <p className="text-xs text-muted-foreground leading-relaxed">
                {t("mame.dialogs.janusMapping.liquidClassHint")}
              </p>

              <details className="group">
                <summary className="cursor-pointer text-xs font-medium text-muted-foreground">
                  {t("mame.dialogs.janusMapping.deckHeading")}
                </summary>
                <div className="mt-2 space-y-2">
                  <div className="space-y-1">
                    <Label
                      htmlFor="janus-sample-type"
                      className="text-xs font-medium text-muted-foreground"
                    >
                      {t("mame.dialogs.janusMapping.sampleTypeLabel")}
                    </Label>
                    <Input
                      id="janus-sample-type"
                      value={settings.sampleType}
                      onChange={(e) => patchSettings({ sampleType: e.target.value })}
                      className="h-9 w-full min-w-0 text-sm"
                      disabled={isExporting}
                    />
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {sourcePlates.map((plate) => (
                      <div key={plate} className="flex-1 min-w-0 space-y-1">
                        <Label
                          htmlFor={`janus-rack-${plate}`}
                          className="text-xs font-medium text-muted-foreground"
                        >
                          {t("mame.dialogs.janusMapping.sourceRackLabel", { plate })}
                        </Label>
                        <Input
                          id={`janus-rack-${plate}`}
                          type="number"
                          min={1}
                          step={1}
                          value={settings.sourceRacks[plate] ?? ""}
                          onChange={(e) => patchSourceRack(plate, e.target.value)}
                          className="h-9 w-full text-sm"
                          disabled={isExporting}
                        />
                      </div>
                    ))}
                    <div className="flex-1 min-w-0 space-y-1">
                      <Label
                        htmlFor="janus-dest-rack"
                        className="text-xs font-medium text-muted-foreground"
                      >
                        {t("mame.dialogs.janusMapping.destRackLabel")}
                      </Label>
                      <Input
                        id="janus-dest-rack"
                        type="number"
                        min={1}
                        step={1}
	                        value={settings.destRack}
	                        onChange={(e) => {
	                          const parsed = parsePositiveIntegerInput(e.target.value);
	                          if (parsed !== null) patchSettings({ destRack: parsed });
	                        }}
                        className="h-9 w-full text-sm"
                        disabled={isExporting}
                      />
                    </div>
                  </div>
                  <p className="text-xs text-muted-foreground leading-relaxed">
                    {t("mame.dialogs.janusMapping.rackHint")}
                  </p>
                  {/* The plate names are the run's own; before a run there are
                      none, so say that instead of implying the list is final. */}
                  {!platesComeFromRun && (
                    <p className="text-xs text-muted-foreground leading-relaxed">
                      {t("mame.dialogs.janusMapping.rackPlatesPending")}
                    </p>
                  )}
                </div>
              </details>
            </fieldset>
          )}

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
                    onClick={() => void loadPreview(settings)}
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
	                      {previewColumns.map((column, idx) => (
	                        <th
	                          key={`${column}-${idx}`}
	                          scope="col"
	                          className="px-2 py-1 font-medium"
	                        >
	                          {column}
	                        </th>
	                      ))}
	                    </tr>
                  </thead>
                  <tbody>
                    {preview.rows.map((row, idx) => (
                      <tr
                        key={`${row.name}-${row.source_plate}-${row.source_well}-${idx}`}
                        className="border-t border-border/60"
                      >
                        {previewColumns.map((column, columnIdx) => (
                          <td
                            key={`${column}-${columnIdx}`}
                            className="px-2 py-1 font-mono tabular-nums"
                          >
                            {previewCellValue(row, idx, columnIdx, column, preview.settings)}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {preview && !previewLoading && (
              <div className="space-y-1">
                <p className="text-caption font-medium text-muted-foreground">
                  {t("mame.dialogs.janusMapping.excludedHeading", {
                    count: preview.excluded_count,
                  })}
                </p>
                {preview.excluded_count === 0 ? (
                  <p className="text-caption text-muted-foreground">
                    {t("mame.dialogs.janusMapping.excludedNone")}
                  </p>
                ) : (
                  <ul className="space-y-0.5">
                    {(
                      Object.entries(excludedByReason) as [JanusExclusionReason, string[]][]
                    ).map(([reason, ids]) => (
                      <li key={reason} className="text-caption text-muted-foreground">
                        <span className="font-medium">
                          {t(`mame.dialogs.janusMapping.excludedReason.${reason}`)}
                        </span>
                        <span className="tabular-nums"> ({ids.length}): </span>
                        <span className="font-mono break-all">{ids.join(", ")}</span>
                      </li>
                    ))}
                  </ul>
                )}
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
            {t(`mame.dialogs.janusMapping.columnsNote.${settings.outputSchema}`)}
            <br />
            <span className="text-warning">
              {t("mame.dialogs.janusMapping.selectionNote")}
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
            disabled={!canExport}
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
