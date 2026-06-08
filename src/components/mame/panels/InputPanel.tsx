import { useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { FolderOpen, LayoutGrid, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import { useKumaProject } from "@/state/projectContext";
import { applyMameAutoDetect } from "@/hooks/useAutosaveHydration";
import { detectFromInputDir } from "@/lib/mame/detectProjectFiles";
import type { InputMode } from "@/store/mame/slice-interfaces";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { InlineHelp } from "@/components/ui/InlineHelp";
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

function getPathPreview(value: string): string {
  if (!value) return "";
  const parts = value.split(/[/\\]/);
  return parts[parts.length - 1] || value;
}

export function InputPanel() {
  const { t } = useTranslation();
  const inputDir = useMameAppStore((s) => s.inputDir);
  const inputMode = useMameAppStore((s) => s.inputMode);
  const expectedPath = useMameAppStore((s) => s.expectedPath);
  const referencePath = useMameAppStore((s) => s.referencePath);
  const outputPath = useMameAppStore((s) => s.outputPath);
  const sampleMapPath = useMameAppStore((s) => s.sampleMapPath);
  const rawRunParams = useMameAppStore((s) => s.rawRunParams);
  const verdictCount = useMameAppStore((s) => s.verdicts.length);
  const setInputDir = useMameAppStore((s) => s.setInputDir);
  const setExpectedPath = useMameAppStore((s) => s.setExpectedPath);
  const setReferencePath = useMameAppStore((s) => s.setReferencePath);
  const setOutputPath = useMameAppStore((s) => s.setOutputPath);
  const setSampleMapPath = useMameAppStore((s) => s.setSampleMapPath);
  const setParams = useMameAppStore((s) => s.setParams);
  const wellLayout = useMameAppStore((s) => s.wellLayout);
  const buildWellLayout = useMameAppStore((s) => s.buildWellLayout);

  const project = useKumaProject();
  const [isDetecting, setIsDetecting] = useState(false);
  const [isAutoFilling, setIsAutoFilling] = useState(false);
  const [isBuildingLayout, setIsBuildingLayout] = useState(false);

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
        filled.push("expected");
      }
      if (!store.sampleMapPath && detectedPaths.sampleMapPath) {
        store.setSampleMapPath(detectedPaths.sampleMapPath);
        filled.push("sample map");
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

  async function handleBuildWellLayout() {
    if (isBuildingLayout) return;
    setIsBuildingLayout(true);
    try {
      await buildWellLayout();
    } finally {
      setIsBuildingLayout(false);
    }
  }

  async function browseExpected() {
    const selected = toSinglePath(
      await open({ directory: false, filters: [{ name: "Excel", extensions: ["xlsx"] }] }),
    );
    if (selected) setExpectedPath(selected);
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

  async function browseSampleMap() {
    const selected = toSinglePath(
      await open({
        directory: false,
        filters: [{ name: "Sample map", extensions: ["xlsx"] }],
        title: "Select sample map (mutants well layout)",
      }),
    );
    if (selected) setSampleMapPath(selected);
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
          <FileField
            label={t("mame.inputPanel.sampleMap.label")}
            value={sampleMapPath}
            onChange={setSampleMapPath}
            onBrowse={browseSampleMap}
            placeholder={t("mame.inputPanel.sampleMap.placeholder")}
            stateLabel={t("mame.inputPanel.sampleMap.stateLabel")}
            filled={Boolean(sampleMapPath)}
            helperText={t("mame.inputPanel.sampleMap.helperText")}
            helpText={t("mame.inputPanel.sampleMap.helpText")}
            noPathLabel={noPathLabel}
            readyLabel={readyLabel}
            browseAriaLabel={t("mame.inputPanel.browseFolderAriaLabel", { label: t("mame.inputPanel.sampleMap.label") })}
          />
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
      {expectedPath && (
        <div className="flex items-center gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => void handleBuildWellLayout()}
            disabled={isBuildingLayout}
            aria-label={t("mame.inputPanel.buildWellLayout.ariaLabel")}
            className="h-8 gap-1.5 px-3 text-xs"
          >
            <LayoutGrid size={12} aria-hidden="true" />
            {isBuildingLayout
              ? t("mame.inputPanel.buildWellLayout.building")
              : t("mame.inputPanel.buildWellLayout.button")}
          </Button>
          {wellLayout !== null && (
            <span className="rounded-full bg-primary/10 px-2 py-0.5 text-caption font-medium text-primary">
              {t("mame.inputPanel.buildWellLayout.confirmed", {
                count: Object.keys(wellLayout).length,
              })}
            </span>
          )}
        </div>
      )}
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

function FileField({
  label,
  value,
  onChange,
  onBrowse,
  placeholder,
  stateLabel,
  filled,
  helperText,
  helpText,
  noPathLabel,
  readyLabel,
  browseAriaLabel,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  onBrowse: () => Promise<void>;
  placeholder?: string;
  stateLabel: string;
  filled: boolean;
  helperText?: string;
  helpText?: string;
  noPathLabel: string;
  readyLabel: string;
  browseAriaLabel?: string;
}) {
  const inputId = `file-field-${label.replace(/\s+/g, "-").toLowerCase()}`;
  const preview = getPathPreview(value);

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-3">
        <Label htmlFor={inputId} className="text-caption font-medium uppercase tracking-wide text-muted-foreground">
          <span className="inline-flex items-center gap-1.5">
            {label}
            {helpText && <InlineHelp text={helpText} />}
          </span>
        </Label>
        <span
          className={`rounded-full px-2 py-0.5 text-caption font-medium ${
            filled
              ? "bg-primary/10 text-primary"
              : "bg-muted text-muted-foreground"
          }`}
        >
          {filled ? readyLabel : stateLabel}
        </span>
      </div>
      <div className="flex gap-1.5">
        <Input
          id={inputId}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className="h-8 flex-1 min-w-0 text-xs font-mono"
          aria-label={label}
        />
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => void onBrowse()}
          className="h-8 gap-1 px-2"
          aria-label={browseAriaLabel ?? label}
        >
          <FolderOpen size={12} aria-hidden="true" />
        </Button>
      </div>
      {helperText && (
        <p className="text-caption text-muted-foreground/90">{helperText}</p>
      )}
      <p className="truncate text-caption text-muted-foreground" title={value || undefined}>
        {filled ? preview : noPathLabel}
      </p>
    </div>
  );
}
