/**
 * BuildEvolveproInputPanel: MAME activity to EVOLVEpro input build panel.
 *
 * The build takes two independent axes, each with its own toggle:
 *   axis A, the 1-replicate primary screen. Exactly one of a raw Agilent
 *           report (well labels, needs the plate layout), a pre-normalised GC
 *           data sheet (well labels, needs the plate layout) or a previous
 *           EVOLVEpro input xlsx (variant labels, no layout).
 *   axis B, the n-replicate confirmation that overrides the baseline. At most
 *           one of a variant-labeled Agilent report or a numeric-index report
 *           (which needs a rank source). Omitting it leaves the build
 *           provisional.
 * The two axes do not constrain each other, so every combination is offered.
 * An NGS verdict file is axis-independent and always available.
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

import { useState, useCallback, useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { open, save } from "@tauri-apps/plugin-dialog";
import { mkdir } from "@tauri-apps/plugin-fs";
import { FolderOpen, Loader2, AlertTriangle } from "lucide-react";
import { toast } from "sonner";
import { buildEvolveproInput } from "@/lib/ipc-mame";
import { useKumaProject } from "@/state/projectContext";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import { describeRpcError, extractMissingMethod } from "@/lib/errors";
import { revealInOSFolder } from "@/lib/openFolder";
import { registerArtifacts } from "@/lib/workspace";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { InlineHelp } from "@/components/ui/InlineHelp";
import { Label } from "@/components/ui/label";
import type {
  BuildEvolveproInputParams,
  BuildEvolveproInputResult,
  BuildEvolveproPrimarySourceId,
  BuildEvolveproConfirmationSourceId,
} from "@/types/mame/build_evolvepro_input";
import {
  type BuildEvolveproFormState as FormState,
  buildEvolveproFormSignature,
  loadBuildEvolveproFromStorage as loadFromStorage,
  saveBuildEvolveproToStorage as saveToStorage,
  BUILD_EVOLVEPRO_DEFAULT_STATE,
  createBuildEvolveproCompletion,
  hasBuildEvolveproFormValues,
} from "@/lib/mame/buildEvolveproFormStorage";

function getFilename(p: string): string {
  if (!p) return "";
  const parts = p.split(/[/\\]/);
  return parts[parts.length - 1] ?? p;
}

function toSinglePath(result: string | string[] | null): string | null {
  return typeof result === "string" ? result : null;
}

function projectFile(projectPath: string, folder: string, filename: string): string {
  const sep = projectPath.includes("\\") ? "\\" : "/";
  return `${projectPath.replace(/[\\/]+$/, "")}${sep}${folder}${sep}${filename}`;
}

function parentDir(filePath: string): string {
  const index = Math.max(filePath.lastIndexOf("/"), filePath.lastIndexOf("\\"));
  return index > 0 ? filePath.slice(0, index) : "";
}

/** Helper copy shown under each axis toggle for the currently selected source. */
const PRIMARY_HELP: Record<FormState["primarySource"], string> = {
  rawReport: "mame.buildEvolvepro.primarySourceRawReportHelper",
  gcSheet: "mame.buildEvolvepro.primarySourceGcSheetHelper",
  prevEvolvepro: "mame.buildEvolvepro.primarySourcePrevEvolveproHelper",
};

const CONFIRMATION_HELP: Record<FormState["confirmationSource"], string> = {
  none: "mame.buildEvolvepro.confirmationSourceNoneHelper",
  variantLabels: "mame.buildEvolvepro.confirmationSourceVariantLabelsHelper",
  numericIndex: "mame.buildEvolvepro.confirmationSourceNumericIndexHelper",
};

/** Backend axis identifiers to the toggle labels they correspond to. */
const PRIMARY_SOURCE_LABEL: Record<BuildEvolveproPrimarySourceId, string> = {
  raw_report: "mame.buildEvolvepro.primarySourceRawReport",
  gc_sheet: "mame.buildEvolvepro.primarySourceGcSheet",
  prev_evolvepro: "mame.buildEvolvepro.primarySourcePrevEvolvepro",
  numeric_report: "mame.buildEvolvepro.primarySourceNumericReport",
};

const CONFIRMATION_SOURCE_LABEL: Record<
  BuildEvolveproConfirmationSourceId,
  string
> = {
  none: "mame.buildEvolvepro.confirmationSourceNone",
  variant_labels: "mame.buildEvolvepro.confirmationSourceVariantLabels",
  numeric_subset: "mame.buildEvolvepro.confirmationSourceNumericSubset",
  numeric_index: "mame.buildEvolvepro.confirmationSourceNumericIndex",
};

export function BuildEvolveproInputPanel() {
  const { t } = useTranslation();
  const project = useKumaProject();
  const [form, setFormRaw] = useState<FormState>(() => loadFromStorage());
  const [showRestoredNotice, setShowRestoredNotice] = useState(() =>
    hasBuildEvolveproFormValues(loadFromStorage()),
  );
  const [isBuilding, setIsBuilding] = useState(false);
  const [result, setResult] = useState<BuildEvolveproInputResult | null>(null);
  const resetEpoch = useMameAppStore((s) => s.resetEpoch);
  const setBuildEvolveproCompletion = useMameAppStore(
    (s) => s.setBuildEvolveproCompletion,
  );
  const formRef = useRef(form);
  const formGenerationRef = useRef(0);

  useEffect(() => {
    formRef.current = form;
  }, [form]);

  function setForm(partial: Partial<FormState>) {
    setFormRaw((prev) => {
      const next = { ...prev, ...partial };
      saveToStorage(next);
      formGenerationRef.current += 1;
      setBuildEvolveproCompletion(null);
      return next;
    });
  }

  useEffect(() => {
    if (!project?.path || form.outputXlsx) return;
    setForm({ outputXlsx: projectFile(project.path, "activity", "evolvepro_input.xlsx") });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project?.path, form.outputXlsx]);

  // Clear the previous result when any input changes so the summary never lags.
  useEffect(() => {
    setResult(null);
  }, [
    form.primarySource,
    form.confirmationSource,
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
    formGenerationRef.current += 1;
    setShowRestoredNotice(false);
    setBuildEvolveproCompletion(null);
    setResult(null);
  }, [resetEpoch, setBuildEvolveproCompletion]);

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
    const defaultPath = project?.path
      ? form.outputXlsx || projectFile(project.path, "activity", "evolvepro_input.xlsx")
      : form.outputXlsx || undefined;
    const selected = await save({
      defaultPath,
      filters: [{ name: "Excel", extensions: ["xlsx"] }],
      title: t("mame.buildEvolvepro.chooseOutput"),
    });
    if (selected) setForm({ outputXlsx: selected });
  }, [form.outputXlsx, project?.path, t]);

  // Optional review artifact, so it uses a save-file dialog like the output
  // control (never an open dialog: the file does not exist yet).
  const browseGcExport = useCallback(async () => {
    const selected = await save({
      filters: [{ name: "Excel", extensions: ["xlsx"] }],
      title: t("mame.buildEvolvepro.gcExportXlsx"),
    });
    if (selected) setForm({ gcExportXlsx: selected });
  }, [t]);

  // Client-side gate mirroring the backend _axis_sources validator, so a build
  // is never dispatched only to come back as a ValueError. Each entry is a
  // label of a still-missing required file for the selected axis pair.
  const missing: { label: string; fieldId: string }[] = [];
  const need = (key: string, fieldId: string) =>
    missing.push({ label: t(`mame.buildEvolvepro.${key}`), fieldId });

  // Axis A. The two well-labeled sources need the layout to name their wells;
  // the previous-EVOLVEpro source carries variant labels already.
  if (form.primarySource === "rawReport") {
    if (!form.layoutXlsx) need("layoutXlsx", "bep-layout");
    if (!form.round1ReportXlsx) need("round1ReportXlsx", "bep-round1");
  } else if (form.primarySource === "gcSheet") {
    if (!form.layoutXlsx) need("layoutXlsx", "bep-layout");
    if (!form.gcDataXlsx) need("gcDataXlsx", "bep-gc");
  } else if (!form.round1EvolveproXlsx) {
    need("round1EvolveproXlsx", "bep-round1-evolvepro");
  }

  // Axis B. "none" needs nothing (provisional); the numeric-index report has no
  // variant names of its own, so it needs the rank source alongside it.
  if (form.confirmationSource === "variantLabels") {
    if (!form.remeasureReportXlsx) need("remeasureReportXlsx", "bep-remeasure");
  } else if (form.confirmationSource === "numericIndex") {
    if (!form.repBatchXlsx) need("repBatchXlsx", "bep-rep");
    if (!form.prevEvolveproXlsx) need("prevEvolveproXlsx", "bep-prev");
  }

  if (!form.outputXlsx) need("outputXlsx", "bep-output-path");

  const canBuild = missing.length === 0 && !isBuilding;

  // Each axis names only the params it owns, so a path left over from a
  // previously selected source can never leak into the request and trip the
  // backend "multiple sources" checks.
  function primaryParams(): Partial<BuildEvolveproInputParams> {
    switch (form.primarySource) {
      case "rawReport":
        return {
          layout_xlsx: form.layoutXlsx,
          round1_report_xlsx: form.round1ReportXlsx,
          gc_export_xlsx: form.gcExportXlsx || undefined,
        };
      case "gcSheet":
        return {
          layout_xlsx: form.layoutXlsx,
          gc_data_xlsx: form.gcDataXlsx,
        };
      case "prevEvolvepro":
        // Layout is optional here and only maps variant to well for NGS gating.
        return {
          round1_evolvepro_xlsx: form.round1EvolveproXlsx,
          layout_xlsx: form.layoutXlsx || undefined,
        };
    }
  }

  function confirmationParams(): Partial<BuildEvolveproInputParams> {
    switch (form.confirmationSource) {
      case "none":
        return {};
      case "variantLabels":
        return { remeasure_report_xlsx: form.remeasureReportXlsx };
      case "numericIndex":
        return {
          rep_batch_xlsx: form.repBatchXlsx,
          prev_evolvepro_xlsx: form.prevEvolveproXlsx,
        };
    }
  }

  function buildParams(): BuildEvolveproInputParams {
    return {
      ...primaryParams(),
      ...confirmationParams(),
      verdict_xlsx: form.verdictXlsx || undefined,
      output_xlsx: form.outputXlsx,
    };
  }

  async function handleBuild() {
    if (!canBuild) return;
    setIsBuilding(true);
    setResult(null);

    const params = buildParams();
    const buildGeneration = formGenerationRef.current;
    const buildSignature = buildEvolveproFormSignature(form);

    try {
      const outputParent = parentDir(params.output_xlsx);
      if (outputParent) {
        await mkdir(outputParent, { recursive: true });
      }
      const res = await buildEvolveproInput(params);
      if (
        formGenerationRef.current !== buildGeneration ||
        buildEvolveproFormSignature(formRef.current) !== buildSignature
      ) {
        return;
      }
      setResult(res);
      setBuildEvolveproCompletion(
        createBuildEvolveproCompletion(form, res.output_path),
      );
      await registerArtifacts([
        {
          app: "mame",
          step: "activity",
          type: "evolvepro_csv",
          absolutePath: res.output_path,
        },
      ]).catch((err) => {
        console.warn("[workspace] mame EVOLVEpro artifact registration failed", err);
      });
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

  function handleMissingClick(fieldId: string) {
    const field = document.getElementById(fieldId);
    if (!field) return;
    if (typeof field.scrollIntoView === "function") {
      field.scrollIntoView({ block: "center", behavior: "smooth" });
    }
    field.focus();
  }

  function handleClearRestored() {
    setFormRaw(BUILD_EVOLVEPRO_DEFAULT_STATE);
    saveToStorage(BUILD_EVOLVEPRO_DEFAULT_STATE);
    formGenerationRef.current += 1;
    setShowRestoredNotice(false);
    setBuildEvolveproCompletion(null);
    setResult(null);
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
        {showRestoredNotice && (
          <div className="mt-3 flex flex-wrap items-center justify-between gap-2 rounded-md border border-border bg-muted/20 px-3 py-2">
            <p className="min-w-0 flex-1 text-xs text-muted-foreground">
              {t("mame.buildEvolvepro.restoredNotice")}
            </p>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={handleClearRestored}
              className="h-7 text-xs"
            >
              {t("mame.buildEvolvepro.clearRestored")}
            </Button>
          </div>
        )}
      </header>

      <section aria-labelledby="bep-input-files">
        <h3
          id="bep-input-files"
          className="mb-3 text-sm font-medium text-foreground"
        >
          {t("mame.buildEvolvepro.inputFiles")}
        </h3>
        <div className="space-y-4">
          {/* Axis A, the 1-replicate primary screen (exactly one source). */}
          <ChoiceToggle
            label={t("mame.buildEvolvepro.primarySourceLabel")}
            helperText={t(PRIMARY_HELP[form.primarySource])}
            helpText={t(PRIMARY_HELP[form.primarySource])}
            options={[
              {
                value: "rawReport",
                label: t("mame.buildEvolvepro.primarySourceRawReport"),
              },
              {
                value: "gcSheet",
                label: t("mame.buildEvolvepro.primarySourceGcSheet"),
              },
              {
                value: "prevEvolvepro",
                label: t("mame.buildEvolvepro.primarySourcePrevEvolvepro"),
              },
            ]}
            selected={form.primarySource}
            onSelect={(v) =>
              setForm({ primarySource: v as FormState["primarySource"] })
            }
          />

          {form.primarySource === "prevEvolvepro" ? (
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
                helperText={t("mame.buildEvolvepro.round1EvolveproXlsxHelper")}
                helpText={t("mame.buildEvolvepro.round1EvolveproXlsxHelper")}
              />
              <FilePickerField
                id="bep-layout-optional"
                label={`${t("mame.buildEvolvepro.layoutXlsx")} (${t("mame.buildEvolvepro.optionalLabel")})`}
                filled={Boolean(form.layoutXlsx)}
                value={form.layoutXlsx}
                optional
                onBrowse={() =>
                  browseXlsx("layoutXlsx", t("mame.buildEvolvepro.layoutXlsx"))
                }
                helperText={t("mame.buildEvolvepro.layoutXlsxOptionalHelper")}
                helpText={t("mame.buildEvolvepro.layoutXlsxOptionalHelper")}
              />
            </>
          ) : (
            <>
              {/* Both well-labeled sources need the layout to name their wells. */}
              <FilePickerField
                id="bep-layout"
                label={t("mame.buildEvolvepro.layoutXlsx")}
                filled={Boolean(form.layoutXlsx)}
                value={form.layoutXlsx}
                onBrowse={() =>
                  browseXlsx("layoutXlsx", t("mame.buildEvolvepro.layoutXlsx"))
                }
                helperText={t("mame.buildEvolvepro.layoutXlsxHelper")}
                helpText={t("mame.buildEvolvepro.layoutXlsxHelper")}
              />
              {form.primarySource === "rawReport" ? (
                <>
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
                    helpText={t("mame.buildEvolvepro.round1ReportXlsxHelper")}
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
              ) : (
                <FilePickerField
                  id="bep-gc"
                  label={t("mame.buildEvolvepro.gcDataXlsx")}
                  filled={Boolean(form.gcDataXlsx)}
                  value={form.gcDataXlsx}
                  onBrowse={() =>
                    browseXlsx("gcDataXlsx", t("mame.buildEvolvepro.gcDataXlsx"))
                  }
                  helperText={t("mame.buildEvolvepro.gcDataXlsxHelper")}
                  helpText={t("mame.buildEvolvepro.gcDataXlsxHelper")}
                />
              )}
            </>
          )}

          {/* Axis B, the n-replicate confirmation (optional, overrides axis A). */}
          <ChoiceToggle
            label={t("mame.buildEvolvepro.confirmationSourceLabel")}
            helperText={t(CONFIRMATION_HELP[form.confirmationSource])}
            helpText={t(CONFIRMATION_HELP[form.confirmationSource])}
            options={[
              {
                value: "none",
                label: t("mame.buildEvolvepro.confirmationSourceNone"),
              },
              {
                value: "variantLabels",
                label: t("mame.buildEvolvepro.confirmationSourceVariantLabels"),
              },
              {
                value: "numericIndex",
                label: t("mame.buildEvolvepro.confirmationSourceNumericIndex"),
              },
            ]}
            selected={form.confirmationSource}
            onSelect={(v) =>
              setForm({
                confirmationSource: v as FormState["confirmationSource"],
              })
            }
          />

          {form.confirmationSource === "variantLabels" && (
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
              helpText={t("mame.buildEvolvepro.remeasureReportXlsxHelper")}
            />
          )}

          {form.confirmationSource === "numericIndex" && (
            <>
              <FilePickerField
                id="bep-rep"
                label={t("mame.buildEvolvepro.repBatchXlsx")}
                filled={Boolean(form.repBatchXlsx)}
                value={form.repBatchXlsx}
                onBrowse={() =>
                  browseXlsx("repBatchXlsx", t("mame.buildEvolvepro.repBatchXlsx"))
                }
                helperText={t("mame.buildEvolvepro.repBatchXlsxHelper")}
                helpText={t("mame.buildEvolvepro.repBatchXlsxHelper")}
              />
              <FilePickerField
                id="bep-prev"
                label={t("mame.buildEvolvepro.prevEvolveproXlsx")}
                filled={Boolean(form.prevEvolveproXlsx)}
                value={form.prevEvolveproXlsx}
                onBrowse={() =>
                  browseXlsx(
                    "prevEvolveproXlsx",
                    t("mame.buildEvolvepro.prevEvolveproXlsx"),
                  )
                }
                helperText={t("mame.buildEvolvepro.prevEvolveproXlsxHelper")}
                helpText={t("mame.buildEvolvepro.prevEvolveproXlsxHelper")}
              />
            </>
          )}

          {/* NGS gating is axis-independent, so it stays visible throughout. */}
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
            helpText={t("mame.buildEvolvepro.verdictXlsxHelper")}
          />
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
            <span className="inline-flex items-center gap-1.5">
              <Label
                htmlFor="bep-output-path"
                className="text-xs font-medium uppercase tracking-wide text-muted-foreground"
              >
                {t("mame.buildEvolvepro.outputXlsx")}
              </Label>
              <InlineHelp text={t("mame.buildEvolvepro.outputXlsxHelper")} />
            </span>
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
        <div
          role="status"
          className="rounded-md border border-border bg-muted/30 px-3 py-2 text-xs text-muted-foreground"
        >
          <span>
            {t("mame.buildEvolvepro.missingInputs")}:{" "}
            {missing.map((item) => item.label).join(", ")}
          </span>
          <span className="mt-2 flex flex-wrap gap-1">
            {missing.map((item) => (
              <Button
                key={item.fieldId}
                type="button"
                variant="outline"
                size="sm"
                onClick={() => handleMissingClick(item.fieldId)}
                className="h-6 px-2 text-xs"
              >
                {item.label}
              </Button>
            ))}
          </span>
        </div>
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

      {/* Driven by the confirmation axis rather than the legacy rank-mode
          "confidence" field, which the backend omits on some axis pairs. A
          build without a confirmation source is provisional whatever its
          primary screen source was. */}
      <div className="space-y-1.5">
        <div
          role="status"
          className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${
            result.confirmation_source === "none"
              ? "bg-amber-500/15 text-amber-700 dark:text-amber-400"
              : "bg-primary/10 text-primary"
          }`}
        >
          {result.confirmation_source === "none"
            ? t("mame.buildEvolvepro.provisionalLabel")
            : t("mame.buildEvolvepro.confirmedLabel")}
        </div>
        <p className="text-xs text-muted-foreground">
          {t("mame.buildEvolvepro.builtFromLabel")}:{" "}
          {t(PRIMARY_SOURCE_LABEL[result.primary_source])}
          {" + "}
          {t(CONFIRMATION_SOURCE_LABEL[result.confirmation_source])}
        </p>
      </div>

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
  helpText,
}: {
  label: string;
  options: { value: string; label: string }[];
  selected: string;
  onSelect: (value: string) => void;
  helperText?: string;
  helpText?: string;
}) {
  return (
    <div className="space-y-1.5">
      <span className="inline-flex items-center gap-1.5">
        <Label className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {label}
        </Label>
        {helpText && <InlineHelp text={helpText} />}
      </span>
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
  helpText,
  optional = false,
}: {
  id: string;
  label: string;
  filled: boolean;
  value: string;
  onBrowse: () => Promise<void>;
  helperText?: string;
  helpText?: string;
  optional?: boolean;
}) {
  const { t } = useTranslation();
  const preview = getFilename(value);
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-3">
        <span className="inline-flex items-center gap-1.5">
          <Label
            htmlFor={id}
            className="text-xs font-medium uppercase tracking-wide text-muted-foreground"
          >
            {label}
          </Label>
          {helpText && <InlineHelp text={helpText} />}
        </span>
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
