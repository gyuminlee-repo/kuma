/**
 * BarcodeSetupPanel: MAME Phase 1 (Barcode Setup) 입력 패널.
 *
 * 사용자가 CDS FASTA, 바코드 시드 xlsx, 프라이머 파라미터를 입력하고
 * generate_mame_package RPC를 호출해 design/ 폴더에 패키지를 생성한다.
 *
 * 상태: 컴포넌트 local useState (마지막 값은 localStorage `kuma:mame:barcodeSetup`에 영속화)
 */

import { useState, useCallback } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { CheckCircle2, FolderOpen, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { useKumaProject } from "@/state/projectContext";
import { rpc } from "@/lib/ipc";
import { revealInOSFolder } from "@/lib/openFolder";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { GenerateMamePackageParams, MamePackageResult } from "@/types/mame/barcode_package";

// ─── localStorage 영속화 ─────────────────────────────────────────────────────

const STORAGE_KEY = "kuma:mame:barcodeSetup";

interface SetupFormState {
  fastaPath: string;
  geneStart: string;
  geneEnd: string;
  geneName: string;
  polymerase: "Q5" | "Taq" | "Phusion";
  flankMin: string;
  flankMax: string;
  bindingMinLen: string;
  bindingMaxLen: string;
  tmMin: string;
  tmMax: string;
  requireGcClamp: boolean;
  barcodeSeedsPath: string;
}

const DEFAULT_STATE: SetupFormState = {
  fastaPath: "",
  geneStart: "",
  geneEnd: "",
  geneName: "ispS",
  polymerase: "Q5",
  flankMin: "100",
  flankMax: "400",
  bindingMinLen: "18",
  bindingMaxLen: "35",
  tmMin: "55.0",
  tmMax: "68.0",
  requireGcClamp: true,
  barcodeSeedsPath: "",
};

function loadFromStorage(): SetupFormState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_STATE;
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null) return DEFAULT_STATE;
    // polymerase 값 검증
    const p = parsed as Record<string, unknown>;
    const poly =
      p.polymerase === "Q5" || p.polymerase === "Taq" || p.polymerase === "Phusion"
        ? p.polymerase
        : DEFAULT_STATE.polymerase;
    return {
      fastaPath: typeof p.fastaPath === "string" ? p.fastaPath : DEFAULT_STATE.fastaPath,
      geneStart: typeof p.geneStart === "string" ? p.geneStart : DEFAULT_STATE.geneStart,
      geneEnd: typeof p.geneEnd === "string" ? p.geneEnd : DEFAULT_STATE.geneEnd,
      geneName: typeof p.geneName === "string" ? p.geneName : DEFAULT_STATE.geneName,
      polymerase: poly,
      flankMin: typeof p.flankMin === "string" ? p.flankMin : DEFAULT_STATE.flankMin,
      flankMax: typeof p.flankMax === "string" ? p.flankMax : DEFAULT_STATE.flankMax,
      bindingMinLen:
        typeof p.bindingMinLen === "string" ? p.bindingMinLen : DEFAULT_STATE.bindingMinLen,
      bindingMaxLen:
        typeof p.bindingMaxLen === "string" ? p.bindingMaxLen : DEFAULT_STATE.bindingMaxLen,
      tmMin: typeof p.tmMin === "string" ? p.tmMin : DEFAULT_STATE.tmMin,
      tmMax: typeof p.tmMax === "string" ? p.tmMax : DEFAULT_STATE.tmMax,
      requireGcClamp:
        typeof p.requireGcClamp === "boolean"
          ? p.requireGcClamp
          : DEFAULT_STATE.requireGcClamp,
      barcodeSeedsPath:
        typeof p.barcodeSeedsPath === "string"
          ? p.barcodeSeedsPath
          : DEFAULT_STATE.barcodeSeedsPath,
    };
  } catch {
    return DEFAULT_STATE;
  }
}

function saveToStorage(state: SetupFormState): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    // 저장 실패 시 무시
  }
}

// ─── 헬퍼 ────────────────────────────────────────────────────────────────────

function getFilename(p: string): string {
  if (!p) return "";
  const parts = p.split(/[/\\]/);
  return parts[parts.length - 1] ?? p;
}

function toSinglePath(result: string | string[] | null): string | null {
  return typeof result === "string" ? result : null;
}

// ─── 메인 컴포넌트 ────────────────────────────────────────────────────────────

export function BarcodeSetupPanel() {
  const project = useKumaProject();
  const [form, setFormRaw] = useState<SetupFormState>(() => loadFromStorage());
  const [isGenerating, setIsGenerating] = useState(false);
  const [result, setResult] = useState<MamePackageResult | null>(null);

  function setForm(partial: Partial<SetupFormState>) {
    setFormRaw((prev) => {
      const next = { ...prev, ...partial };
      saveToStorage(next);
      return next;
    });
  }

  // ─── 파일 브라우저 ───────────────────────────────────────────────────────

  const browseFasta = useCallback(async () => {
    const selected = toSinglePath(
      await open({
        directory: false,
        filters: [{ name: "FASTA", extensions: ["fa", "fasta", "fna"] }],
        title: "Select CDS FASTA file",
      }),
    );
    if (selected) setForm({ fastaPath: selected });
  }, []);

  const browseBarcodeSeeds = useCallback(async () => {
    const selected = toSinglePath(
      await open({
        directory: false,
        filters: [{ name: "Excel", extensions: ["xlsx"] }],
        title: "Select barcode seeds xlsx",
      }),
    );
    if (selected) setForm({ barcodeSeedsPath: selected });
  }, []);

  // ─── 검증 ────────────────────────────────────────────────────────────────

  const geneStartNum = parseInt(form.geneStart, 10);
  const geneEndNum = parseInt(form.geneEnd, 10);
  const isStartValid = form.geneStart !== "" && !isNaN(geneStartNum) && geneStartNum >= 0;
  const isEndValid = form.geneEnd !== "" && !isNaN(geneEndNum) && geneEndNum >= 1;
  const isRangeValid = isStartValid && isEndValid && geneEndNum > geneStartNum;

  const isFormReady =
    Boolean(form.fastaPath) &&
    Boolean(form.barcodeSeedsPath) &&
    isStartValid &&
    isEndValid &&
    isRangeValid;

  const canGenerate = isFormReady && Boolean(project?.path) && !isGenerating;

  // ─── RPC 호출 ─────────────────────────────────────────────────────────────

  async function handleGenerate() {
    if (!project?.path) return;
    if (!isRangeValid) {
      toast.error("gene_end must be greater than gene_start");
      return;
    }

    const destDir = `${project.path}/design`;
    setIsGenerating(true);
    setResult(null);

    function optInt(s: string): number | undefined {
      const n = parseInt(s, 10);
      return Number.isFinite(n) ? n : undefined;
    }
    function optFloat(s: string): number | undefined {
      const n = parseFloat(s);
      return Number.isFinite(n) ? n : undefined;
    }

    const params: GenerateMamePackageParams = {
      fasta_path: form.fastaPath,
      gene_start: geneStartNum,
      gene_end: geneEndNum,
      barcode_seeds_path: form.barcodeSeedsPath,
      output_dir: destDir,
      project_root: project.path,
      gene_name: form.geneName || undefined,
      polymerase: form.polymerase,
      flank_min: optInt(form.flankMin),
      flank_max: optInt(form.flankMax),
      binding_min_len: optInt(form.bindingMinLen),
      binding_max_len: optInt(form.bindingMaxLen),
      tm_min: optFloat(form.tmMin),
      tm_max: optFloat(form.tmMax),
      require_gc_clamp: form.requireGcClamp,
    };

    try {
      // generate_mame_package는 프라이머 설계 작업으로 시간이 걸릴 수 있다.
      const res = await rpc<MamePackageResult>("mame", "generate_mame_package", params);
      setResult(res);
      toast.success("Barcode package generated", {
        description: "Files saved to design/",
        duration: 4000,
      });
    } catch (err) {
      toast.error("Generation failed", {
        description: String(err),
        duration: 6000,
      });
    } finally {
      setIsGenerating(false);
    }
  }

  // ─── 렌더링 ──────────────────────────────────────────────────────────────

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-2xl space-y-6 p-4">
        <header>
          <h2 className="text-base font-semibold text-foreground">Barcode Package Setup</h2>
          <p className="mt-1 text-xs text-muted-foreground">
            CDS FASTA와 바코드 시드 파일로 MAME 바코드 패키지를 생성합니다.
          </p>
        </header>

        {/* 섹션 1: 입력 파일 */}
        <section aria-labelledby="section-files">
          <h3 id="section-files" className="mb-3 text-sm font-medium text-foreground">
            Input files
          </h3>
          <div className="space-y-4">
            <FilePickerField
              id="fasta-path"
              label="CDS FASTA"
              stateLabel="Required"
              filled={Boolean(form.fastaPath)}
              value={form.fastaPath}
              onChange={(v) => setForm({ fastaPath: v })}
              onBrowse={browseFasta}
              placeholder=".fa / .fasta / .fna file path"
              helperText="기준 CDS FASTA 파일입니다. 유전자 좌표(gene_start, gene_end)는 이 서열 내 0-based 인덱스입니다."
            />

            <FilePickerField
              id="barcode-seeds"
              label="Barcode Seeds xlsx"
              stateLabel="Required"
              filled={Boolean(form.barcodeSeedsPath)}
              value={form.barcodeSeedsPath}
              onChange={(v) => setForm({ barcodeSeedsPath: v })}
              onBrowse={browseBarcodeSeeds}
              placeholder=".xlsx file path"
              helperText="fwd_1..12, rev_1..8 시드 서열이 담긴 xlsx 파일입니다."
            />
          </div>
        </section>

        {/* 섹션 2: 유전자 좌표 */}
        <section aria-labelledby="section-coords">
          <h3 id="section-coords" className="mb-3 text-sm font-medium text-foreground">
            Gene coordinates
          </h3>
          <div className="grid grid-cols-2 gap-3">
            <NumberField
              id="gene-start"
              label="gene_start"
              value={form.geneStart}
              onChange={(v) => setForm({ geneStart: v })}
              min={0}
              step={1}
              placeholder="0"
              helperText="0-based inclusive"
              hasError={form.geneStart !== "" && (!isStartValid || !isRangeValid)}
            />
            <NumberField
              id="gene-end"
              label="gene_end"
              value={form.geneEnd}
              onChange={(v) => setForm({ geneEnd: v })}
              min={1}
              step={1}
              placeholder="e.g. 534"
              helperText="0-based exclusive"
              hasError={form.geneEnd !== "" && (!isEndValid || !isRangeValid)}
            />
          </div>
          {form.geneStart !== "" && form.geneEnd !== "" && !isRangeValid && (
            <p role="alert" className="mt-1 text-xs text-destructive">
              gene_end must be greater than gene_start.
            </p>
          )}
        </section>

        {/* 섹션 3: 프로젝트 메타 */}
        <section aria-labelledby="section-meta">
          <h3 id="section-meta" className="mb-3 text-sm font-medium text-foreground">
            Project metadata
          </h3>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="gene-name" className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Gene name
              </Label>
              <Input
                id="gene-name"
                value={form.geneName}
                onChange={(e) => setForm({ geneName: e.target.value })}
                placeholder="ispS"
                className="h-8 text-xs font-mono"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="polymerase" className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Polymerase
              </Label>
              <Select
                value={form.polymerase}
                onValueChange={(v) =>
                  setForm({ polymerase: v as "Q5" | "Taq" | "Phusion" })
                }
              >
                <SelectTrigger id="polymerase" className="h-8 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="Q5">Q5</SelectItem>
                  <SelectItem value="Taq">Taq</SelectItem>
                  <SelectItem value="Phusion">Phusion</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </section>

        {/* 섹션 4: 플랭크 파라미터 */}
        <section aria-labelledby="section-flank">
          <h3 id="section-flank" className="mb-3 text-sm font-medium text-foreground">
            Flank parameters
          </h3>
          <div className="grid grid-cols-2 gap-3">
            <NumberField
              id="flank-min"
              label="flank_min (nt)"
              value={form.flankMin}
              onChange={(v) => setForm({ flankMin: v })}
              min={0}
              step={1}
              placeholder="100"
            />
            <NumberField
              id="flank-max"
              label="flank_max (nt)"
              value={form.flankMax}
              onChange={(v) => setForm({ flankMax: v })}
              min={1}
              step={1}
              placeholder="400"
            />
          </div>
        </section>

        {/* 섹션 5: 바인딩 파라미터 */}
        <section aria-labelledby="section-binding">
          <h3 id="section-binding" className="mb-3 text-sm font-medium text-foreground">
            Binding parameters
          </h3>
          <div className="grid grid-cols-2 gap-3">
            <NumberField
              id="binding-min-len"
              label="binding_min_len (nt)"
              value={form.bindingMinLen}
              onChange={(v) => setForm({ bindingMinLen: v })}
              min={1}
              step={1}
              placeholder="18"
            />
            <NumberField
              id="binding-max-len"
              label="binding_max_len (nt)"
              value={form.bindingMaxLen}
              onChange={(v) => setForm({ bindingMaxLen: v })}
              min={1}
              step={1}
              placeholder="35"
            />
            <NumberField
              id="tm-min"
              label="Tm min (degC)"
              value={form.tmMin}
              onChange={(v) => setForm({ tmMin: v })}
              min={0}
              step={0.5}
              placeholder="55.0"
            />
            <NumberField
              id="tm-max"
              label="Tm max (degC)"
              value={form.tmMax}
              onChange={(v) => setForm({ tmMax: v })}
              min={0}
              step={0.5}
              placeholder="68.0"
            />
          </div>

          <div className="mt-3 flex items-center gap-2">
            <input
              type="checkbox"
              id="require-gc-clamp"
              checked={form.requireGcClamp}
              onChange={(e) => setForm({ requireGcClamp: e.target.checked })}
              className="h-4 w-4 cursor-pointer accent-primary"
              aria-label="Require GC clamp on 3-prime end"
            />
            <Label
              htmlFor="require-gc-clamp"
              className="cursor-pointer text-sm text-foreground"
            >
              Require GC clamp (3-prime end)
            </Label>
          </div>
        </section>

        {/* 프로젝트 없음 안내 */}
        {!project?.path && (
          <p role="status" className="rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-400">
            프로젝트를 열어야 패키지를 생성할 수 있습니다. File menu에서 Open Project를 선택하세요.
          </p>
        )}

        {/* 생성 버튼 */}
        <Button
          type="button"
          className="w-full"
          disabled={!canGenerate}
          onClick={() => void handleGenerate()}
          aria-busy={isGenerating}
        >
          {isGenerating ? (
            <>
              <Loader2 size={14} className="mr-2 animate-spin" aria-hidden="true" />
              Generating...
            </>
          ) : (
            "Generate Barcode Package"
          )}
        </Button>

        {/* 출력 섹션 */}
        {result && (
          <section aria-labelledby="section-output" aria-live="polite">
            <h3 id="section-output" className="mb-3 text-sm font-medium text-foreground">
              Generated files
            </h3>
            <div className="rounded-md border border-border bg-muted/30 p-3 space-y-2">
              {(
                [
                  { label: "Barcodes xlsx", path: result.barcodes_xlsx },
                  { label: "Amplicon FASTA", path: result.amplicon_fa },
                  { label: "Sample map template", path: result.sample_map_template },
                  { label: "Context JSON", path: result.context_json },
                ] as const
              ).map(({ label, path }) => (
                <div key={label} className="flex items-start gap-2">
                  <CheckCircle2
                    size={14}
                    className="mt-0.5 shrink-0 text-green-600 dark:text-green-400"
                    aria-hidden="true"
                  />
                  <div className="min-w-0">
                    <p className="text-xs font-medium text-foreground">{label}</p>
                    <p
                      className="truncate font-mono text-xs text-muted-foreground"
                      title={path}
                    >
                      {getFilename(path)}
                    </p>
                  </div>
                </div>
              ))}
            </div>

            {result.warnings.length > 0 && (
              <div
                role="status"
                aria-label="Warnings"
                className="mt-3 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 space-y-1"
              >
                <p className="text-xs font-semibold text-amber-700 dark:text-amber-400">
                  Warnings
                </p>
                {result.warnings.map((w, i) => (
                  <p key={i} className="text-xs text-amber-700 dark:text-amber-400">
                    {w}
                  </p>
                ))}
              </div>
            )}

            <Button
              type="button"
              variant="outline"
              size="sm"
              className="mt-3"
              onClick={() =>
                void revealInOSFolder(result.barcodes_xlsx).catch((e) =>
                  toast.error(String(e)),
                )
              }
            >
              <FolderOpen size={12} className="mr-1.5" aria-hidden="true" />
              Open folder
            </Button>
          </section>
        )}
      </div>
    </div>
  );
}

// ─── 서브 컴포넌트 ────────────────────────────────────────────────────────────

function FilePickerField({
  id,
  label,
  stateLabel,
  filled,
  value,
  onChange,
  onBrowse,
  placeholder,
  helperText,
}: {
  id: string;
  label: string;
  stateLabel: string;
  filled: boolean;
  value: string;
  onChange: (v: string) => void;
  onBrowse: () => Promise<void>;
  placeholder?: string;
  helperText?: string;
}) {
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
          {filled ? "Ready" : stateLabel}
        </span>
      </div>
      <div className="flex gap-1.5">
        <Input
          id={id}
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
          aria-label={`Browse ${label}`}
        >
          <FolderOpen size={12} aria-hidden="true" />
        </Button>
      </div>
      {helperText && <p className="text-xs text-muted-foreground/90">{helperText}</p>}
      <p className="truncate text-xs text-muted-foreground" title={value || undefined}>
        {filled ? preview : "No path selected"}
      </p>
    </div>
  );
}

function NumberField({
  id,
  label,
  value,
  onChange,
  min,
  step,
  placeholder,
  helperText,
  hasError = false,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
  min?: number;
  step?: number;
  placeholder?: string;
  helperText?: string;
  hasError?: boolean;
}) {
  return (
    <div className="space-y-1.5">
      <Label
        htmlFor={id}
        className="text-xs font-medium uppercase tracking-wide text-muted-foreground"
      >
        {label}
      </Label>
      <Input
        id={id}
        type="number"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        min={min}
        step={step}
        placeholder={placeholder}
        className={`h-8 text-xs font-mono ${hasError ? "border-destructive focus-visible:ring-destructive" : ""}`}
        aria-label={label}
        aria-invalid={hasError}
      />
      {helperText && <p className="text-xs text-muted-foreground/90">{helperText}</p>}
    </div>
  );
}
