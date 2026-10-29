/**
 * Step 4.1 positive clone JANUS mapping.
 *
 * After the round-1 GC screen, the clones above wild-type are moved from the
 * final cell stock (96 PCR plate) into a 96 deep well plate (LB + Km). This
 * section lists every measured clone of the screen as a checkbox, starts with
 * the above-WT ones checked (the sidecar decides which, with the rule the
 * build itself uses), lets the operator drop or add clones, and writes the
 * eight column JANUS worklist on an explicit export.
 *
 * It is a side section: nothing here gates the EVOLVEpro build or step 4
 * completion (AGENTS.md, "no Janus value may gate a run, step 2, or step 4").
 * The selection and deck fields are kept on the round, so autosave and the
 * project carry them.
 */

import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { save } from "@tauri-apps/plugin-dialog";
import { mkdir } from "@tauri-apps/plugin-fs";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";
import { exportPositiveJanus, positiveJanusCandidates } from "@/lib/ipc-mame";
import { describeRpcError } from "@/lib/errors";
import { useRoundStore } from "@/store/round/roundSlice";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type {
  PositiveJanusCandidatesResult,
  PositiveJanusSourceParams,
} from "@/types/mame/positive_janus";
import type { PositiveJanusRecord } from "@/types/round";

export interface PositiveJanusPanelProps {
  /** The screen and mapping to read, or null when the form holds none. */
  sources: PositiveJanusSourceParams | null;
  roundId: string | null;
  roundNumber: number;
  /** Folder the save dialog opens in, or null without a project. */
  defaultFolder: string | null;
}

/** Identity of the files a selection was made against. */
export function positiveJanusSignature(sources: PositiveJanusSourceParams): string {
  return JSON.stringify([
    sources.gc_data_xlsx ?? "",
    sources.round1_report_xlsx ?? "",
    sources.numeric_report_xlsx ?? "",
    sources.verdict_xlsx ?? "",
    sources.layout_xlsx ?? "",
    sources.expected_xlsx ?? "",
  ]);
}

function joinPath(folder: string, filename: string): string {
  const sep = folder.includes("\\") ? "\\" : "/";
  return `${folder.replace(/[\\/]+$/, "")}${sep}${filename}`;
}

function parentDir(filePath: string): string {
  const index = Math.max(filePath.lastIndexOf("/"), filePath.lastIndexOf("\\"));
  return index > 0 ? filePath.slice(0, index) : "";
}

export function PositiveJanusPanel({
  sources,
  roundId,
  roundNumber,
  defaultFolder,
}: PositiveJanusPanelProps) {
  const { t } = useTranslation();
  const signature = sources ? positiveJanusSignature(sources) : "";
  const stored = useRoundStore((s) => {
    const round = s.rounds.find((candidate) => candidate.id === roundId);
    return round?.positive_janus ?? null;
  });
  // A record made against other files describes another plate.
  const record = stored && stored.input_signature === signature ? stored : null;
  const [listing, setListing] = useState<{
    signature: string;
    result: PositiveJanusCandidatesResult;
  } | null>(null);
  const [isFinding, setIsFinding] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [written, setWritten] = useState<{ path: string; count: number } | null>(null);
  const [volumeText, setVolumeText] = useState<string | null>(null);

  const result = listing && listing.signature === signature ? listing.result : null;
  const defaults = result?.defaults ?? null;
  const aboveWells = useMemo(
    () => (result ? result.candidates.filter((c) => c.above_wt).map((c) => c.well) : []),
    [result],
  );
  const selected = useMemo(
    () => new Set(record ? record.selected_wells : aboveWells),
    [record, aboveWells],
  );
  const volume = record?.volume ?? defaults?.volume ?? null;
  const sourceRack = record?.source_rack ?? defaults?.source_rack ?? "";
  const destRack = record?.dest_rack ?? defaults?.dest_rack ?? "";

  function writeRecord(patch: Partial<PositiveJanusRecord>) {
    if (!roundId || !defaults || !sources) return;
    const next: PositiveJanusRecord = {
      input_signature: signature,
      selected_wells: record ? record.selected_wells : aboveWells,
      volume: record?.volume ?? defaults.volume,
      source_rack: record?.source_rack ?? defaults.source_rack,
      dest_rack: record?.dest_rack ?? defaults.dest_rack,
      ...patch,
    };
    useRoundStore.getState().updateRoundField(roundId, "positive_janus", next);
    setWritten(null);
  }

  function toggle(well: string, checked: boolean) {
    const next = new Set(selected);
    if (checked) next.add(well);
    else next.delete(well);
    const order = result ? result.candidates.map((c) => c.well) : [...next];
    writeRecord({ selected_wells: order.filter((w) => next.has(w)) });
  }

  async function handleFind() {
    if (!sources) return;
    const requested = signature;
    setIsFinding(true);
    setError(null);
    setWritten(null);
    try {
      const res = await positiveJanusCandidates(sources);
      setListing({ signature: requested, result: res });
    } catch (err) {
      setError(describeRpcError(err, "mame"));
    } finally {
      setIsFinding(false);
    }
  }

  const volumeValid = volume !== null && Number.isFinite(volume) && volume > 0;
  const canExport =
    result !== null && selected.size > 0 && volumeValid &&
    sourceRack.trim() !== "" && destRack.trim() !== "" && !isExporting;

  async function handleExport() {
    if (!sources || !canExport || volume === null) return;
    const filename = `positive_janus_r${roundNumber}.csv`;
    const target = await save({
      defaultPath: defaultFolder ? joinPath(defaultFolder, filename) : filename,
      filters: [{ name: "CSV", extensions: ["csv"] }],
      title: t("mame.positiveJanus.chooseOutput"),
    });
    if (!target) return;
    setIsExporting(true);
    setError(null);
    try {
      const parent = parentDir(target);
      if (parent) await mkdir(parent, { recursive: true });
      const res = await exportPositiveJanus({
        ...sources,
        selected_wells: [...selected],
        volume,
        source_rack: sourceRack,
        dest_rack: destRack,
        output_csv: target,
      });
      setWritten({ path: res.output_path, count: res.row_count });
      toast.success(
        t("mame.positiveJanus.exported", { count: res.row_count, path: res.output_path }),
      );
    } catch (err) {
      setError(describeRpcError(err, "mame"));
    } finally {
      setIsExporting(false);
    }
  }

  return (
    <section
      aria-labelledby="bep-positive-janus"
      className="space-y-3 rounded-md border border-border p-3"
    >
      <h3 id="bep-positive-janus" className="text-sm font-medium text-foreground">
        {t("mame.positiveJanus.title")}
      </h3>
      <p className="text-xs text-muted-foreground">{t("mame.positiveJanus.description")}</p>

      {sources === null ? (
        <p role="status" className="text-xs text-muted-foreground">
          {t("mame.positiveJanus.needsPlateScreen")}
        </p>
      ) : (
        <>
          {result === null && record !== null && (
            <p role="status" className="text-xs text-muted-foreground">
              {t("mame.positiveJanus.savedSelection", { count: record.selected_wells.length })}
            </p>
          )}
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => void handleFind()}
            disabled={isFinding}
            aria-busy={isFinding}
          >
            {isFinding ? (
              <>
                <Loader2 size={14} className="mr-2 animate-spin" aria-hidden="true" />
                {t("mame.positiveJanus.finding")}
              </>
            ) : (
              t("mame.positiveJanus.find")
            )}
          </Button>
        </>
      )}

      {result !== null && (
        <>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p role="status" className="text-xs text-foreground">
              {t("mame.positiveJanus.summary", {
                selected: selected.size,
                total: result.candidates.length,
                above: result.n_above_wt,
              })}
            </p>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-6 px-2 text-xs"
              onClick={() => writeRecord({ selected_wells: aboveWells })}
            >
              {t("mame.positiveJanus.resetSelection")}
            </Button>
          </div>
          {result.warnings.map((warning) => (
            <p key={warning} className="text-xs text-muted-foreground">{warning}</p>
          ))}
          <ul
            aria-label={t("mame.positiveJanus.listLabel")}
            className="grid max-h-64 grid-cols-1 gap-1 overflow-y-auto overflow-x-hidden sm:grid-cols-2"
          >
            {result.candidates.map((c) => {
              const id = `bep-positive-${c.well}`;
              return (
                <li key={c.well} className="flex min-w-0 items-center gap-2 text-xs">
                  <input
                    id={id}
                    type="checkbox"
                    checked={selected.has(c.well)}
                    onChange={(event) => toggle(c.well, event.target.checked)}
                    className="h-4 w-4 cursor-pointer accent-primary"
                  />
                  <Label htmlFor={id} className="min-w-0 flex-1 cursor-pointer truncate text-xs">
                    <span className="font-mono">{c.well}</span> {c.name}{" "}
                    <span className="text-muted-foreground">
                      {t("mame.positiveJanus.relative", { value: c.relative.toFixed(3) })}
                    </span>
                    {c.above_wt && (
                      <span className="ml-1 text-primary">{t("mame.positiveJanus.aboveWt")}</span>
                    )}
                  </Label>
                </li>
              );
            })}
          </ul>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
            <div className="min-w-0 space-y-1">
              <Label htmlFor="bep-positive-volume" className="text-xs">
                {t("mame.positiveJanus.volume")}
              </Label>
              <Input
                id="bep-positive-volume"
                type="number"
                min={0}
                step="any"
                value={volumeText ?? (volume === null ? "" : String(volume))}
                onChange={(event) => {
                  setVolumeText(event.target.value);
                  const parsed = Number(event.target.value);
                  if (event.target.value.trim() !== "" && Number.isFinite(parsed) && parsed > 0) {
                    writeRecord({ volume: parsed });
                  }
                }}
                onBlur={() => setVolumeText(null)}
              />
            </div>
            <div className="min-w-0 space-y-1">
              <Label htmlFor="bep-positive-source" className="text-xs">
                {t("mame.positiveJanus.sourceRack")}
              </Label>
              <Input
                id="bep-positive-source"
                value={sourceRack}
                onChange={(event) => writeRecord({ source_rack: event.target.value })}
              />
            </div>
            <div className="min-w-0 space-y-1">
              <Label htmlFor="bep-positive-dest" className="text-xs">
                {t("mame.positiveJanus.destRack")}
              </Label>
              <Input
                id="bep-positive-dest"
                value={destRack}
                onChange={(event) => writeRecord({ dest_rack: event.target.value })}
              />
            </div>
          </div>
          <Button
            type="button"
            size="sm"
            disabled={!canExport}
            onClick={() => void handleExport()}
            aria-busy={isExporting}
          >
            {isExporting ? t("mame.positiveJanus.exporting") : t("mame.positiveJanus.export")}
          </Button>
        </>
      )}

      {written !== null && (
        <p role="status" className="break-all text-xs text-foreground">
          {t("mame.positiveJanus.exported", { count: written.count, path: written.path })}
        </p>
      )}
      {error !== null && (
        <div
          role="alert"
          className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-foreground"
        >
          <p className="font-medium">{t("mame.positiveJanus.error")}</p>
          <p className="mt-1 whitespace-pre-wrap text-muted-foreground">{error}</p>
        </div>
      )}
    </section>
  );
}
