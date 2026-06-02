import { useState, useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { open as openDialog } from "@tauri-apps/plugin-dialog";
import { Plus, X } from "lucide-react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { useEvolveProStore } from "@/store/evolvepro/evolveProStore";
import { EvolveProErrorAlert } from "./EvolveProErrorAlert";
import { readTextHead } from "@/lib/ipc-evolvepro";
import {
  validateRoundCsv,
  validateFasta,
  validateTopN,
  validateOutputDir,
} from "@/lib/evolveProValidation";

interface FormErrors {
  roundFiles?: string;
  wtFasta?: string;
  topN?: string;
  outputDir?: string;
}

export interface EvolveProRunFormProps {
  envName: string;
}

/**
 * EVOLVEpro run input form. Independent module, does not touch the main flow.
 * Uses only shadcn primitives (Card/Button/Input/Label/Progress) and tailwind
 * tokens (text-foreground, bg-background, border-border) to maintain visual
 * continuity with the rest of KUMA.
 */
export function EvolveProRunForm({ envName }: EvolveProRunFormProps) {
  const { t } = useTranslation();
  const startRun = useEvolveProStore((s) => s.startEvolveProRun);
  const cancelRun = useEvolveProStore((s) => s.cancelEvolveProRun);
  const running = useEvolveProStore((s) => s.evolveProRunning);
  const progress = useEvolveProStore((s) => s.evolveProProgress);
  const progressLog = useEvolveProStore((s) => s.evolveProProgressLog);
  const evolveProRunResult = useEvolveProStore((s) => s.evolveProRunResult);
  const error = useEvolveProStore((s) => s.evolveProError);
  const runStartedAt = useEvolveProStore((s) => s.evolveProRunStartedAt);
  const activeEsm2ModelId = useEvolveProStore((s) => s.activeEsm2ModelId);
  const esm2Installed = useEvolveProStore((s) => s.esm2Installed);
  const esm2Recommendation = useEvolveProStore((s) => s.esm2Recommendation);
  const embeddingCacheStatus = useEvolveProStore((s) => s.embeddingCacheStatus);
  const embeddingCacheLoading = useEvolveProStore((s) => s.embeddingCacheLoading);
  const loadEmbeddingCacheStatus = useEvolveProStore((s) => s.loadEmbeddingCacheStatus);
  const roundFiles = useEvolveProStore((s) => s.evolveProRoundFiles);
  const setRoundFiles = useEvolveProStore((s) => s.setEvolveProRoundFiles);
  const wtFasta = useEvolveProStore((s) => s.evolveProWtFasta);
  const setWtFasta = useEvolveProStore((s) => s.setEvolveProWtFasta);
  const wtSequence = useEvolveProStore((s) => s.evolveProWtSequence);
  const setWtSequence = useEvolveProStore((s) => s.setEvolveProWtSequence);
  const outputDir = useEvolveProStore((s) => s.evolveProOutputDir);
  const setOutputDir = useEvolveProStore((s) => s.setEvolveProOutputDir);
  const topN = useEvolveProStore((s) => s.evolveProTopN);
  const setTopN = useEvolveProStore((s) => s.setEvolveProTopN);
  const [errors, setErrors] = useState<FormErrors>({});
  const [elapsedSec, setElapsedSec] = useState(0);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (running && runStartedAt !== null) {
      setElapsedSec(Math.max(0, Math.floor((Date.now() - runStartedAt) / 1000)));
      intervalRef.current = setInterval(() => {
        setElapsedSec(Math.max(0, Math.floor((Date.now() - runStartedAt) / 1000)));
      }, 1000);
    } else {
      setElapsedSec(0);
    }
    return () => {
      if (intervalRef.current !== null) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [running, runStartedAt]);

  function formatElapsed(totalSec: number): string {
    const m = Math.floor(totalSec / 60);
    const s = totalSec % 60;
    return `${m}:${String(s).padStart(2, "0")}`;
  }

  function setError(key: keyof FormErrors, msg: string | undefined) {
    setErrors((prev) => {
      const next = { ...prev };
      if (msg) next[key] = msg;
      else delete next[key];
      return next;
    });
  }

  async function validateRoundFiles(paths: string[]) {
    for (const p of paths) {
      const r = await validateRoundCsv(p);
      if (!r.ok) {
        setError("roundFiles", `${p}: ${r.message}`);
        return;
      }
    }
    setError("roundFiles", undefined);
  }

  async function addRoundFile() {
    const paths = await openDialog({
      multiple: true,
      directory: false,
      filters: [{ name: "Activity table", extensions: ["csv", "xlsx", "xls"] }],
    });
    let nextFiles: string[] | null = null;
    if (typeof paths === "string") {
      nextFiles = [...roundFiles, paths];
    } else if (Array.isArray(paths)) {
      nextFiles = [...roundFiles, ...paths];
    }
    if (nextFiles) {
      setRoundFiles(nextFiles);
      await validateRoundFiles(nextFiles);
    }
  }

  function removeRoundFile(index: number) {
    const next = roundFiles.filter((_, i) => i !== index);
    setRoundFiles(next);
    void validateRoundFiles(next);
  }

  async function pickWtFasta() {
    const path = await openDialog({
      multiple: false,
      directory: false,
      filters: [{ name: "FASTA", extensions: ["fa", "faa", "fasta", "fas"] }],
    });
    if (typeof path === "string") {
      setWtFasta(path);
      const r = await validateFasta(path);
      setError("wtFasta", r.ok ? undefined : r.message);
      if (r.ok) {
        try {
          const text = await readTextHead(path, 64 * 1024);
          const seq = text
            .split(/\r?\n/)
            .filter((l) => !l.startsWith(">") && l.length > 0)
            .join("")
            .replace(/\s/g, "")
            .toUpperCase()
            .replace(/\*+$/, "");
          setWtSequence(seq);
        } catch {
          setWtSequence("");
        }
      } else {
        setWtSequence("");
      }
    }
  }

  async function pickOutputDir() {
    const path = await openDialog({ multiple: false, directory: true });
    if (typeof path === "string") {
      setOutputDir(path);
      // C is validated on submit. Clear any prior error on re-pick.
      setError("outputDir", undefined);
    }
  }

  function handleTopNChange(raw: string) {
    const n = Number(raw);
    setTopN(n);
    const r = validateTopN(raw);
    setError("topN", r.ok ? undefined : r.message);
  }

  useEffect(() => {
    void loadEmbeddingCacheStatus(wtSequence, activeEsm2ModelId ?? "");
  }, [wtSequence, activeEsm2ModelId, loadEmbeddingCacheStatus]);

  const activeEsm2Installed =
    activeEsm2ModelId !== null && esm2Installed[activeEsm2ModelId] === true;

  const activeEsm2Label =
    esm2Recommendation?.models.find((m) => m.model_id === activeEsm2ModelId)?.label ?? null;

  const hasBlockingErrors =
    Boolean(errors.roundFiles) || Boolean(errors.wtFasta) || Boolean(errors.topN);

  const canSubmit =
    !running &&
    roundFiles.length > 0 &&
    wtFasta.length > 0 &&
    outputDir.length > 0 &&
    topN >= 0 &&
    activeEsm2Installed &&
    !hasBlockingErrors;

  async function handleSubmit() {
    if (!activeEsm2ModelId) return;
    const dirCheck = await validateOutputDir(outputDir);
    if (!dirCheck.ok) {
      setError("outputDir", dirCheck.message);
      return;
    }
    setError("outputDir", undefined);
    void startRun({
      input_csv: roundFiles[0] ?? "",
      round_files: roundFiles,
      wt_sequence: "",
      wt_fasta: wtFasta,
      n_rounds: roundFiles.length,
      output_dir: outputDir,
      top_n: topN,
      env_name: envName,
      esm2_model_id: activeEsm2ModelId,
    });
  }

  const handleSubmitClick = () => {
    void handleSubmit();
  };

  // Indeterminate when running but no countable total yet (e.g. ESM-2 embedding stage).
  const isIndeterminate = running && (!progress || progress.total === 0);
  const progressPct =
    progress?.stage === "done"
      ? 100
      : progress && progress.total > 0
        ? Math.min(100, Math.round((progress.current / progress.total) * 100))
        : 0;

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          {t("evolvePro.runForm.title", { defaultValue: "EVOLVEpro Variant Scoring" })}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {error ? <EvolveProErrorAlert error={error} /> : null}

        <div className="space-y-2">
          <Label>
            {t("evolvePro.runForm.roundData", { defaultValue: "Round activity files" })}
          </Label>
          <p className="text-xs text-muted-foreground">
            {t("evolvePro.runForm.roundDataHint", {
              defaultValue:
                "Add completed round tables in order. Round 1 predicts Round 2; Round 1 + Round 2 predicts Round 3.",
            })}
          </p>
          <p className="text-xs text-muted-foreground">
            {t("evolvePro.runForm.roundFileColumns", {
              defaultValue:
                "Required columns: Variant and activity. Variant supports WT, full notation like S29I, or short notation like 29I.",
            })}
          </p>
          <div className="space-y-2">
            {roundFiles.length === 0 ? (
              <div className="rounded-md border border-dashed border-border px-3 py-2 text-sm text-muted-foreground">
                {t("evolvePro.runForm.noRoundFiles", { defaultValue: "No round files added yet." })}
              </div>
            ) : (
              roundFiles.map((file, index) => (
                <div key={`${file}-${index}`} className="flex items-center gap-2 rounded-md border border-border px-3 py-2">
                  <div className="min-w-20 text-sm font-medium">
                    {t("evolvePro.runForm.roundLabel", {
                      round: index + 1,
                      defaultValue: `Round ${index + 1}`,
                    })}
                  </div>
                  <div className="min-w-0 flex-1 truncate text-sm text-muted-foreground">{file}</div>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    onClick={() => removeRoundFile(index)}
                    disabled={running}
                    aria-label={t("evolvePro.runForm.removeRound", { defaultValue: "Remove round file" })}
                  >
                    <X className="h-4 w-4" />
                  </Button>
                </div>
              ))
            )}
          </div>
          <div className="flex items-center justify-between gap-2">
            <Button type="button" variant="outline" onClick={() => void addRoundFile()} disabled={running}>
              <Plus className="mr-2 h-4 w-4" />
              {t("evolvePro.runForm.addRound", { defaultValue: "Add round file" })}
            </Button>
            <div className="text-xs text-muted-foreground">
              {t("evolvePro.runForm.nextPrediction", {
                round: roundFiles.length + 1,
                defaultValue: `Next prediction: Round ${roundFiles.length + 1}`,
              })}
            </div>
          </div>
          {errors.roundFiles ? (
            <p className="text-xs text-destructive">{errors.roundFiles}</p>
          ) : null}
        </div>

        <div className="space-y-2">
          <Label htmlFor="evolvepro-wt-fasta">
            {t("evolvePro.runForm.wtFasta", { defaultValue: "WT FASTA file" })}
          </Label>
          <div className="flex gap-2">
            <Input
              id="evolvepro-wt-fasta"
              type="text"
              readOnly
              value={wtFasta}
              placeholder={t("evolvePro.runForm.wtFastaPlaceholder", {
                defaultValue: "Click Browse to select WT FASTA...",
              })}
              className="min-w-0 flex-1"
            />
            <Button type="button" variant="outline" onClick={() => void pickWtFasta()} disabled={running}>
              {t("evolvePro.runForm.browse", { defaultValue: "Browse" })}
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">
            {t("evolvePro.runForm.wtFastaHint", {
              defaultValue:
                "Used to expand short variants such as 29I into full notation such as S29I.",
            })}
          </p>
          {errors.wtFasta ? (
            <p className="text-xs text-destructive">{errors.wtFasta}</p>
          ) : null}
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="evolvepro-top-n">
              {t("evolvePro.runForm.topN", { defaultValue: "Top N summary rows" })}
            </Label>
            <Input
              id="evolvepro-top-n"
              type="number"
              min={0}
              max={1000}
              value={topN}
              onChange={(e) => handleTopNChange(e.target.value)}
              disabled={running}
            />
            <p className="text-xs text-muted-foreground">
              {t("evolvePro.runForm.topNHint", {
                defaultValue: "0 writes all predictions to the summary file. df_test.csv always contains all unmeasured variants.",
              })}
            </p>
            {errors.topN ? (
              <p className="text-xs text-destructive">{errors.topN}</p>
            ) : null}
          </div>

          <div className="space-y-2 rounded-md border border-border bg-muted/30 px-3 py-2">
            <div className="text-sm font-medium">
              {t("evolvePro.runForm.roundsFixedTitle", { defaultValue: "Cumulative training" })}
            </div>
            <p className="text-xs text-muted-foreground">
              {t("evolvePro.runForm.roundsFixedHint", {
                defaultValue:
                  "The GUI trains from every uploaded round table and predicts candidates for the next round.",
              })}
            </p>
          </div>
        </div>

        <div className="space-y-2">
          <Label htmlFor="evolvepro-output-dir">
            {t("evolvePro.runForm.outputDir", { defaultValue: "Output directory" })}
          </Label>
          <div className="flex gap-2">
            <Input
              id="evolvepro-output-dir"
              type="text"
              readOnly
              value={outputDir}
              placeholder={t("evolvePro.runForm.outputDirPlaceholder", {
                defaultValue: "Click Browse to select…",
              })}
              className="min-w-0 flex-1"
            />
            <Button type="button" variant="outline" onClick={() => void pickOutputDir()} disabled={running}>
              {t("evolvePro.runForm.browse", { defaultValue: "Browse" })}
            </Button>
          </div>
          {errors.outputDir ? (
            <p className="text-xs text-destructive">{errors.outputDir}</p>
          ) : null}
        </div>

        {running || progress ? (
          <div className="space-y-2 rounded-md border border-border bg-muted/30 p-3">
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>
                {progress?.stage
                  ? t(`evolvePro.runForm.stage.${progress.stage}`, { defaultValue: progress.stage })
                  : t("evolvePro.runForm.stage.starting", { defaultValue: "Starting…" })}
              </span>
              <span className="flex items-center gap-2">
                {running ? (
                  <span className="tabular-nums">
                    {t("evolvePro.runForm.elapsed", { defaultValue: "Elapsed" })}{" "}
                    {formatElapsed(elapsedSec)}
                  </span>
                ) : null}
                {!isIndeterminate && progress && progress.total > 0 ? (
                  <span className="tabular-nums">
                    {progress.current}/{progress.total} ({progressPct}%)
                  </span>
                ) : !isIndeterminate ? (
                  <span>{progressPct}%</span>
                ) : null}
              </span>
            </div>
            {isIndeterminate ? (
              <div
                className="relative h-2 w-full overflow-hidden rounded-full bg-secondary"
                role="progressbar"
                aria-label={t("evolvePro.runForm.stage.loading", { defaultValue: "Loading ESM-2 model" })}
                aria-busy="true"
              >
                <div className="absolute inset-y-0 w-1/3 animate-[indeterminate_1.5s_ease-in-out_infinite] rounded-full bg-primary" />
              </div>
            ) : (
              <Progress value={progressPct} />
            )}
            {progress?.message ? (
              <p className="text-xs text-muted-foreground">{progress.message}</p>
            ) : null}
            {progressLog.length > 0 ? (
              <div className="rounded-md border border-border bg-background/60 p-2">
                <div className="mb-1 text-xs font-medium text-foreground">
                  {t("evolvePro.runForm.progressLog", { defaultValue: "Progress log" })}
                </div>
                <ol className="max-h-36 space-y-1 overflow-y-auto text-xs text-muted-foreground">
                  {progressLog.slice(-10).map((line, index) => (
                    <li key={`${index}-${line}`} className="font-mono">
                      {line}
                    </li>
                  ))}
                </ol>
              </div>
            ) : null}
          </div>
        ) : null}

        {evolveProRunResult ? (
          <div className="rounded-md border border-success/40 bg-success/10 p-3 text-sm">
            <div className="font-medium text-foreground">
              {t("evolvePro.runForm.resultTitle", { defaultValue: "Run complete" })}
            </div>
            <div className="mt-1 text-xs text-muted-foreground">
              {t("evolvePro.runForm.outputCsv", { defaultValue: "Output" })}: {evolveProRunResult.output_csv}
            </div>
            <div className="text-xs text-muted-foreground">
              {t("evolvePro.runForm.nPredictions", { defaultValue: "Predictions" })}: {evolveProRunResult.n_predictions}
            </div>
            <div className="text-xs text-muted-foreground">
              {t("evolvePro.runForm.topVariants", { defaultValue: "Top variants" })}: {(evolveProRunResult.top_variants ?? []).length}
            </div>
            {evolveProRunResult.elapsed_sec !== null && evolveProRunResult.elapsed_sec !== undefined ? (
              <div className="text-xs text-muted-foreground">
                {t("evolvePro.runForm.elapsed", { defaultValue: "Elapsed" })}: {evolveProRunResult.elapsed_sec.toFixed(1)}s
              </div>
            ) : null}
          </div>
        ) : null}

        {/* ESM2 active model status */}
        {activeEsm2Label ? (
          <div className="rounded-md border border-primary/30 bg-primary/5 px-3 py-2 text-sm">
            {t("evolvePro.runForm.usingModel", {
              defaultValue: "Using ESM2 model: {{label}}",
              label: activeEsm2Label,
            })}
          </div>
        ) : (
          <div className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
            {t("evolvePro.runForm.selectModelFirst", {
              defaultValue: "Select an installed ESM2 model from the card above",
            })}
          </div>
        )}

        {/* Embedding cache status banner */}
        {embeddingCacheLoading ? (
          <div className="rounded-md border border-border bg-muted/30 px-3 py-2 text-sm text-muted-foreground">
            {t("evolvePro.runForm.cacheChecking", { defaultValue: "Checking embedding cache..." })}
          </div>
        ) : wtSequence && activeEsm2ModelId && embeddingCacheStatus ? (
          embeddingCacheStatus.cached ? (
            <div
              className="rounded-md border border-success/40 bg-success/10 px-3 py-2 text-sm"
              role="status"
              aria-live="polite"
            >
              <span className="font-medium text-foreground">
                {t("evolvePro.runForm.cacheBannerHit", {
                  defaultValue: "Embedding cache available. Fast run expected.",
                })}
              </span>
              <span className="ml-2 text-xs text-muted-foreground">
                {t("evolvePro.runForm.cacheVariants", {
                  defaultValue: "({{n}} variants cached)",
                  n: embeddingCacheStatus.n_variants,
                })}
              </span>
            </div>
          ) : (
            <div
              className="rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-sm"
              role="status"
              aria-live="polite"
            >
              <span className="font-medium text-foreground">
                {t("evolvePro.runForm.cacheBannerMiss", {
                  defaultValue: "No embedding cache. ESM-2 compute required.",
                })}
              </span>
              {embeddingCacheStatus.estimate_seconds !== null &&
              embeddingCacheStatus.estimate_seconds !== undefined ? (
                <span className="ml-2 text-xs text-muted-foreground">
                  {embeddingCacheStatus.estimate_seconds < 60
                    ? t("evolvePro.runForm.cacheEstimateSec", {
                        defaultValue: "Est. {{s}}s ({{basis}})",
                        s: Math.round(embeddingCacheStatus.estimate_seconds),
                        basis:
                          embeddingCacheStatus.estimate_basis === "spec" ? "approx." : "measured",
                      })
                    : t("evolvePro.runForm.cacheEstimateMin", {
                        defaultValue: "Est. ~{{m}} min ({{basis}})",
                        m: Math.round(embeddingCacheStatus.estimate_seconds / 60),
                        basis:
                          embeddingCacheStatus.estimate_basis === "spec" ? "approx." : "measured",
                      })}
                  {" | "}
                  {t("evolvePro.runForm.cacheVariants", {
                    defaultValue: "{{n}} variants",
                    n: embeddingCacheStatus.n_variants,
                  })}
                </span>
              ) : null}
            </div>
          )
        ) : null}

        <div className="flex gap-2">
          <Button type="button" onClick={handleSubmitClick} disabled={!canSubmit}>
            {running
              ? t("evolvePro.runForm.running", { defaultValue: "Running…" })
              : t("evolvePro.runForm.submit", { defaultValue: "Start EVOLVEpro" })}
          </Button>
          {running ? (
            <Button type="button" variant="outline" onClick={() => void cancelRun()}>
              {t("evolvePro.runForm.cancel", { defaultValue: "Cancel" })}
            </Button>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}
