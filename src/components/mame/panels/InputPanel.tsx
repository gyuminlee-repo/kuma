import { open } from "@tauri-apps/plugin-dialog";
import { FolderOpen } from "lucide-react";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

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
  const expectedPath = useMameAppStore((s) => s.expectedPath);
  const referencePath = useMameAppStore((s) => s.referencePath);
  const outputPath = useMameAppStore((s) => s.outputPath);
  const setInputDir = useMameAppStore((s) => s.setInputDir);
  const setExpectedPath = useMameAppStore((s) => s.setExpectedPath);
  const setReferencePath = useMameAppStore((s) => s.setReferencePath);
  const setOutputPath = useMameAppStore((s) => s.setOutputPath);

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
    const selected = toSinglePath(
      await open({ directory: false, filters: [{ name: "Excel", extensions: ["xlsx"] }] }),
    );
    if (selected) setOutputPath(selected);
  }

  return (
    <div className="rounded-lg border border-border bg-background p-4 space-y-4">
      <header>
        <h3 className="text-sm font-semibold text-foreground">Input files</h3>
        <p className="mt-1 text-xs text-muted-foreground">
          4 required paths for the analysis run.
        </p>
      </header>

      <FileField
        label="Consensus FASTA directory"
        value={inputDir}
        onChange={setInputDir}
        onBrowse={browseDirectory}
        placeholder="Choose a directory path"
        stateLabel="Required"
        filled={Boolean(inputDir)}
      />
      <FileField
        label="KURO xlsx"
        value={expectedPath}
        onChange={setExpectedPath}
        onBrowse={browseExpected}
        placeholder=".xlsx file path"
        stateLabel="Required"
        filled={Boolean(expectedPath)}
        helperText="expected_mutations sheet from KURO"
      />
      <FileField
        label="Reference FASTA"
        value={referencePath}
        onChange={setReferencePath}
        onBrowse={browseReference}
        placeholder=".fasta / .fa file path"
        stateLabel="Required"
        filled={Boolean(referencePath)}
      />
      <FileField
        label="Output xlsx"
        value={outputPath}
        onChange={setOutputPath}
        onBrowse={browseOutput}
        placeholder="Output save path (.xlsx)"
        stateLabel="Output"
        filled={Boolean(outputPath)}
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
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  onBrowse: () => Promise<void>;
  placeholder?: string;
  stateLabel: string;
  filled: boolean;
  helperText?: string;
}) {
  const inputId = `file-field-${label.replace(/\s+/g, "-").toLowerCase()}`;
  const preview = getPathPreview(value);

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-3">
        <Label htmlFor={inputId} className="text-caption font-medium uppercase tracking-wide text-muted-foreground">
          {label}
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
