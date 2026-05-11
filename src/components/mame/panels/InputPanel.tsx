import { open } from "@tauri-apps/plugin-dialog";
import { FolderOpen } from "lucide-react";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import type { InputMode } from "@/store/mame/slice-interfaces";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { InlineHelp } from "@/components/ui/InlineHelp";
import { defaultMameExportFilename } from "@/lib/filename";

const INPUT_DIR_CONFIG: Record<
  InputMode,
  { label: string; helperText: string; placeholder: string }
> = {
  consensus: {
    label: "Amplicon consensus directory",
    helperText: "Folder containing *-consensus.fasta files (amplicon mode)",
    placeholder: "Choose a directory path",
  },
  sorted_barcode: {
    label: "Sorted barcode directory",
    helperText: "Folder containing NB01/, NB02/, … subdirectories with consensus FASTA ({R}_{F}.fasta)",
    placeholder: "Choose a directory path",
  },
  raw_run: {
    label: "MinKNOW run folder",
    helperText: "Folder containing fastq_pass/ subtree from MinKNOW; Run will sort barcodes before analysis",
    placeholder: "Choose a run folder path",
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
  const inputDir = useMameAppStore((s) => s.inputDir);
  const inputMode = useMameAppStore((s) => s.inputMode);
  const expectedPath = useMameAppStore((s) => s.expectedPath);
  const referencePath = useMameAppStore((s) => s.referencePath);
  const outputPath = useMameAppStore((s) => s.outputPath);
  const rawRunParams = useMameAppStore((s) => s.rawRunParams);
  const verdictCount = useMameAppStore((s) => s.verdicts.length);
  const setInputDir = useMameAppStore((s) => s.setInputDir);
  const setExpectedPath = useMameAppStore((s) => s.setExpectedPath);
  const setReferencePath = useMameAppStore((s) => s.setReferencePath);
  const setOutputPath = useMameAppStore((s) => s.setOutputPath);
  const setParams = useMameAppStore((s) => s.setParams);

  function updateRaw(partial: Partial<typeof rawRunParams>) {
    setParams({ rawRunParams: partial });
  }

  function joinPath(dir: string, filename: string): string {
    const separator = dir.includes("\\") ? "\\" : "/";
    return `${dir.replace(/[\\/]+$/, "")}${separator}${filename}`;
  }

  function currentOutputFilename(): string {
    const current = getPathPreview(outputPath);
    return current.toLowerCase().endsWith(".xlsx")
      ? current
      : defaultMameExportFilename({ referencePath, inputDir, verdictCount });
  }

  async function browseDirectory() {
    const selected = toSinglePath(await open({ directory: true }));
    if (selected) setInputDir(selected);
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
        filters: [{ name: "FASTA", extensions: ["fasta", "fa", "fna"] }],
      }),
    );
    if (selected) setReferencePath(selected);
  }

  async function browseOutput() {
    const selected = toSinglePath(await open({ directory: true, title: "Select export folder" }));
    if (selected) setOutputPath(joinPath(selected, currentOutputFilename()));
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

  async function browseSequencingSummary() {
    const selected = toSinglePath(
      await open({
        directory: false,
        filters: [{ name: "Sequencing summary", extensions: ["txt", "tsv", "csv"] }],
        title: "Select sequencing summary file",
      }),
    );
    if (selected) updateRaw({ sequencingSummaryPath: selected });
  }

  return (
    <div className="rounded-lg border border-border bg-background p-4 space-y-4">
      <header>
        <h3 className="text-sm font-semibold text-foreground">Input files</h3>
        <p className="mt-1 text-xs text-muted-foreground">
          Primary run inputs and output location.
        </p>
      </header>

      <FileField
        label={INPUT_DIR_CONFIG[inputMode].label}
        value={inputDir}
        onChange={setInputDir}
        onBrowse={browseDirectory}
        placeholder={INPUT_DIR_CONFIG[inputMode].placeholder}
        stateLabel="Required"
        filled={Boolean(inputDir)}
        helperText={INPUT_DIR_CONFIG[inputMode].helperText}
        helpText={INPUT_DIR_CONFIG[inputMode].helperText}
      />
      {inputMode === "raw_run" && (
        <>
          <FileField
            label="Custom Barcodes (xlsx or csv)"
            value={rawRunParams.customBarcodesPath}
            onChange={(value) => updateRaw({ customBarcodesPath: value })}
            onBrowse={browseCustomBarcodes}
            placeholder=".xlsx / .csv file path"
            stateLabel="Required"
            filled={Boolean(rawRunParams.customBarcodesPath)}
            helperText="Combinatorial barcode definition used before analysis"
            helpText="Raw MinKNOW run mode uses this file to assign reads to per-well FASTA outputs before analysis."
          />
          <FileField
            label="Sequencing Summary (optional)"
            value={rawRunParams.sequencingSummaryPath}
            onChange={(value) => updateRaw({ sequencingSummaryPath: value })}
            onBrowse={browseSequencingSummary}
            placeholder=".txt / .tsv / .csv file path"
            stateLabel="Optional"
            filled={Boolean(rawRunParams.sequencingSummaryPath)}
            helperText="Optional MinKNOW metadata for qscore, length, and barcode score filters"
            helpText="When present, MAME can filter reads by MinKNOW metadata before writing per-well FASTA outputs."
          />
        </>
      )}
      <FileField
        label="KURO xlsx"
        value={expectedPath}
        onChange={setExpectedPath}
        onBrowse={browseExpected}
        placeholder=".xlsx file path"
        stateLabel="Required"
        filled={Boolean(expectedPath)}
        helperText="expected_mutations sheet from KURO"
        helpText="KURO에서 export한 expected_mutations .xlsx 파일입니다. MAME는 이 파일의 기대 변이와 NGS consensus 결과를 비교합니다."
      />
      <FileField
        label="Reference FASTA"
        value={referencePath}
        onChange={setReferencePath}
        onBrowse={browseReference}
        placeholder=".fasta / .fa file path"
        stateLabel="Required"
        filled={Boolean(referencePath)}
        helperText="Reference sequence used for variant calling against consensus"
        helpText="Variant calling 기준이 되는 reference FASTA입니다. KURO 설계에 사용한 동일 reference를 쓰는 것이 안전합니다."
      />
      <FileField
        label="Export destination folder"
        value={outputPath}
        onChange={setOutputPath}
        onBrowse={browseOutput}
        placeholder={`Choose a folder; ${defaultMameExportFilename({ referencePath, inputDir, verdictCount })} will be created`}
        stateLabel="Save to"
        filled={Boolean(outputPath)}
        helperText="Analysis report will use a KURO-style rule-based .xlsx filename"
        helpText="분석 결과 Excel을 저장할 폴더입니다. 파일명은 KURO와 같은 규칙으로 날짜, reference/input 토큰, MAME target, 결과 개수 토큰을 조합해 생성합니다."
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
          {filled ? "Ready" : stateLabel}
        </span>
      </div>
      <div className="flex gap-1.5">
        <Input
          id={inputId}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className="h-8 flex-1 text-xs font-mono"
          aria-label={label}
        />
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => void onBrowse()}
          className="h-8 gap-1 px-2"
          aria-label={`Browse ${label}`}
        >
          <FolderOpen size={12} aria-hidden="true" />
        </Button>
      </div>
      {helperText && (
        <p className="text-caption text-muted-foreground/90">{helperText}</p>
      )}
      <p className="truncate text-caption text-muted-foreground" title={value || undefined}>
        {filled ? preview : "No path selected"}
      </p>
    </div>
  );
}
