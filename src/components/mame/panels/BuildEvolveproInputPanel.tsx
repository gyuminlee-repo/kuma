/**
 * Unified MAME Step 4 (Activity Data) measurement builder.
 *
 * Generic long-format, pre-normalized GC, and raw Agilent inputs are adapters
 * into one NGS-qualified EVOLVEpro export. Plate layout is optional mapping
 * metadata (the verdict sheet carries the same well identities when it is
 * absent),
 * and optional variant-labeled confirmation is normalized independently before
 * it overrides the primary measurement.
 */

import { useState, useCallback, useEffect, useMemo, useRef } from "react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { open, save } from "@tauri-apps/plugin-dialog";
import { mkdir } from "@tauri-apps/plugin-fs";
import { FolderOpen, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { buildEvolveproInput, detectMeasurementSource } from "@/lib/ipc-mame";
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
import type {
  DetectMeasurementSourceResult,
  MeasurementSource,
} from "@/types/mame/detect_measurement_source";
import {
  type BuildEvolveproFormState as FormState,
  buildEvolveproFormSignature,
  loadBuildEvolveproFromStorage as loadFromStorage,
  saveBuildEvolveproToStorage as saveToStorage,
  BUILD_EVOLVEPRO_DEFAULT_STATE,
  createBuildEvolveproCompletion,
  hasBuildEvolveproFormValues,
  buildEvolveproNeedsOrderSource,
  hasBuildEvolveproOrderSource,
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
  numericReport: "mame.buildEvolvepro.primarySourceNumericReportHelper",
};

const CONFIRMATION_HELP: Record<FormState["confirmationSource"], string> = {
  none: "mame.buildEvolvepro.confirmationSourceNoneHelper",
  variantLabels: "mame.buildEvolvepro.confirmationSourceVariantLabelsHelper",
  numericIds: "mame.buildEvolvepro.confirmationSourceNumericIdsHelper",
};

/** Display name of every source the detector can report. */
const SOURCE_LABEL: Record<MeasurementSource, string> = {
  longFormat: "mame.buildEvolvepro.primarySourceLongFormat",
  gcSheet: "mame.buildEvolvepro.primarySourceGcSheet",
  rawReport: "mame.buildEvolvepro.primarySourceRawReport",
  numericReport: "mame.buildEvolvepro.primarySourceNumericReport",
  confirmationVariantLabels: "mame.buildEvolvepro.confirmationSourceVariantLabels",
  confirmationNumericIds: "mame.buildEvolvepro.confirmationSourceNumericIds",
};

/**
 * Exactly one primary path field may hold a value: the backend refuses a call
 * that names two ("exactly one primary source"), so every selection blanks the
 * other three.
 */
const CLEARED_PRIMARY_PATHS = {
  activityPath: "",
  gcDataXlsx: "",
  round1ReportXlsx: "",
  numericReportXlsx: "",
} as const;

function isPrimarySource(
  source: MeasurementSource,
): source is FormState["primarySource"] {
  return (
    source === "longFormat" ||
    source === "gcSheet" ||
    source === "rawReport" ||
    source === "numericReport"
  );
}

/** The measurement path the currently selected primary source reads. */
function primaryPathOf(form: FormState): string {
  switch (form.primarySource) {
    case "longFormat":
      return form.activityPath;
    case "gcSheet":
      return form.gcDataXlsx;
    case "rawReport":
      return form.round1ReportXlsx;
    case "numericReport":
      return form.numericReportXlsx;
  }
}

/**
 * One line saying what the operator is being asked to decide, for a pair the
 * file itself cannot settle. Both pairs are named in
 * `kuma_core/mame/activity/detect_measurement_source.py`.
 */
function ambiguityHelpKey(candidates: MeasurementSource[]): string {
  const found = new Set(candidates);
  if (found.has("gcSheet") && found.has("longFormat")) {
    return "mame.buildEvolvepro.ambiguityGcVsLongFormat";
  }
  if (found.has("numericReport") && found.has("confirmationNumericIds")) {
    return "mame.buildEvolvepro.ambiguityNumericRound";
  }
  return "mame.buildEvolvepro.ambiguityGeneric";
}

/**
 * What the panel knows about the file the operator just chose. `idle` is the
 * mount state and the state after a reset: a restored path was never read by
 * the detector, so nothing about it is reported as detected.
 */
type DetectionState =
  | { status: "idle" }
  | { status: "detecting"; path: string }
  | { status: "detected"; path: string; result: DetectMeasurementSourceResult }
  | { status: "failed"; path: string; message: string };

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
  const [allowLabelMismatch, setAllowLabelMismatch] = useState(false);
  // Verdict and output are both auto-filled, so they render as one-line
  // summaries until the operator asks to change them. Kept out of the `form`
  // reset effect below: that effect also fires on the auto-fill writes, which
  // would collapse a picker the operator has just opened.
  const [showVerdictPicker, setShowVerdictPicker] = useState(false);
  const [showOutputPicker, setShowOutputPicker] = useState(false);
  const [buildError, setBuildError] = useState<string | null>(null);
  const [result, setResult] = useState<BuildEvolveproInputResult | null>(null);
  const resetEpoch = useMameAppStore((s) => s.resetEpoch);
  const seedEpoch = useMameAppStore((s) => s.buildEvolveproSeedEpoch);
  const setBuildEvolveproCompletion = useMameAppStore(
    (s) => s.setBuildEvolveproCompletion,
  );
  const formRef = useRef(form);
  const formGenerationRef = useRef(0);
  // The format is read from the file rather than declared up front. `pending`
  // holds a chosen file whose format is not settled yet, so nothing is written
  // to the form until it is: a half-applied path would leave the operator
  // looking at a source they never picked. `manualFormat` is the override, the
  // operator overruling (or standing in for) the detector.
  const [detection, setDetection] = useState<DetectionState>({ status: "idle" });
  const [pendingPath, setPendingPath] = useState("");
  const [manualFormat, setManualFormat] = useState(false);
  // Bumped on every browse and every reset. A detection that answers after
  // its generation has passed is describing a file the operator has moved on
  // from, so it is dropped. Same guard as `formGenerationRef` on the build.
  const detectGenerationRef = useRef(0);
  const resetDetection = useCallback(() => {
    detectGenerationRef.current += 1;
    setDetection({ status: "idle" });
    setPendingPath("");
    setManualFormat(false);
  }, []);
  // Plate layout is optional in every branch, so it starts folded away. A
  // layout that is already selected (restored, seeded, or just browsed) is
  // never hidden from the operator.
  const [layoutOpen, setLayoutOpen] = useState(() => Boolean(form.layoutXlsx));
  useEffect(() => {
    if (form.layoutXlsx) setLayoutOpen(true);
  }, [form.layoutXlsx]);

  useEffect(() => {
    const loaded = loadFromStorage(project?.path);
    setFormRaw(loaded);
    setShowRestoredNotice(hasBuildEvolveproFormValues(loaded));
    setResult(null);
    setBuildEvolveproCompletion(null);
    resetDetection();
  }, [project?.path, resetDetection, setBuildEvolveproCompletion]);

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
    // Acknowledgement is evidence-specific: changing any source may change
    // the label audit, so never carry approval from an earlier set of files.
    setAllowLabelMismatch(false);
  }, [form]);

  useEffect(() => {
    if (resetEpoch === 0) return;
    setFormRaw(BUILD_EVOLVEPRO_DEFAULT_STATE);
    saveToStorage(BUILD_EVOLVEPRO_DEFAULT_STATE, project?.path);
    formGenerationRef.current += 1;
    setShowRestoredNotice(false);
    setBuildEvolveproCompletion(null);
    setResult(null);
    resetDetection();
  }, [project?.path, resetEpoch, resetDetection, setBuildEvolveproCompletion]);

  // loadSampleData bumps this once it has finished writing sample paths to
  // this project's storage row. `seedBuildEvolveproForm` only touches
  // localStorage, so a panel already mounted (and therefore already holding
  // whatever it read at mount, before the seed landed) would otherwise keep
  // showing stale, empty fields until the operator navigated away and back.
  // Starts at 0, same convention as resetEpoch, so the mount-time load above
  // is not re-run here too.
  useEffect(() => {
    if (seedEpoch === 0) return;
    const loaded = loadFromStorage(project?.path);
    setFormRaw(loaded);
    setShowRestoredNotice(hasBuildEvolveproFormValues(loaded));
    setResult(null);
    setBuildEvolveproCompletion(null);
    resetDetection();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seedEpoch]);

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

  /**
   * Route one measurement file to the field its format reads from. Selecting a
   * primary source blanks the other three primary paths; selecting a
   * confirmation source leaves the primary alone, because a confirmation file
   * does not replace the measurement it overrides.
   */
  function applySelection(source: MeasurementSource, path: string) {
    if (!path) return;
    if (source === "confirmationVariantLabels") {
      setForm({ confirmationSource: "variantLabels", remeasureReportXlsx: path });
    } else if (source === "confirmationNumericIds") {
      setForm({ confirmationSource: "numericIds", remeasureNumericXlsx: path });
    } else {
      const patch: Partial<FormState> = {
        ...CLEARED_PRIMARY_PATHS,
        primarySource: source,
      };
      if (source === "longFormat") patch.activityPath = path;
      else if (source === "gcSheet") patch.gcDataXlsx = path;
      else if (source === "rawReport") patch.round1ReportXlsx = path;
      else patch.numericReportXlsx = path;
      setForm(patch);
    }
    setPendingPath("");
    setManualFormat(false);
  }

  /**
   * Pick the measurement file first and read its format from it. The detector
   * runs once per selection, never on render, and its answer is a list: one
   * candidate is applied, two are offered, none falls back to the manual
   * choice. A detector that cannot answer must not stop the operator, so a
   * rejected call opens the same manual choice.
   */
  async function handleMeasurementBrowse() {
    const selected = toSinglePath(
      await open({
        directory: false,
        filters: [{ name: "Measurement", extensions: ["csv", "xlsx", "xls"] }],
        title: t("mame.buildEvolvepro.measurementFile"),
      }),
    );
    if (!selected) return;
    detectGenerationRef.current += 1;
    const generation = detectGenerationRef.current;
    setPendingPath(selected);
    setManualFormat(false);
    setDetection({ status: "detecting", path: selected });
    try {
      const res = await detectMeasurementSource({ measurement_path: selected });
      if (detectGenerationRef.current !== generation) return;
      setDetection({ status: "detected", path: selected, result: res });
      const only = res.candidates.length === 1 ? res.candidates[0] : undefined;
      if (only !== undefined && isPrimarySource(only)) {
        applySelection(only, selected);
      } else if (res.candidates.length === 0) {
        setManualFormat(true);
      }
    } catch (err) {
      if (detectGenerationRef.current !== generation) return;
      setDetection({
        status: "failed",
        path: selected,
        message: describeRpcError(err, "mame"),
      });
      setManualFormat(true);
    }
  }

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

  // A file whose format is not settled is held out of the form until it is,
  // so the path on screen is the pending one while that lasts.
  const measurementPath = pendingPath || primaryPathOf(form);
  const unresolved = pendingPath !== "";
  const detectionResult = detection.status === "detected" ? detection.result : null;
  const detectedCandidates = detectionResult?.candidates ?? [];
  const confirmationOnly =
    detectedCandidates.length > 0 &&
    detectedCandidates.every((candidate) => !isPrimarySource(candidate));
  const showSummary = !manualFormat && !unresolved && measurementPath !== "";
  // "Detected" is only said about a file this panel actually had read. A path
  // restored from storage was never sent to the detector.
  const appliedDetection =
    detectionResult !== null &&
    detectionResult.candidates.length === 1 &&
    detection.status === "detected" &&
    detection.path === measurementPath;

  const missing: { label: string; fieldId: string }[] = [];
  const need = (key: string, fieldId: string) =>
    missing.push({ label: t(`mame.buildEvolvepro.${key}`), fieldId });

  // One gate for all four formats: the file is chosen first and its format is
  // read from it, so what can be missing is the file. No layout gate: an
  // unselected layout means the builder derives the well->variant mapping from
  // the verdict sheet, which this form requires anyway.
  if (!primaryPathOf(form)) need("measurementFile", "bep-measurement");
  if (form.confirmationSource === "variantLabels" && !form.remeasureReportXlsx) {
    need("remeasureReportXlsx", "bep-remeasure");
  }
  if (form.confirmationSource === "numericIds" && !form.remeasureNumericXlsx) {
    need("remeasureNumericXlsx", "bep-remeasure-numeric");
  }
  // A numeric sample name is a position, so one order source has to say which
  // position holds which variant. Both at once leaves the answer ambiguous.
  if (buildEvolveproNeedsOrderSource(form) && !hasBuildEvolveproOrderSource(form)) {
    need("orderSource", "bep-expected");
  }
  if (!form.verdictXlsx) need("verdictXlsx", "bep-verdict");
  if (!form.outputXlsx) need("outputXlsx", "bep-output-path");
  if (form.migrationNotice) missing.push({ label: "Unsupported saved mode", fieldId: "bep-input-files" });

  const canBuild = missing.length === 0 && !isBuilding;

  function buildParams(): BuildEvolveproInputParams {
    const layout = form.layoutXlsx || undefined;
    const primary =
      form.primarySource === "longFormat"
        ? {
            activity_path: form.activityPath,
            activity_scale: form.activityScale,
            layout_xlsx: layout,
          }
        : form.primarySource === "gcSheet"
          ? { gc_data_xlsx: form.gcDataXlsx, layout_xlsx: layout }
          : form.primarySource === "rawReport"
            ? { round1_report_xlsx: form.round1ReportXlsx, layout_xlsx: layout }
            : { numeric_report_xlsx: form.numericReportXlsx, layout_xlsx: layout };
    return {
      ...primary,
      expected_xlsx: form.expectedXlsx || undefined,
      remeasure_report_xlsx:
        form.confirmationSource === "variantLabels" ? form.remeasureReportXlsx : undefined,
      remeasure_numeric_xlsx:
        form.confirmationSource === "numericIds" ? form.remeasureNumericXlsx : undefined,
      verdict_xlsx: form.verdictXlsx,
      output_xlsx: form.outputXlsx,
      allow_label_mismatch: allowLabelMismatch,
      mismatch_threshold: form.mismatchThreshold,
    };
  }

  async function handleBuild() {
    if (!canBuild) return;
    setIsBuilding(true);
    setResult(null);
    setBuildError(null);

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
      setBuildError(description);
      toast.error(t("mame.buildEvolvepro.toastError"), {
        description,
        duration: 12000,
      });
    } finally {
      setIsBuilding(false);
    }
  }

  // Backend refusal wording (kuma_core/mame/activity/build_evolvepro_input.py
  // and python-core/sidecar_mame/handlers/activity.py both start with it).
  const isLabelSwapError =
    buildError !== null && buildError.includes("Label swap detected");

  function handleMissingClick(fieldId: string) {
    const field = document.getElementById(fieldId);
    if (!field) return;
    if (typeof field.scrollIntoView === "function") {
      field.scrollIntoView({ block: "center", behavior: "smooth" });
    }
    field.focus();
  }

  function handleDismissError() {
    setBuildError(null);
  }

  function handleClearRestored() {
    setFormRaw(BUILD_EVOLVEPRO_DEFAULT_STATE);
    saveToStorage(BUILD_EVOLVEPRO_DEFAULT_STATE, project?.path);
    formGenerationRef.current += 1;
    setShowRestoredNotice(false);
    setBuildEvolveproCompletion(null);
    setResult(null);
    resetDetection();
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
          {showSummary ? (
            <FileSummaryRow
              id="bep-measurement"
              label={t("mame.buildEvolvepro.measurementFile")}
              value={measurementPath}
              onChange={() => setManualFormat(true)}
            />
          ) : (
            <FilePickerField
              id="bep-measurement"
              label={t("mame.buildEvolvepro.measurementFile")}
              filled={Boolean(measurementPath)}
              value={measurementPath}
              onBrowse={handleMeasurementBrowse}
              helperText={t("mame.buildEvolvepro.measurementFileHelper")}
            />
          )}

          {detection.status === "detecting" && (
            <p role="status" className="text-xs text-muted-foreground">
              {t("mame.buildEvolvepro.detectingFormat")}
            </p>
          )}

          {/* Say which format the file is being read as, and whether that was
              read from the file or carried over from a restored selection. */}
          {showSummary && (
            <p role="status" className="text-xs text-muted-foreground">
              {t(
                appliedDetection
                  ? "mame.buildEvolvepro.detectedFormat"
                  : "mame.buildEvolvepro.selectedFormat",
                { format: t(SOURCE_LABEL[form.primarySource]) },
              )}
            </p>
          )}

          {/* Two candidates: the file reads as both and cannot settle which,
              so it is put to the operator rather than guessed at. */}
          {unresolved && detectedCandidates.length > 1 && (
            <div className="space-y-1.5 rounded-md border border-border bg-muted/20 px-3 py-2">
              <p role="status" className="text-xs text-muted-foreground">
                {t("mame.buildEvolvepro.chooseBetweenFormats")}
              </p>
              <p className="text-xs text-muted-foreground">
                {t(ambiguityHelpKey(detectedCandidates))}
              </p>
              <ChoiceToggle
                label={t("mame.buildEvolvepro.primarySourceLabel")}
                options={detectedCandidates.map((candidate) => ({
                  value: candidate,
                  label: t(SOURCE_LABEL[candidate]),
                }))}
                selected=""
                onSelect={(value) =>
                  applySelection(value as MeasurementSource, pendingPath)
                }
              />
            </div>
          )}

          {/* A confirmation file in the measurement slot. The build used to
              refuse this at the end; it is named here instead, with the slot
              it belongs in offered. */}
          {unresolved && confirmationOnly && (
            <div
              role="status"
              className="space-y-1.5 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2"
            >
              <p className="text-xs text-amber-700 dark:text-amber-400">
                {t("mame.buildEvolvepro.confirmationOnlyFile")}
              </p>
              <div className="flex flex-wrap gap-1.5">
                {detectedCandidates.map((candidate) => (
                  <Button
                    key={candidate}
                    type="button"
                    variant="outline"
                    size="sm"
                    className="h-7 px-2 text-xs"
                    onClick={() => applySelection(candidate, pendingPath)}
                  >
                    {t("mame.buildEvolvepro.useAsConfirmation", {
                      format: t(SOURCE_LABEL[candidate]),
                    })}
                  </Button>
                ))}
              </div>
            </div>
          )}

          {/* Detector read the file and matched nothing: its own words, then
              the full manual choice below. */}
          {unresolved &&
            detection.status === "detected" &&
            detection.result.candidates.length === 0 && (
              <p
                role="status"
                className="rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-400"
              >
                {t("mame.buildEvolvepro.detectionNoMatch")}{" "}
                <span className="font-mono">{detection.result.reason}</span>
              </p>
            )}

          {/* Detection is not a gate: a call that failed leaves the manual
              choice open rather than blocking the file. */}
          {unresolved && detection.status === "failed" && (
            <p
              role="status"
              className="rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-400"
            >
              {t("mame.buildEvolvepro.detectionFailed")}{" "}
              <span className="text-muted-foreground">{detection.message}</span>
            </p>
          )}

          {/* The override. Reached by "Change", by an unmatched file, and by a
              detector that did not answer, so the operator can always win. */}
          {manualFormat && (
            <ChoiceToggle
              label={t("mame.buildEvolvepro.primarySourceLabel")}
              helperText={t(PRIMARY_HELP[form.primarySource])}
              options={[
                { value: "longFormat", label: t("mame.buildEvolvepro.primarySourceLongFormat") },
                { value: "gcSheet", label: t("mame.buildEvolvepro.primarySourceGcSheet") },
                { value: "rawReport", label: t("mame.buildEvolvepro.primarySourceRawReport") },
                { value: "numericReport", label: t("mame.buildEvolvepro.primarySourceNumericReport") },
              ]}
              selected={form.primarySource}
              onSelect={(value) =>
                applySelection(value as MeasurementSource, measurementPath)
              }
            />
          )}

          {/* Whether the values are raw or already relative to the wild type
              is a fact about the run, not about the file, so it stays an
              operator declaration. Shown once there is a file to describe. */}
          {form.primarySource === "longFormat" && form.activityPath && (
            <ChoiceToggle
              label={t("mame.buildEvolvepro.activityScale")}
              helperText={t("mame.buildEvolvepro.activityScaleHelper")}
              options={[
                { value: "raw", label: t("mame.buildEvolvepro.activityScaleRaw") },
                { value: "relative_to_wt", label: t("mame.buildEvolvepro.activityScaleRelative") },
              ]}
              selected={form.activityScale}
              onSelect={(v) => setForm({ activityScale: v as FormState["activityScale"] })}
            />
          )}

          <LayoutDisclosure open={layoutOpen} onOpenChange={setLayoutOpen}>
            <FilePickerField
              id="bep-layout"
              label={`${t("mame.buildEvolvepro.layoutXlsx")} (${t("mame.buildEvolvepro.optionalLabel")})`}
              filled={Boolean(form.layoutXlsx)}
              value={form.layoutXlsx}
              onBrowse={() => browseXlsx("layoutXlsx", t("mame.buildEvolvepro.layoutXlsx"))}
              helperText={
                form.primarySource === "longFormat"
                  ? t("mame.buildEvolvepro.layoutXlsxOptionalHelper")
                  : t("mame.buildEvolvepro.layoutXlsxHelper")
              }
              optional
            />
          </LayoutDisclosure>

          {buildEvolveproNeedsOrderSource(form) && (
            <FilePickerField
              id="bep-expected"
              label={t("mame.buildEvolvepro.expectedXlsx")}
              filled={Boolean(form.expectedXlsx)}
              value={form.expectedXlsx}
              onBrowse={() => browseFile("expectedXlsx", t("mame.buildEvolvepro.expectedXlsx"), ["xlsx", "xls", "csv", "tsv", "txt"])}
              helperText={t("mame.buildEvolvepro.expectedXlsxHelper")}
            />
          )}

          <ChoiceToggle
            label={t("mame.buildEvolvepro.confirmationSourceLabel")}
            helperText={t(CONFIRMATION_HELP[form.confirmationSource])}
            options={[
              { value: "none", label: t("mame.buildEvolvepro.confirmationSourceNone") },
              { value: "variantLabels", label: t("mame.buildEvolvepro.confirmationSourceVariantLabels") },
              { value: "numericIds", label: t("mame.buildEvolvepro.confirmationSourceNumericIds") },
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
            />
          )}

          {form.confirmationSource === "numericIds" && (
            <FilePickerField
              id="bep-remeasure-numeric"
              label={t("mame.buildEvolvepro.remeasureNumericXlsx")}
              filled={Boolean(form.remeasureNumericXlsx)}
              value={form.remeasureNumericXlsx}
              onBrowse={() => browseXlsx("remeasureNumericXlsx", t("mame.buildEvolvepro.remeasureNumericXlsx"))}
              helperText={t("mame.buildEvolvepro.remeasureNumericXlsxHelper")}
            />
          )}

          {/* Only a confirmation source fills the authoritative side of the
              merge, so with no confirmation this threshold can never flag
              anything. The value itself is kept and still sent. */}
          {form.confirmationSource !== "none" && (
            <div className="space-y-1">
              <Label htmlFor="bep-mismatch-threshold">
                {t("mame.buildEvolvepro.mismatchThreshold")}
              </Label>
              <Input
                id="bep-mismatch-threshold"
                type="number"
                min={0.001}
                step={0.01}
                value={form.mismatchThreshold}
                onChange={(event) => {
                  const value = Number(event.target.value);
                  if (Number.isFinite(value) && value > 0) {
                    setForm({ mismatchThreshold: value });
                  }
                }}
                aria-describedby="bep-mismatch-threshold-help"
              />
              <p id="bep-mismatch-threshold-help" className="text-xs text-muted-foreground">
                {t("mame.buildEvolvepro.mismatchThresholdHelper")}
              </p>
            </div>
          )}

          {form.verdictXlsx && !showVerdictPicker ? (
            <FileSummaryRow
              id="bep-verdict"
              label={t("mame.buildEvolvepro.verdictXlsx")}
              value={form.verdictXlsx}
              onChange={() => setShowVerdictPicker(true)}
            />
          ) : (
            <FilePickerField
              id="bep-verdict"
              label={t("mame.buildEvolvepro.verdictXlsx")}
              filled={Boolean(form.verdictXlsx)}
              value={form.verdictXlsx}
              onBrowse={() => browseXlsx("verdictXlsx", t("mame.buildEvolvepro.verdictXlsx"))}
              helperText={t("mame.buildEvolvepro.verdictXlsxHelper")}
            />
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
          {form.outputXlsx && !showOutputPicker ? (
            <FileSummaryRow
              id="bep-output-path"
              label={t("mame.buildEvolvepro.outputXlsx")}
              value={form.outputXlsx}
              onChange={() => setShowOutputPicker(true)}
            />
          ) : (
            <>
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
            </>
          )}
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

      {buildError !== null && (
        <div
          role="alert"
          className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-foreground"
        >
          <p className="font-medium">{t("mame.buildEvolvepro.toastError")}</p>
          <p className="mt-1 whitespace-pre-wrap text-muted-foreground">{buildError}</p>
          {/* The acknowledgement only exists to clear this one refusal, so it
              is offered where the refusal is reported rather than standing on
              the form for every build. */}
          {isLabelSwapError && (
            <div className="mt-2 flex items-start gap-2 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2">
              <input
                id="bep-allow-label-mismatch"
                type="checkbox"
                checked={allowLabelMismatch}
                onChange={(event) => setAllowLabelMismatch(event.target.checked)}
                className="mt-0.5 h-4 w-4 cursor-pointer accent-primary"
              />
              <div>
                <Label
                  htmlFor="bep-allow-label-mismatch"
                  className="cursor-pointer text-xs font-medium text-foreground"
                >
                  {t("mame.buildEvolvepro.allowLabelMismatch")}
                </Label>
                <p className="mt-1 text-xs text-muted-foreground">
                  {t("mame.buildEvolvepro.allowLabelMismatchHelper")}
                </p>
              </div>
            </div>
          )}
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={handleDismissError}
            className="mt-2 h-6 px-2 text-xs"
          >
            {t("mame.buildEvolvepro.dismissError")}
          </Button>
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

/** Folded container for an input that is optional in every branch. */
function LayoutDisclosure({
  open,
  onOpenChange,
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  children: ReactNode;
}) {
  const { t } = useTranslation();
  return (
    <details
      className="rounded-md border border-border px-3 py-2"
      open={open}
      onToggle={(event) => onOpenChange(event.currentTarget.open)}
    >
      <summary className="cursor-pointer text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {`${t("mame.buildEvolvepro.layoutXlsx")} (${t("mame.buildEvolvepro.optionalLabel")})`}
      </summary>
      <div className="mt-2">{children}</div>
    </details>
  );
}

/**
 * One-line stand-in for a file field that is already filled in for the
 * operator. `id` stays on the focusable button so the "Still needed" jump
 * targets keep working if the field is ever both filled and reported.
 */
function FileSummaryRow({
  id,
  label,
  value,
  onChange,
}: {
  id: string;
  label: string;
  value: string;
  onChange: () => void;
}) {
  const { t } = useTranslation();
  const changeLabel = t("mame.buildEvolvepro.changeFile");
  return (
    <div className="flex items-center justify-between gap-3">
      <p
        className="min-w-0 flex-1 truncate text-xs text-muted-foreground"
        title={value || undefined}
      >
        <span className="font-medium uppercase tracking-wide">{label}</span>{" "}
        <span className="font-mono text-foreground">{getFilename(value)}</span>
      </p>
      <Button
        id={id}
        type="button"
        variant="outline"
        size="sm"
        className="h-7 shrink-0 px-2 text-xs"
        aria-label={`${changeLabel}: ${label}`}
        onClick={onChange}
      >
        {changeLabel}
      </Button>
    </div>
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
  // The description under the buttons belongs to whichever option is
  // selected (PRIMARY_HELP/CONFIRMATION_HELP swap it per option), but with
  // N buttons above and one sentence below there is no visual cue for which
  // option it explains. Naming the selected option's own label first turns
  // the sentence into "Selected label: description" instead of a dangling
  // caption that reads like it belongs to the whole group.
  const selectedLabel = options.find((o) => o.value === selected)?.label;
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
        <p className="text-xs text-muted-foreground/90">
          {selectedLabel && (
            <span className="font-medium text-foreground">{selectedLabel}: </span>
          )}
          {helperText}
        </p>
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
          // Icon-only control: without this the button has no accessible name.
          aria-label={t("mame.inputPanel.browseFolderAriaLabel", { label })}
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
