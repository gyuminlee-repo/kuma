/**
 * BuildEvolveproInputPanel: MAME activity to EVOLVEpro input build panel.
 *
 * Two backend input modes are exposed through a source-mode toggle:
 *   rank   , plate layout + GC data (+ optional Agilent rep-batch and previous
 *             EVOLVEpro confirmation pair).
 *   reports, variant-labeled Agilent re-measure report plus exactly one
 *             round-1 source (previous EVOLVEpro file, or a raw Agilent
 *             round-1 report which also needs the plate layout), with an
 *             optional NGS verdict file for gating.
 *
 * The chosen files plus an output path go to the
 * mame.activity.build_evolvepro_input RPC, which writes a merged EVOLVEpro
 * input xlsx (plus an ID-to-variant mapping audit in rank mode). The pre-run
 * result area renders an empty state, never an error boundary.
 *
 * Follows the Kuro-style Browse button + selected-filename preview pattern. The
 * output control uses a save-file dialog. State is local useState, persisted to
 * localStorage `kuma:mame:buildEvolvepro`.
 */

import { useState, useCallback, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { open, save } from "@tauri-apps/plugin-dialog";
import { FolderOpen, Loader2, AlertTriangle } from "lucide-react";
import { toast } from "sonner";
import { buildEvolveproInput } from "@/lib/ipc-mame";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import { describeRpcError, extractMissingMethod } from "@/lib/errors";
import { revealInOSFolder } from "@/lib/openFolder";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type {
  BuildEvolveproInputParams,
  BuildEvolveproInputResult,
} from "@/types/mame/build_evolvepro_input";
import {
  type BuildEvolveproFormState as FormState,
  loadBuildEvolveproFromStorage as loadFromStorage,
  saveBuildEvolveproToStorage as saveToStorage,
  BUILD_EVOLVEPRO_DEFAULT_STATE,
} from "@/lib/mame/buildEvolveproFormStorage";

function getFilename(p: string): string {
  if (!p) return "";
  const parts = p.split(/[/\\]/);
  return parts[parts.length - 1] ?? p;
}

function toSinglePath(result: string | string[] | null): string | null {
  return typeof result === "string" ? result : null;
}

export function BuildEvolveproInputPanel() {
  const { t } = useTranslation();
  const [form, setFormRaw] = useState<FormState>(() => loadFromStorage());
  const [isBuilding, setIsBuilding] = useState(false);
  const [result, setResult] = useState<BuildEvolveproInputResult | null>(null);
  const resetEpoch = useMameAppStore((s) => s.resetEpoch);

  function setForm(partial: Partial<FormState>) {
    setFormRaw((prev) => {
      const next = { ...prev, ...partial };
      saveToStorage(next);
      return next;
    });
  }

  // Clear the previous result when any input changes so the summary never lags.
  useEffect(() => {
    setResult(null);
  }, [
    form.sourceMode,
    form.round1Source,
    form.layoutXlsx,
    form.gcDataXlsx,
    form.repBatchXlsx,
    form.prevEvolveproXlsx,
    form.round1ReportXlsx,
    form.round1EvolveproXlsx,
    form.remeasureReportXlsx,
    form.verdictXlsx,
    form.outputXlsx,
    form.gcExportXlsx,
  ]);

  useEffect(() => {
    if (resetEpoch === 0) return;
    setFormRaw(BUILD_EVOLVEPRO_DEFAULT_STATE);
    setResult(null);
  }, [resetEpoch]);

  const browseXlsx = useCallback(
    async (key: keyof FormState, title: string) => {
      const selected = toSinglePath(
        await open({
          directory: false,
          filters: [{ name: "Excel", extensions: ["xlsx"] }],
          title,
        }),
      );
      if (selected) setForm({ [key]: selected } as Partial<FormState>);
    },
    [],
  );

  const browseOutput = useCallback(async () => {
    const selected = await save({
      filters: [{ name: "Excel", extensions: ["xlsx"] }],
      title: t("mame.buildEvolvepro.chooseOutput"),
    });
    if (selected) setForm({ outputXlsx: selected });
  }, [t]);

  // Optional review artifact, so it uses a save-file dialog like the output
  // control (never an open dialog: the file does not exist yet).
  const browseGcExport = useCallback(async () => {
    const selected = await save({
      filters: [{ name: "Excel", extensions: ["xlsx"] }],
      title: t("mame.buildEvolvepro.gcExportXlsx"),
    });
    if (selected) setForm({ gcExportXlsx: selected });
  }, [t]);

  // Client-side gate mirroring the backend _mode_xor validator, so a build is
  // never dispatched only to come back as a ValueError. Each entry is a label
  // of a still-missing required file for the currently selected mode.
  const missing: string[] = [];
  if (form.sourceMode === "rank") {
    // Confirmation files (rep-batch + previous EVOLVEpro) stay optional: layout
    // + GC alone yields a provisional first-round primary screen.
    if (!form.layoutXlsx) missing.push(t("mame.buildEvolvepro.layoutXlsx"));
    if (!form.gcDataXlsx) missing.push(t("mame.buildEvolvepro.gcDataXlsx"));
  } else if (form.round1Source === "prev") {
    if (!form.round1EvolveproXlsx)
      missing.push(t("mame.buildEvolvepro.round1EvolveproXlsx"));
  } else {
    if (!form.layoutXlsx) missing.push(t("mame.buildEvolvepro.layoutXlsx"));
    if (!form.round1ReportXlsx)
      missing.push(t("mame.buildEvolvepro.round1ReportXlsx"));
  }
  if (form.sourceMode === "reports" && !form.remeasureReportXlsx)
    missing.push(t("mame.buildEvolvepro.remeasureReportXlsx"));
  if (!form.outputXlsx) missing.push(t("mame.buildEvolvepro.outputXlsx"));

  const canBuild = missing.length === 0 && !isBuilding;

  function buildParams(): BuildEvolveproInputParams {
    if (form.sourceMode === "rank") {
      return {
        layout_xlsx: form.layoutXlsx,
        gc_data_xlsx: form.gcDataXlsx,
        rep_batch_xlsx: form.repBatchXlsx || undefined,
        prev_evolvepro_xlsx: form.prevEvolveproXlsx || undefined,
        output_xlsx: form.outputXlsx,
      };
    }
    // Reports mode sends exactly one round-1 source. With a previous EVOLVEpro
    // baseline the layout is optional and only maps variant to well for NGS
    // verdict gating; with a raw round-1 report the layout is required.
    if (form.round1Source === "prev") {
      return {
        round1_evolvepro_xlsx: form.round1EvolveproXlsx,
        layout_xlsx: form.layoutXlsx || undefined,
        remeasure_report_xlsx: form.remeasureReportXlsx,
        verdict_xlsx: form.verdictXlsx || undefined,
        output_xlsx: form.outputXlsx,
      };
    }
    return {
      layout_xlsx: form.layoutXlsx,
      round1_report_xlsx: form.round1ReportXlsx,
      remeasure_report_xlsx: form.remeasureReportXlsx,
      verdict_xlsx: form.verdictXlsx || undefined,
      output_xlsx: form.outputXlsx,
      gc_export_xlsx: form.gcExportXlsx || undefined,
    };
  }

  async function handleBuild() {
    if (!canBuild) return;
    setIsBuilding(true);
    setResult(null);

    const params = buildParams();

    try {
      const res = await buildEvolveproInput(params);
      setResult(res);
      toast.success(t("mame.buildEvolvepro.toastSuccess"), {
        description: t("mame.buildEvolvepro.toastSuccessDesc", {
          count: res.n_variants,
        }),
        duration: 4000,
      });
    } catch (err) {
      const descRaw = describeRpcError(err, "mame");
      const description = descRaw.startsWith("errors.")
        ? t(descRaw, {
            method:
              extractMissingMethod(err) ||
              "mame.activity.build_evolvepro_input",
          })
        : descRaw;
      toast.error(t("mame.buildEvolvepro.toastError"), {
        description,
        duration: 6000,
      });
    } finally {
      setIsBuilding(false);
    }
  }

  return (
    <section className="space-y-6">
      <header>
        <h3 className="text-base font-semibold text-foreground">
          {t("mame.buildEvolvepro.title")}
        </h3>
        <p className="mt-1 text-xs text-muted-foreground">
          {t("mame.buildEvolvepro.subtitle")}
        </p>
        <p className="mt-2 rounded-md border border-border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
          {t("mame.buildEvolvepro.routeNote")}
        </p>
      </header>

      <section aria-labelledby="bep-input-files">
        <h3
          id="bep-input-files"
          className="mb-3 text-sm font-medium text-foreground"
        >
          {t("mame.buildEvolvepro.inputFiles")}
        </h3>
        <div className="space-y-4">
          {/* Source-mode toggle: pre-normalised GC data (rank) vs raw Agilent
              reports. The two modes are mutually exclusive backend-side. */}
          <ChoiceToggle
            label={t("mame.buildEvolvepro.sourceModeLabel")}
            helperText={
              form.sourceMode === "rank"
                ? t("mame.buildEvolvepro.sourceModeRankHelper")
                : t("mame.buildEvolvepro.sourceModeReportsHelper")
            }
            options={[
              { value: "rank", label: t("mame.buildEvolvepro.sourceModeRank") },
              {
                value: "reports",
                label: t("mame.buildEvolvepro.sourceModeReports"),
              },
            ]}
            selected={form.sourceMode}
            onSelect={(v) =>
              setForm({ sourceMode: v as FormState["sourceMode"] })
            }
          />

          {form.sourceMode === "rank" ? (
            <>
              <FilePickerField
                id="bep-layout"
                label={t("mame.buildEvolvepro.layoutXlsx")}
                filled={Boolean(form.layoutXlsx)}
                value={form.layoutXlsx}
                onBrowse={() =>
                  browseXlsx("layoutXlsx", t("mame.buildEvolvepro.layoutXlsx"))
                }
                helperText={t("mame.buildEvolvepro.layoutXlsxHelper")}
              />
              <FilePickerField
                id="bep-gc"
                label={t("mame.buildEvolvepro.gcDataXlsx")}
                filled={Boolean(form.gcDataXlsx)}
                value={form.gcDataXlsx}
                onBrowse={() =>
                  browseXlsx("gcDataXlsx", t("mame.buildEvolvepro.gcDataXlsx"))
                }
                helperText={t("mame.buildEvolvepro.gcDataXlsxHelper")}
              />
              <FilePickerField
                id="bep-rep"
                label={`${t("mame.buildEvolvepro.repBatchXlsx")} (${t("mame.buildEvolvepro.optionalLabel")})`}
                filled={Boolean(form.repBatchXlsx)}
                value={form.repBatchXlsx}
                optional
                onBrowse={() =>
                  browseXlsx(
                    "repBatchXlsx",
                    t("mame.buildEvolvepro.repBatchXlsx"),
                  )
                }
                helperText={t("mame.buildEvolvepro.repBatchXlsxHelper")}
              />
              <FilePickerField
                id="bep-prev"
                label={`${t("mame.buildEvolvepro.prevEvolveproXlsx")} (${t("mame.buildEvolvepro.optionalLabel")})`}
                filled={Boolean(form.prevEvolveproXlsx)}
                value={form.prevEvolveproXlsx}
                optional
                onBrowse={() =>
                  browseXlsx(
                    "prevEvolveproXlsx",
                    t("mame.buildEvolvepro.prevEvolveproXlsx"),
                  )
                }
                helperText={t("mame.buildEvolvepro.prevEvolveproXlsxHelper")}
              />
            </>
          ) : (
            <>
              {/* Round-1 baseline source: prior EVOLVEpro file vs raw report. */}
              <ChoiceToggle
                label={t("mame.buildEvolvepro.round1SourceLabel")}
                helperText={
                  form.round1Source === "prev"
                    ? t("mame.buildEvolvepro.round1SourcePrevHelper")
                    : t("mame.buildEvolvepro.round1SourceRawHelper")
                }
                options={[
                  {
                    value: "prev",
                    label: t("mame.buildEvolvepro.round1SourcePrev"),
                  },
                  {
                    value: "raw",
                    label: t("mame.buildEvolvepro.round1SourceRaw"),
                  },
                ]}
                selected={form.round1Source}
                onSelect={(v) =>
                  setForm({ round1Source: v as FormState["round1Source"] })
                }
              />

              {form.round1Source === "prev" ? (
                <>
                  <FilePickerField
                    id="bep-round1-evolvepro"
                    label={t("mame.buildEvolvepro.round1EvolveproXlsx")}
                    filled={Boolean(form.round1EvolveproXlsx)}
                    value={form.round1EvolveproXlsx}
                    onBrowse={() =>
                      browseXlsx(
                        "round1EvolveproXlsx",
                        t("mame.buildEvolvepro.round1EvolveproXlsx"),
                      )
                    }
                    helperText={t(
                      "mame.buildEvolvepro.round1EvolveproXlsxHelper",
                    )}
                  />
                  <FilePickerField
                    id="bep-layout-optional"
                    label={`${t("mame.buildEvolvepro.layoutXlsx")} (${t("mame.buildEvolvepro.optionalLabel")})`}
                    filled={Boolean(form.layoutXlsx)}
                    value={form.layoutXlsx}
                    optional
                    onBrowse={() =>
                      browseXlsx(
                        "layoutXlsx",
                        t("mame.buildEvolvepro.layoutXlsx"),
                      )
                    }
                    helperText={t(
                      "mame.buildEvolvepro.layoutXlsxOptionalHelper",
                    )}
                  />
                </>
              ) : (
                <>
                  <FilePickerField
                    id="bep-layout"
                    label={t("mame.buildEvolvepro.layoutXlsx")}
                    filled={Boolean(form.layoutXlsx)}
                    value={form.layoutXlsx}
                    onBrowse={() =>
                      browseXlsx(
                        "layoutXlsx",
                        t("mame.buildEvolvepro.layoutXlsx"),
                      )
                    }
                    helperText={t("mame.buildEvolvepro.layoutXlsxHelper")}
                  />
                  <FilePickerField
                    id="bep-round1"
                    label={t("mame.buildEvolvepro.round1ReportXlsx")}
                    filled={Boolean(form.round1ReportXlsx)}
                    value={form.round1ReportXlsx}
                    onBrowse={() =>
                      browseXlsx(
                        "round1ReportXlsx",
                        t("mame.buildEvolvepro.round1ReportXlsx"),
                      )
                    }
                    helperText={t("mame.buildEvolvepro.round1ReportXlsxHelper")}
                  />
                  <FilePickerField
                    id="bep-gc-export"
                    label={`${t("mame.buildEvolvepro.gcExportXlsx")} (${t("mame.buildEvolvepro.optionalLabel")})`}
                    filled={Boolean(form.gcExportXlsx)}
                    value={form.gcExportXlsx}
                    optional
                    onBrowse={() => browseGcExport()}
                    helperText={t("mame.buildEvolvepro.gcExportXlsxHelper")}
                  />
                </>
              )}

              <FilePickerField
                id="bep-remeasure"
                label={t("mame.buildEvolvepro.remeasureReportXlsx")}
                filled={Boolean(form.remeasureReportXlsx)}
                value={form.remeasureReportXlsx}
                onBrowse={() =>
                  browseXlsx(
                    "remeasureReportXlsx",
                    t("mame.buildEvolvepro.remeasureReportXlsx"),
                  )
                }
                helperText={t("mame.buildEvolvepro.remeasureReportXlsxHelper")}
              />
              <FilePickerField
                id="bep-verdict"
                label={`${t("mame.buildEvolvepro.verdictXlsx")} (${t("mame.buildEvolvepro.optionalLabel")})`}
                filled={Boolean(form.verdictXlsx)}
                value={form.verdictXlsx}
                optional
                onBrowse={() =>
                  browseXlsx("verdictXlsx", t("mame.buildEvolvepro.verdictXlsx"))
                }
                helperText={t("mame.buildEvolvepro.verdictXlsxHelper")}
              />
            </>
          )}
        </div>
      </section>

      <section aria-labelledby="bep-output">
        <h3
          id="bep-output"
          className="mb-3 text-sm font-medium text-foreground"
        >
          {t("mame.buildEvolvepro.outputXlsx")}
        </h3>
        <div className="space-y-1.5">
          <div className="flex items-center justify-between gap-3">
            <Label
              htmlFor="bep-output-path"
              className="text-xs font-medium uppercase tracking-wide text-muted-foreground"
            >
              {t("mame.buildEvolvepro.outputXlsx")}
            </Label>
            <span
              className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                form.outputXlsx
                  ? "bg-primary/10 text-primary"
                  : "bg-muted text-muted-foreground"
              }`}
            >
              {form.outputXlsx
                ? t("mame.inputPanel.fileReady")
                : t("mame.buildEvolvepro.requiredStateLabel")}
            </span>
          </div>
          <div className="flex gap-1.5">
            <Input
              id="bep-output-path"
              value={getFilename(form.outputXlsx)}
              readOnly
              placeholder={t("mame.buildEvolvepro.noOutputSelected")}
              className="h-8 flex-1 min-w-0 text-xs font-mono"
              aria-label={t("mame.buildEvolvepro.outputXlsx")}
              title={form.outputXlsx || undefined}
            />
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => void browseOutput()}
              className="h-8 gap-1 px-2"
            >
              <FolderOpen size={12} aria-hidden="true" />
            </Button>
          </div>
          <p className="text-xs text-muted-foreground/90">
            {t("mame.buildEvolvepro.outputXlsxHelper")}
          </p>
        </div>
      </section>

      {missing.length > 0 && (
        <p
          role="status"
          className="rounded-md border border-border bg-muted/30 px-3 py-2 text-xs text-muted-foreground"
        >
          {t("mame.buildEvolvepro.missingInputs")}: {missing.join(", ")}
        </p>
      )}

      <Button
        type="button"
        className="w-full"
        disabled={!canBuild}
        onClick={() => void handleBuild()}
        aria-busy={isBuilding}
      >
        {isBuilding ? (
          <>
            <Loader2 size={14} className="mr-2 animate-spin" aria-hidden="true" />
            {t("mame.buildEvolvepro.building")}
          </>
        ) : (
          t("mame.buildEvolvepro.build")
        )}
      </Button>

      {/* Pre-run empty state, NOT an error boundary. */}
      {result === null ? (
        <p
          role="status"
          className="rounded-md border border-dashed border-border bg-muted/20 px-3 py-6 text-center text-xs text-muted-foreground"
        >
          {t("mame.buildEvolvepro.emptyState")}
        </p>
      ) : (
        <BuildResult result={result} />
      )}
    </section>
  );
}

function BuildResult({ result }: { result: BuildEvolveproInputResult }) {
  const { t } = useTranslation();
  return (
    <section aria-labelledby="bep-result" aria-live="polite" className="space-y-3">
      <h3 id="bep-result" className="text-sm font-medium text-foreground">
        {t("mame.buildEvolvepro.resultTitle")}
      </h3>

      {/* Confidence is a rank-mode concept; the backend omits it in reports
          mode, where a "provisional" badge would be a false statement. */}
      {result.confidence && (
        <div
          role="status"
          className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${
            result.confidence === "confirmed"
              ? "bg-primary/10 text-primary"
              : "bg-amber-500/15 text-amber-700 dark:text-amber-400"
          }`}
        >
          {result.confidence === "confirmed"
            ? t("mame.buildEvolvepro.confirmedLabel")
            : t("mame.buildEvolvepro.provisionalLabel")}
        </div>
      )}

      <div className="grid grid-cols-3 gap-2">
        <Stat label={t("mame.buildEvolvepro.nVariants")} value={result.n_variants} />
        <Stat
          label={t("mame.buildEvolvepro.nAuthoritative")}
          value={result.n_authoritative}
        />
        <Stat
          label={t("mame.buildEvolvepro.nFallbackOnly")}
          value={result.n_fallback_only}
        />
      </div>

      {result.n_ngs_excluded > 0 && (
        <div className="rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-400">
          <span className="font-semibold">
            {t("mame.buildEvolvepro.nNgsExcluded")}: {result.n_ngs_excluded}
          </span>{" "}
          <span className="font-mono">{result.ngs_excluded.join(", ")}</span>
        </div>
      )}

      {/* The rank assumption veto signal only exists in rank mode. */}
      {result.mode === "rank" && !result.prev_descending && (
        <div
          role="status"
          className="flex items-start gap-2 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-400"
        >
          <AlertTriangle size={14} className="mt-0.5 shrink-0" aria-hidden="true" />
          <span>{t("mame.buildEvolvepro.prevDescendingWarn")}</span>
        </div>
      )}

      {result.warnings.length > 0 && (
        <div className="rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 space-y-1">
          <p className="text-xs font-semibold text-amber-700 dark:text-amber-400">
            {t("mame.buildEvolvepro.warningsLabel")}
          </p>
          {result.warnings.map((w, i) => (
            <p key={i} className="text-xs text-amber-700 dark:text-amber-400">
              {w}
            </p>
          ))}
        </div>
      )}

      {result.swap_warnings.length > 0 && (
        <div className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 space-y-1">
          <p className="text-xs font-semibold text-destructive">
            {t("mame.buildEvolvepro.swapWarningsLabel")}
          </p>
          {result.swap_warnings.map((w, i) => (
            <p key={i} className="text-xs text-destructive">
              {w.message}
            </p>
          ))}
        </div>
      )}

      {result.mismatched.length > 0 && (
        <div className="rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 space-y-1">
          <p className="text-xs font-semibold text-amber-700 dark:text-amber-400">
            {t("mame.buildEvolvepro.mismatchedLabel")}
          </p>
          <p className="text-xs text-amber-700 dark:text-amber-400">
            {t("mame.buildEvolvepro.mismatchedHint")}
          </p>
          <div className="max-h-40 overflow-y-auto rounded-md border border-amber-500/30">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-amber-500/10">
                <tr>
                  <th className="px-2 py-1 text-left font-medium text-amber-700 dark:text-amber-400">
                    {t("mame.buildEvolvepro.colVariant")}
                  </th>
                  <th className="px-2 py-1 text-right font-medium text-amber-700 dark:text-amber-400">
                    {t("mame.buildEvolvepro.mismatchedAuthoritative")}
                  </th>
                  <th className="px-2 py-1 text-right font-medium text-amber-700 dark:text-amber-400">
                    {t("mame.buildEvolvepro.mismatchedFallback")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {result.mismatched.map((m) => (
                  <tr key={m.variant} className="border-t border-amber-500/20">
                    <td className="px-2 py-1 font-mono text-amber-700 dark:text-amber-400">
                      {m.variant}
                    </td>
                    <td className="px-2 py-1 text-right font-mono text-amber-700 dark:text-amber-400">
                      {m.authoritative.toFixed(3)}
                    </td>
                    <td className="px-2 py-1 text-right font-mono text-amber-700 dark:text-amber-400">
                      {m.fallback.toFixed(3)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div>
        <h4 className="mb-2 text-xs font-semibold text-foreground">
          {t("mame.buildEvolvepro.mappingAuditTitle")}
        </h4>
        <div className="max-h-56 overflow-y-auto rounded-md border border-border">
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-muted/60">
              <tr>
                <th className="px-2 py-1 text-left font-medium text-muted-foreground">
                  {t("mame.buildEvolvepro.colId")}
                </th>
                <th className="px-2 py-1 text-left font-medium text-muted-foreground">
                  {t("mame.buildEvolvepro.colVariant")}
                </th>
                <th className="px-2 py-1 text-left font-medium text-muted-foreground">
                  {t("mame.buildEvolvepro.colWell")}
                </th>
              </tr>
            </thead>
            <tbody>
              {result.mapping_audit.map((row) => (
                <tr key={row.id} className="border-t border-border/60">
                  <td className="px-2 py-1 font-mono">{row.id}</td>
                  <td className="px-2 py-1 font-mono">{row.variant}</td>
                  <td className="px-2 py-1 font-mono text-muted-foreground">
                    {row.well ?? ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {/* Reports mode writes no JSON audit artifact and returns an empty path. */}
        {result.mapping_audit_path && (
          <p
            className="mt-1 truncate text-xs text-muted-foreground"
            title={result.mapping_audit_path}
          >
            {t("mame.buildEvolvepro.mappingAuditPath")}:{" "}
            {getFilename(result.mapping_audit_path)}
          </p>
        )}
      </div>

      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() =>
          void revealInOSFolder(result.output_path).catch((e) =>
            toast.error(String(e)),
          )
        }
      >
        <FolderOpen size={12} className="mr-1.5" aria-hidden="true" />
        {t("mame.buildEvolvepro.openFolder")}
      </Button>
    </section>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md border border-border bg-muted/30 px-2 py-2 text-center">
      <p className="text-lg font-semibold text-foreground">{value}</p>
      <p className="text-xs text-muted-foreground">{label}</p>
    </div>
  );
}

/** Exclusive choice rendered as a radiogroup of two-plus buttons. */
function ChoiceToggle({
  label,
  options,
  selected,
  onSelect,
  helperText,
}: {
  label: string;
  options: { value: string; label: string }[];
  selected: string;
  onSelect: (value: string) => void;
  helperText?: string;
}) {
  return (
    <div className="space-y-1.5">
      <Label className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </Label>
      <div className="flex gap-1.5" role="radiogroup" aria-label={label}>
        {options.map((o) => (
          <Button
            key={o.value}
            type="button"
            size="sm"
            variant={selected === o.value ? "default" : "outline"}
            className="flex-1 min-w-0 text-xs"
            role="radio"
            aria-checked={selected === o.value}
            onClick={() => onSelect(o.value)}
          >
            {o.label}
          </Button>
        ))}
      </div>
      {helperText && (
        <p className="text-xs text-muted-foreground/90">{helperText}</p>
      )}
    </div>
  );
}

function FilePickerField({
  id,
  label,
  filled,
  value,
  onBrowse,
  helperText,
  optional = false,
}: {
  id: string;
  label: string;
  filled: boolean;
  value: string;
  onBrowse: () => Promise<void>;
  helperText?: string;
  optional?: boolean;
}) {
  const { t } = useTranslation();
  const preview = getFilename(value);
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-3">
        <Label
          htmlFor={id}
          className="text-xs font-medium uppercase tracking-wide text-muted-foreground"
        >
          {label}
        </Label>
        <span
          className={`rounded-full px-2 py-0.5 text-xs font-medium ${
            filled ? "bg-primary/10 text-primary" : "bg-muted text-muted-foreground"
          }`}
        >
          {filled
            ? t("mame.inputPanel.fileReady")
            : optional
              ? t("mame.buildEvolvepro.optionalStateLabel")
              : t("mame.buildEvolvepro.requiredStateLabel")}
        </span>
      </div>
      <div className="flex gap-1.5">
        {/* Browse-only selection: the path field is read-only (no manual edit),
            showing the selected filename. Full path is in the title tooltip. */}
        <Input
          id={id}
          value={preview}
          readOnly
          placeholder={t("mame.inputPanel.noPathSelected")}
          className="h-8 flex-1 min-w-0 text-xs font-mono"
          aria-label={label}
          title={value || undefined}
        />
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => void onBrowse()}
          className="h-8 gap-1 px-2"
        >
          <FolderOpen size={12} aria-hidden="true" />
        </Button>
      </div>
      {helperText && (
        <p className="text-xs text-muted-foreground/90">{helperText}</p>
      )}
      <p className="truncate text-xs text-muted-foreground" title={value || undefined}>
        {filled ? preview : t("mame.inputPanel.noPathSelected")}
      </p>
    </div>
  );
}
