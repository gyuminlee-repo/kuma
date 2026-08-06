import { useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import { useKumaProject } from "@/state/projectContext";
import { applyMameAutoDetect } from "@/hooks/useAutosaveHydration";
import { detectFromInputDir } from "@/lib/mame/detectProjectFiles";
import type { InputMode } from "@/store/mame/slice-interfaces";
import { Button } from "@/components/ui/button";
import { FileField } from "./FileField";
import { VariantColumnMapping } from "./VariantColumnMapping";
import { Spinner } from "@/components/ui/Spinner";
import { defaultMameExportFilename } from "@/lib/filename";

const INPUT_DIR_CONFIG_KEYS: Record<InputMode, { labelKey: string; helperTextKey: string; placeholderKey: string }> = {
  consensus: {
    labelKey: "mame.inputPanel.consensus.label",
    helperTextKey: "mame.inputPanel.consensus.helperText",
    placeholderKey: "mame.inputPanel.consensus.placeholder",
  },
  sorted_barcode: {
    labelKey: "mame.inputPanel.sorted_barcode.label",
    helperTextKey: "mame.inputPanel.sorted_barcode.helperText",
    placeholderKey: "mame.inputPanel.sorted_barcode.placeholder",
  },
  raw_run: {
    labelKey: "mame.inputPanel.raw_run.label",
    helperTextKey: "mame.inputPanel.raw_run.helperText",
    placeholderKey: "mame.inputPanel.raw_run.placeholder",
  },
};

function toSinglePath(result: string | string[] | null): string | null {
  return typeof result === "string" ? result : null;
}

export function InputPanel() {
  const { t } = useTranslation();
  const inputDir = useMameAppStore((s) => s.inputDir);
  const inputMode = useMameAppStore((s) => s.inputMode);
  const expectedPath = useMameAppStore((s) => s.expectedPath);
  const referencePath = useMameAppStore((s) => s.referencePath);
  const outputPath = useMameAppStore((s) => s.outputPath);
  const rawRunParams = useMameAppStore((s) => s.rawRunParams);
  const barcodeAxisCounts = useMameAppStore((s) => s.barcodeAxisCounts);
  const verdictCount = useMameAppStore((s) => s.verdicts.length);
  const setInputDir = useMameAppStore((s) => s.setInputDir);
  const setExpectedPath = useMameAppStore((s) => s.setExpectedPath);
  const checkExpectedPlateOrder = useMameAppStore((s) => s.checkExpectedPlateOrder);
  const setReferencePath = useMameAppStore((s) => s.setReferencePath);
  const setOutputPath = useMameAppStore((s) => s.setOutputPath);
  const setParams = useMameAppStore((s) => s.setParams);
  const inspectVariantSource = useMameAppStore((s) => s.inspectVariantSource);

  const project = useKumaProject();
  const [isDetecting, setIsDetecting] = useState(false);
  const [isAutoFilling, setIsAutoFilling] = useState(false);

  async function handleRedetect() {
    if (!project?.path) return;
    setIsDetecting(true);
    try {
      await applyMameAutoDetect(project.path, (filled) => {
        if (filled.length === 0) {
          toast.info(t("mame.inputPanel.toastNoFiles"));
        } else {
          toast.success(t("mame.inputPanel.toastAutoDetected", { items: filled.join(", ") }));
        }
      });
    } finally {
      setIsDetecting(false);
    }
  }

  function updateRaw(partial: Partial<typeof rawRunParams>) {
    setParams({ rawRunParams: partial });
  }

  async function browseDirectory() {
    if (isAutoFilling) return;
    const selected = toSinglePath(await open({ directory: true }));
    if (!selected) return;
    setInputDir(selected);
    setIsAutoFilling(true);
    try {
      const detectedPaths = await detectFromInputDir(selected);
      const store = useMameAppStore.getState();
      const filled: string[] = [];

      if (!store.referencePath && detectedPaths.referencePath) {
        store.setReferencePath(detectedPaths.referencePath);
        filled.push("reference");
      }
      if (!store.expectedPath && detectedPaths.expectedPath) {
        store.setExpectedPath(detectedPaths.expectedPath);
        // Auto-fill reaches the same state a manual pick does, so it owes the
        // same two questions about the file it just chose.
        void store.checkExpectedPlateOrder(detectedPaths.expectedPath);
        void store.inspectVariantSource(detectedPaths.expectedPath);
        filled.push("expected");
      }
      // An existing project's sample map is recorded, not filled in as an
      // input: nothing places wells from it any more. `validate_inputs`
      // compares it against the computed layout and refuses a disagreement.
      if (!store.legacySampleMapPath && detectedPaths.legacySampleMapPath) {
        store.setLegacySampleMapPath(detectedPaths.legacySampleMapPath);
      }
      if (!store.rawRunParams.customBarcodesPath && detectedPaths.customBarcodesPath) {
        store.setParams({ rawRunParams: { customBarcodesPath: detectedPaths.customBarcodesPath } });
        filled.push("custom barcodes");
      }
      if (!store.rawRunParams.sequencingSummaryPath && detectedPaths.sequencingSummaryPath) {
        store.setParams({ rawRunParams: { sequencingSummaryPath: detectedPaths.sequencingSummaryPath } });
        filled.push("sequencing summary");
      }

      if (filled.length > 0) {
        toast.success(t("mame.inputPanel.toastAutoDetected", { items: filled.join(", ") }));
      }
    } finally {
      setIsAutoFilling(false);
    }
  }

  async function browseExpected() {
    const selected = toSinglePath(
      await open({
        directory: false,
        filters: [{ name: "Variant list (Excel / CSV)", extensions: ["xlsx", "csv"] }],
      }),
    );
    if (!selected) return;
    setExpectedPath(selected);
    // Ask about this one workbook now, not at analyze time. Picking the file is
    // where the 2026-08-04 plate mismatch entered and the last moment the answer
    // is still cheap to act on. Not the full validate_inputs: the other inputs
    // may not be chosen yet, and their absence would bury the answer under
    // errors about files the operator has not reached.
    void checkExpectedPlateOrder(selected);
    // Same moment, same reason: the mapping picker can only offer sheets and
    // columns it has read, and the auto-detected column it preselects is the
    // one the backend would read on its own.
    void inspectVariantSource(selected);
  }

  async function browseReference() {
    const selected = toSinglePath(
      await open({
        directory: false,
        filters: [
          {
            name: "Sequence (FASTA / GenBank / SnapGene)",
            extensions: ["fasta", "fa", "fna", "gb", "gbk", "gbff", "dna"],
          },
        ],
      }),
    );
    if (selected) setReferencePath(selected);
  }

  async function browseOutput() {
    const selected = toSinglePath(await open({ directory: true, title: "Select export folder" }));
    if (selected) setOutputPath(selected);
  }

  async function browseCustomBarcodes() {
    const selected = toSinglePath(
      await open({
        directory: false,
        filters: [{ name: "Barcode files", extensions: ["xlsx", "csv"] }],
        title: "Select custom barcode file",
      }),
    );
    if (selected) updateRaw({ customBarcodesPath: selected });
  }

  const inputDirKeys = INPUT_DIR_CONFIG_KEYS[inputMode];
  const noPathLabel = t("mame.inputPanel.noPathSelected");
  const readyLabel = t("mame.inputPanel.fileReady");

  return (
    <div className="rounded-lg border border-border bg-background p-4 space-y-4">
      <header className="flex items-start justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-foreground">{t("mame.inputPanel.title")}</h3>
          <p className="mt-1 text-xs text-muted-foreground">
            {t("mame.inputPanel.subtitle")}
          </p>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => void handleRedetect()}
          disabled={!project?.path || isDetecting}
          aria-label={t("mame.inputPanel.redetectAriaLabel")}
          className="h-7 shrink-0"
        >
          {isDetecting ? (
            <Spinner size="sm" />
          ) : (
            <RefreshCw className="h-3 w-3" aria-hidden="true" />
          )}
          <span className="ml-1">
            {isDetecting ? t("mame.inputPanel.redetecting") : t("mame.inputPanel.redetect")}
          </span>
        </Button>
      </header>

      <FileField
        label={t(inputDirKeys.labelKey)}
        value={inputDir}
        onChange={setInputDir}
        onBrowse={browseDirectory}
        placeholder={t(inputDirKeys.placeholderKey)}
        stateLabel={t("mame.inputPanel.kuroXlsx.stateLabel")}
        filled={Boolean(inputDir)}
        helperText={t(inputDirKeys.helperTextKey)}
        helpText={t(inputDirKeys.helperTextKey)}
        noPathLabel={noPathLabel}
        readyLabel={readyLabel}
        browseAriaLabel={t("mame.inputPanel.browseFolderAriaLabel", { label: t(inputDirKeys.labelKey) })}
      />
      {inputMode === "raw_run" && rawRunParams.sequencingSummaryPath && (
        <p className="text-xs text-muted-foreground -mt-2 pl-1">
          ✓ {rawRunParams.sequencingSummaryPath.split(/[/\\]/).pop()}
        </p>
      )}
      {inputMode === "raw_run" && (
        <>
          <FileField
            label={t("mame.inputPanel.customBarcodes.label")}
            value={rawRunParams.customBarcodesPath}
            onChange={(value) => updateRaw({ customBarcodesPath: value })}
            onBrowse={browseCustomBarcodes}
            placeholder={t("mame.inputPanel.customBarcodes.placeholder")}
            stateLabel={t("mame.inputPanel.customBarcodes.stateLabel")}
            filled={Boolean(rawRunParams.customBarcodesPath)}
            helperText={t("mame.inputPanel.customBarcodes.helperText")}
            helpText={t("mame.inputPanel.customBarcodes.helpText")}
            noPathLabel={noPathLabel}
            readyLabel={readyLabel}
            browseAriaLabel={t("mame.inputPanel.browseFolderAriaLabel", { label: t("mame.inputPanel.customBarcodes.label") })}
          />
          {/* What the workbook contains, read back after a validation. A line of
              text and nothing more: the plate convention is fixed in the code,
              so there is no value here for the operator to choose. */}
          {barcodeAxisCounts && (
            <p className="text-xs text-muted-foreground -mt-2 pl-1">
              {t("mame.inputPanel.customBarcodes.axisCounts", {
                forward: barcodeAxisCounts.forward_count,
                reverse: barcodeAxisCounts.reverse_count,
                wells: barcodeAxisCounts.wells,
              })}
            </p>
          )}
        </>
      )}
      <FileField
        label={t("mame.inputPanel.kuroXlsx.label")}
        value={expectedPath}
        onChange={setExpectedPath}
        onBrowse={browseExpected}
        placeholder={t("mame.inputPanel.kuroXlsx.placeholder")}
        stateLabel={t("mame.inputPanel.kuroXlsx.stateLabel")}
        filled={Boolean(expectedPath)}
        helperText={t("mame.inputPanel.kuroXlsx.helperText")}
        helpText={t("mame.inputPanel.kuroXlsx.helpText")}
        noPathLabel={noPathLabel}
        readyLabel={readyLabel}
        browseAriaLabel={t("mame.inputPanel.browseFolderAriaLabel", { label: t("mame.inputPanel.kuroXlsx.label") })}
      />
      <VariantColumnMapping />
      <FileField
        label={t("mame.inputPanel.referenceFasta.label")}
        value={referencePath}
        onChange={setReferencePath}
        onBrowse={browseReference}
        placeholder={t("mame.inputPanel.referenceFasta.placeholder")}
        stateLabel={t("mame.inputPanel.referenceFasta.stateLabel")}
        filled={Boolean(referencePath)}
        helperText={t("mame.inputPanel.referenceFasta.helperText")}
        helpText={t("mame.inputPanel.referenceFasta.helpText")}
        noPathLabel={noPathLabel}
        readyLabel={readyLabel}
        browseAriaLabel={t("mame.inputPanel.browseFolderAriaLabel", { label: t("mame.inputPanel.referenceFasta.label") })}
      />
      <FileField
        label={t("mame.inputPanel.exportDest.label")}
        value={outputPath}
        onChange={setOutputPath}
        onBrowse={browseOutput}
        placeholder={t("mame.inputPanel.exportDest.placeholder", {
          filename: defaultMameExportFilename({ referencePath, inputDir, verdictCount }),
        })}
        stateLabel={t("mame.inputPanel.exportDest.stateLabel")}
        filled={Boolean(outputPath)}
        helperText={t("mame.inputPanel.exportDest.helperText")}
        helpText={t("mame.inputPanel.exportDest.helpText")}
        noPathLabel={noPathLabel}
        readyLabel={readyLabel}
        browseAriaLabel={t("mame.inputPanel.browseFolderAriaLabel", { label: t("mame.inputPanel.exportDest.label") })}
      />
    </div>
  );
}

