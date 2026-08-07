/**
 * Unified MAME Step 4 (Activity Data) measurement builder.
 *
 * Generic long-format, pre-normalized GC, and raw Agilent inputs are adapters
 * into one NGS-qualified EVOLVEpro export. Plate layout is mapping metadata,
 * and optional variant-labeled confirmation is normalized independently before
 * it overrides the primary measurement.
 */

import { useState, useCallback, useEffect, useMemo, useRef } from "react";
import { useTranslation } from "react-i18next";
import { open, save } from "@tauri-apps/plugin-dialog";
import { mkdir } from "@tauri-apps/plugin-fs";
import { FolderOpen, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { buildEvolveproInput } from "@/lib/ipc-mame";
import { useKumaProject } from "@/state/projectContext";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import { useRoundStore } from "@/store/round/roundSlice";
import { describeRpcError, extractMissingMethod } from "@/lib/errors";
import { revealInOSFolder } from "@/lib/openFolder";
import { registerArtifacts } from "@/lib/workspace";
import {
  EVOLVEPRO_INPUT_FOLDER,
  evolveproInputFilename,
  roundOwningOutput,
} from "@/lib/round/roundArtifacts";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { InlineHelp } from "@/components/ui/InlineHelp";
import { Label } from "@/components/ui/label";
import type {
  BuildEvolveproInputParams,
  BuildEvolveproInputResult,
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

const PRIMARY_HELP: Record<FormState["primarySource"], string> = {
  longFormat: "mame.buildEvolvepro.primarySourceLongFormatHelper",
  gcSheet: "mame.buildEvolvepro.primarySourceGcSheetHelper",
  rawReport: "mame.buildEvolvepro.primarySourceRawReportHelper",
};

const CONFIRMATION_HELP: Record<FormState["confirmationSource"], string> = {
  none: "mame.buildEvolvepro.confirmationSourceNoneHelper",
  variantLabels: "mame.buildEvolvepro.confirmationSourceVariantLabelsHelper",
};

export function BuildEvolveproInputPanel() {
  const { t } = useTranslation();
  const project = useKumaProject();
  const activeRoundId = useRoundStore((s) => s.active_round_id);
  const rounds = useRoundStore((s) => s.rounds);
  const activeRoundNumber = useRoundStore(
    (s) => s.rounds.find((candidate) => candidate.id === s.active_round_id)?.n ?? 1,
  );
  const roundVerdictPath = useRoundStore((s) => {
    const round = s.rounds.find((candidate) => candidate.id === s.active_round_id);
    const value = round?.genotype.verdict_xlsx;
    return typeof value === "string" ? value : "";
  });
  const roundEvidenceSignature = useRoundStore((s) => {
    const round = s.rounds.find((candidate) => candidate.id === s.active_round_id);
    const value = round?.genotype.evidence_signature;
    return typeof value === "string" ? value : "";
  });
  const [form, setFormRaw] = useState<FormState>(() => loadFromStorage(project?.path));
  const [showRestoredNotice, setShowRestoredNotice] = useState(() =>
    hasBuildEvolveproFormValues(loadFromStorage(project?.path)),
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
    const loaded = loadFromStorage(project?.path);
    setFormRaw(loaded);
    setShowRestoredNotice(hasBuildEvolveproFormValues(loaded));
    setResult(null);
    setBuildEvolveproCompletion(null);
  }, [project?.path, setBuildEvolveproCompletion]);

  useEffect(() => {
    formRef.current = form;
  }, [form]);

  function setForm(partial: Partial<FormState>) {
    setFormRaw((prev) => {
      const next = { ...prev, ...partial, migrationNotice: false };
      saveToStorage(next, project?.path);
      formGenerationRef.current += 1;
      setBuildEvolveproCompletion(null);
      return next;
    });
  }

  // The default destination carries the round number so building round 2 does
  // not write over what round 1 produced, which is the series step 4.2 reads.
  // It is re-derived when the active round changes, but only while the path is
  // still one this panel generated: `outputXlsxRoundId` names that round, and
  // browsing clears it, so a hand-picked destination is never rewritten under
  // the operator. A path restored from an older project also has no round id
  // and is left alone for the same reason; the collision notice below is what
  // catches it once a round has recorded that file as its output.
  useEffect(() => {
    if (!project?.path || form.migrationNotice || !activeRoundId) return;
    const panelOwnsPath = !form.outputXlsx || Boolean(form.outputXlsxRoundId);
    if (!panelOwnsPath) return;
    if (form.outputXlsx && form.outputXlsxRoundId === activeRoundId) return;
    setForm({
      outputXlsx: projectFile(
        project.path,
        EVOLVEPRO_INPUT_FOLDER,
        evolveproInputFilename(activeRoundNumber),
      ),
      outputXlsxRoundId: activeRoundId,
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    project?.path,
    form.outputXlsx,
    form.outputXlsxRoundId,
    form.migrationNotice,
    activeRoundId,
    activeRoundNumber,
  ]);

  useEffect(() => {
    setResult(null);
  }, [form]);

  useEffect(() => {
    if (resetEpoch === 0) return;
    setFormRaw(BUILD_EVOLVEPRO_DEFAULT_STATE);
    saveToStorage(BUILD_EVOLVEPRO_DEFAULT_STATE, project?.path);
    formGenerationRef.current += 1;
    setShowRestoredNotice(false);
    setBuildEvolveproCompletion(null);
    setResult(null);
  }, [project?.path, resetEpoch, setBuildEvolveproCompletion]);

  const browseFile = useCallback(
    async (key: keyof FormState, title: string, extensions: string[]) => {
      const selected = toSinglePath(
        await open({ directory: false, filters: [{ name: "Input", extensions }], title }),
      );
      if (selected) {
        setForm({
          [key]: selected,
          ...(key === "verdictXlsx" ? { verdictEvidenceSignature: "" } : {}),
        } as Partial<FormState>);
      }
    },
    [],
  );
  useEffect(() => {
    if (!activeRoundId || !roundVerdictPath) return;
    const evidenceChanged =
      Boolean(form.verdictEvidenceSignature) &&
      form.verdictEvidenceSignature !== roundEvidenceSignature;
    if (!form.verdictXlsx || evidenceChanged) {
      setForm({
        verdictXlsx: roundVerdictPath,
        verdictEvidenceSignature: roundEvidenceSignature,
      });
    }
  // setForm intentionally writes the current project-scoped form.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeRoundId, roundEvidenceSignature, roundVerdictPath]);

  const browseXlsx = useCallback(
    (key: keyof FormState, title: string) => browseFile(key, title, ["xlsx"]),
    [browseFile],
  );

  const browseOutput = useCallback(async () => {
    const defaultPath = project?.path
      ? form.outputXlsx ||
        projectFile(
          project.path,
          EVOLVEPRO_INPUT_FOLDER,
          evolveproInputFilename(activeRoundNumber),
        )
      : form.outputXlsx || undefined;
    const selected = await save({
      defaultPath,
      filters: [{ name: "Excel", extensions: ["xlsx"] }],
      title: t("mame.buildEvolvepro.chooseOutput"),
    });
    // Clearing the round id marks the path as the operator choice, which the
    // effect above never rewrites.
    if (selected) setForm({ outputXlsx: selected, outputXlsxRoundId: "" });
  }, [activeRoundNumber, form.outputXlsx, project?.path, t]);

  // A destination another round already recorded. Building writes over that
  // round measurements while its entry still points at the file, so say so
  // instead of letting the overwrite happen quietly.
  const collidingRound = useMemo(
    () => roundOwningOutput(rounds, form.outputXlsx, activeRoundId),
    [rounds, form.outputXlsx, activeRoundId],
  );

  const missing: { label: string; fieldId: string }[] = [];
  const need = (key: string, fieldId: string) =>
    missing.push({ label: t(`mame.buildEvolvepro.${key}`), fieldId });

  if (form.primarySource === "longFormat") {
    if (!form.activityPath) missing.push({ label: "Activity CSV/XLSX", fieldId: "bep-activity" });
  } else {
    if (!form.layoutXlsx) need("layoutXlsx", "bep-layout");
    if (form.primarySource === "gcSheet" && !form.gcDataXlsx) need("gcDataXlsx", "bep-gc");
    if (form.primarySource === "rawReport" && !form.round1ReportXlsx) need("round1ReportXlsx", "bep-round1");
  }
  if (form.confirmationSource === "variantLabels" && !form.remeasureReportXlsx) {
    need("remeasureReportXlsx", "bep-remeasure");
  }
  if (!form.verdictXlsx) need("verdictXlsx", "bep-verdict");
  if (!form.outputXlsx) need("outputXlsx", "bep-output-path");
  if (form.migrationNotice) missing.push({ label: "Unsupported saved mode", fieldId: "bep-input-files" });

  const canBuild = missing.length === 0 && !isBuilding;

  function buildParams(): BuildEvolveproInputParams {
    const primary =
      form.primarySource === "longFormat"
        ? {
            activity_path: form.activityPath,
            activity_scale: form.activityScale,
            layout_xlsx: form.layoutXlsx || undefined,
          }
        : form.primarySource === "gcSheet"
          ? { gc_data_xlsx: form.gcDataXlsx, layout_xlsx: form.layoutXlsx }
          : { round1_report_xlsx: form.round1ReportXlsx, layout_xlsx: form.layoutXlsx };
    return {
      ...primary,
      remeasure_report_xlsx:
        form.confirmationSource === "variantLabels" ? form.remeasureReportXlsx : undefined,
      verdict_xlsx: form.verdictXlsx,
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
      // File it on the round so step 4.2 can rebuild the series. The workspace
      // manifest below keeps only the newest EVOLVEpro input of the project
      // (one `app::step::type` slot), which is what KURO imports from.
      //
      // The wild-type replicates are filed with it rather than beside it: the
      // workbook drops the WT rows, and step 4.2 needs them to run the
      // bootstrap behind switch_combinatorial and stop. Keeping them in the
      // same record means a rebuild replaces the file and the replicates
      // together, so a stale spread can never be read against a fresh file.
      if (activeRoundId) {
        useRoundStore.getState().updateRoundField(activeRoundId, "evolvepro_input", {
          path: res.output_path,
          produced_at: new Date().toISOString(),
          wt_values: res.wt_values,
        });
      }
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
    saveToStorage(BUILD_EVOLVEPRO_DEFAULT_STATE, project?.path);
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
              {form.migrationNotice
                ? t("mame.buildEvolvepro.migrationUnsupported")
                : t("mame.buildEvolvepro.restoredNotice")}
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
          <ChoiceToggle
            label={t("mame.buildEvolvepro.primarySourceLabel")}
            helperText={t(PRIMARY_HELP[form.primarySource])}
            helpText={t(PRIMARY_HELP[form.primarySource])}
            options={[
              { value: "longFormat", label: t("mame.buildEvolvepro.primarySourceLongFormat") },
              { value: "gcSheet", label: t("mame.buildEvolvepro.primarySourceGcSheet") },
              { value: "rawReport", label: t("mame.buildEvolvepro.primarySourceRawReport") },
            ]}
            selected={form.primarySource}
            onSelect={(v) => setForm({ primarySource: v as FormState["primarySource"] })}
          />

          {form.primarySource === "longFormat" ? (
            <>
              <FilePickerField
                id="bep-activity"
                label={t("mame.buildEvolvepro.activityPath")}
                filled={Boolean(form.activityPath)}
                value={form.activityPath}
                onBrowse={() => browseFile("activityPath", t("mame.buildEvolvepro.activityPath"), ["csv", "xlsx"])}
                helperText={t("mame.buildEvolvepro.activityPathHelper")}
                helpText={t("mame.buildEvolvepro.activityPathHelper")}
              />
              <ChoiceToggle
                label={t("mame.buildEvolvepro.activityScale")}
                helperText={t("mame.buildEvolvepro.activityScaleHelper")}
                helpText={t("mame.buildEvolvepro.activityScaleHelper")}
                options={[
                  { value: "raw", label: t("mame.buildEvolvepro.activityScaleRaw") },
                  { value: "relative_to_wt", label: t("mame.buildEvolvepro.activityScaleRelative") },
                ]}
                selected={form.activityScale}
                onSelect={(v) => setForm({ activityScale: v as FormState["activityScale"] })}
              />
              <FilePickerField
                id="bep-layout"
                label={`${t("mame.buildEvolvepro.layoutXlsx")} (${t("mame.buildEvolvepro.optionalLabel")})`}
                filled={Boolean(form.layoutXlsx)}
                value={form.layoutXlsx}
                onBrowse={() => browseXlsx("layoutXlsx", t("mame.buildEvolvepro.layoutXlsx"))}
                helperText={t("mame.buildEvolvepro.layoutXlsxOptionalHelper")}
                helpText={t("mame.buildEvolvepro.layoutXlsxOptionalHelper")}
              />
            </>
          ) : (
            <>
              <FilePickerField
                id="bep-layout"
                label={t("mame.buildEvolvepro.layoutXlsx")}
                filled={Boolean(form.layoutXlsx)}
                value={form.layoutXlsx}
                onBrowse={() => browseXlsx("layoutXlsx", t("mame.buildEvolvepro.layoutXlsx"))}
                helperText={t("mame.buildEvolvepro.layoutXlsxHelper")}
                helpText={t("mame.buildEvolvepro.layoutXlsxHelper")}
              />
              <FilePickerField
                id={form.primarySource === "gcSheet" ? "bep-gc" : "bep-round1"}
                label={form.primarySource === "gcSheet" ? t("mame.buildEvolvepro.gcDataXlsx") : t("mame.buildEvolvepro.round1ReportXlsx")}
                filled={Boolean(form.primarySource === "gcSheet" ? form.gcDataXlsx : form.round1ReportXlsx)}
                value={form.primarySource === "gcSheet" ? form.gcDataXlsx : form.round1ReportXlsx}
                onBrowse={() => browseXlsx(
                  form.primarySource === "gcSheet" ? "gcDataXlsx" : "round1ReportXlsx",
                  form.primarySource === "gcSheet" ? t("mame.buildEvolvepro.gcDataXlsx") : t("mame.buildEvolvepro.round1ReportXlsx"),
                )}
                helperText={form.primarySource === "gcSheet" ? t("mame.buildEvolvepro.gcDataXlsxHelper") : t("mame.buildEvolvepro.round1ReportXlsxHelper")}
                helpText={form.primarySource === "gcSheet" ? t("mame.buildEvolvepro.gcDataXlsxHelper") : t("mame.buildEvolvepro.round1ReportXlsxHelper")}
              />
            </>
          )}

          <ChoiceToggle
            label={t("mame.buildEvolvepro.confirmationSourceLabel")}
            helperText={t(CONFIRMATION_HELP[form.confirmationSource])}
            helpText={t(CONFIRMATION_HELP[form.confirmationSource])}
            options={[
              { value: "none", label: t("mame.buildEvolvepro.confirmationSourceNone") },
              { value: "variantLabels", label: t("mame.buildEvolvepro.confirmationSourceVariantLabels") },
            ]}
            selected={form.confirmationSource}
            onSelect={(v) => setForm({ confirmationSource: v as FormState["confirmationSource"] })}
          />

          {form.confirmationSource === "variantLabels" && (
            <FilePickerField
              id="bep-remeasure"
              label={t("mame.buildEvolvepro.remeasureReportXlsx")}
              filled={Boolean(form.remeasureReportXlsx)}
              value={form.remeasureReportXlsx}
              onBrowse={() => browseXlsx("remeasureReportXlsx", t("mame.buildEvolvepro.remeasureReportXlsx"))}
              helperText={t("mame.buildEvolvepro.remeasureReportXlsxHelper")}
              helpText={t("mame.buildEvolvepro.remeasureReportXlsxHelper")}
            />
          )}

          <FilePickerField
            id="bep-verdict"
            label={t("mame.buildEvolvepro.verdictXlsx")}
            filled={Boolean(form.verdictXlsx)}
            value={form.verdictXlsx}
            onBrowse={() => browseXlsx("verdictXlsx", t("mame.buildEvolvepro.verdictXlsx"))}
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
          {collidingRound && (
            <p
              role="status"
              className="rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-400"
            >
              {t("mame.buildEvolvepro.outputCollidesRound", {
                round: collidingRound.n,
              })}
            </p>
          )}
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

      <p className="text-xs text-muted-foreground">
        {t("mame.buildEvolvepro.builtFromLabel")}
      </p>

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
