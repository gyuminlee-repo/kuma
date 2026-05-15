import { useState } from "react";
import { useTranslation } from "react-i18next";
import { open as openDialog } from "@tauri-apps/plugin-dialog";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { useAppStore } from "@/store/appStore";
import { EvolveProErrorAlert } from "./EvolveProErrorAlert";

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
  const startRun = useAppStore((s) => s.startEvolveProRun);
  const cancelRun = useAppStore((s) => s.cancelEvolveProRun);
  const running = useAppStore((s) => s.evolveProRunning);
  const progress = useAppStore((s) => s.evolveProProgress);
  const result = useAppStore((s) => s.evolveProResult);
  const error = useAppStore((s) => s.evolveProError);

  const [inputCsv, setInputCsv] = useState<string>("");
  const [wtSequence, setWtSequence] = useState<string>("");
  const [nRounds, setNRounds] = useState<number>(3);
  const [outputDir, setOutputDir] = useState<string>("");
  const [topN, setTopN] = useState<number>(20);

  async function pickInputCsv() {
    const path = await openDialog({
      multiple: false,
      directory: false,
      filters: [{ name: "CSV", extensions: ["csv"] }],
    });
    if (typeof path === "string") setInputCsv(path);
  }

  async function pickOutputDir() {
    const path = await openDialog({ multiple: false, directory: true });
    if (typeof path === "string") setOutputDir(path);
  }

  const canSubmit =
    !running &&
    inputCsv.length > 0 &&
    wtSequence.length > 0 &&
    outputDir.length > 0 &&
    nRounds >= 1 &&
    nRounds <= 10;

  function handleSubmit() {
    void startRun({
      input_csv: inputCsv,
      wt_sequence: wtSequence,
      n_rounds: nRounds,
      output_dir: outputDir,
      top_n: topN,
      env_name: envName,
    });
  }

  const progressPct =
    progress && progress.total > 0
      ? Math.min(100, Math.round((progress.current / progress.total) * 100))
      : running
        ? 5
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
          <Label htmlFor="evolvepro-input-csv">
            {t("evolvePro.runForm.inputCsv", { defaultValue: "Input CSV (variant library)" })}
          </Label>
          <div className="flex gap-2">
            <Input
              id="evolvepro-input-csv"
              type="text"
              readOnly
              value={inputCsv}
              placeholder={t("evolvePro.runForm.inputCsvPlaceholder", {
                defaultValue: "Click Browse to select…",
              })}
              className="min-w-0 flex-1"
            />
            <Button type="button" variant="outline" onClick={() => void pickInputCsv()} disabled={running}>
              {t("evolvePro.runForm.browse", { defaultValue: "Browse" })}
            </Button>
          </div>
        </div>

        <div className="space-y-2">
          <Label htmlFor="evolvepro-wt-sequence">
            {t("evolvePro.runForm.wtSequence", { defaultValue: "WT protein sequence" })}
          </Label>
          <textarea
            id="evolvepro-wt-sequence"
            value={wtSequence}
            onChange={(e) => setWtSequence(e.target.value)}
            disabled={running}
            rows={4}
            maxLength={4000}
            className="w-full rounded-md border border-border bg-background px-3 py-2 font-mono text-xs text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
            placeholder="MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGDGTQDNLSGAEK..."
          />
          <p className="text-xs text-muted-foreground">
            {t("evolvePro.runForm.wtSequenceHint", {
              defaultValue: "Amino acid sequence (1-4000 chars). Used as wild-type reference.",
            })}
          </p>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label htmlFor="evolvepro-n-rounds">
              {t("evolvePro.runForm.nRounds", { defaultValue: "Rounds" })}: {nRounds}
            </Label>
            <input
              id="evolvepro-n-rounds"
              type="range"
              min={1}
              max={10}
              step={1}
              value={nRounds}
              onChange={(e) => setNRounds(Number(e.target.value))}
              disabled={running}
              className="w-full"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="evolvepro-top-n">
              {t("evolvePro.runForm.topN", { defaultValue: "Top N" })}
            </Label>
            <Input
              id="evolvepro-top-n"
              type="number"
              min={0}
              max={1000}
              value={topN}
              onChange={(e) => setTopN(Number(e.target.value))}
              disabled={running}
            />
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
        </div>

        {running || progress ? (
          <div className="space-y-2 rounded-md border border-border bg-muted/30 p-3">
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>
                {progress?.stage
                  ? t(`evolvePro.runForm.stage.${progress.stage}`, { defaultValue: progress.stage })
                  : t("evolvePro.runForm.stage.starting", { defaultValue: "Starting…" })}
              </span>
              <span>{progressPct}%</span>
            </div>
            <Progress value={progressPct} />
            {progress?.message ? (
              <p className="text-xs text-muted-foreground">{progress.message}</p>
            ) : null}
          </div>
        ) : null}

        {result ? (
          <div className="rounded-md border border-success/40 bg-success/10 p-3 text-sm">
            <div className="font-medium text-foreground">
              {t("evolvePro.runForm.resultTitle", { defaultValue: "Run complete" })}
            </div>
            <div className="mt-1 text-xs text-muted-foreground">
              {t("evolvePro.runForm.outputCsv", { defaultValue: "Output" })}: {result.output_csv}
            </div>
            <div className="text-xs text-muted-foreground">
              {t("evolvePro.runForm.topVariants", { defaultValue: "Top variants" })}: {result.top_variants.length}
            </div>
            <div className="text-xs text-muted-foreground">
              {t("evolvePro.runForm.elapsed", { defaultValue: "Elapsed" })}: {result.elapsed_sec.toFixed(1)}s
            </div>
          </div>
        ) : null}

        <div className="flex gap-2">
          <Button type="button" onClick={handleSubmit} disabled={!canSubmit}>
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
