/**
 * AdvisoryDecisionCard -- read-only display of the strategy.classify_round output.
 *
 * Scope (Fork D):
 *  - The list of per-round xlsx files (Variant + activity fold-change columns)
 *    is prefilled from what the rounds produced in step 4.1 and stays editable.
 *  - Calls strategy.classify_round RPC with RoundFileEntry list.
 *  - Advisory only: no Confirm button, and nothing here is a PI decision. The
 *    answer itself is kept on the round with the files and the time it came
 *    from, so it can be re-examined later; a stored answer is shown as history,
 *    never as the current verdict, once the list on screen differs from the one
 *    it was computed from or step 4.1 has rebuilt any file in that list.
 *  - The answer on the round is also what marks step 4.2 done (lib/mame/
 *    mameStepCompletion.ts). This card publishes nothing to the app store, so
 *    opening the screen cannot make the step look finished.
 *  - anti-fallback: never fabricates a result; JSON-RPC errors are shown explicitly.
 *
 * Two success states, drawn differently on purpose:
 *  - advisory "decision": the classifier answered. Coloured label badge, the
 *    reason behind it, and the confidence when the bootstrap gate produced one.
 *  - advisory "not_assessable": the classifier was never asked. Neutral outlined
 *    badge, no label, and a sentence naming the absent input together with the
 *    labels it puts out of reach. Drawing this as another "deferred" badge would
 *    claim a judgement was weighed and withheld.
 *
 * What decides whether switch_combinatorial and stop can be reached: both sit
 * behind a bootstrap gate that needs the wild-type replicates of the round
 * being judged. The per-round xlsx has no column for them, so step 4.1 records
 * them on the round it built and this card forwards them on the matching file
 * entry (lib/round/roundArtifacts.ts).
 *
 * The gate is only consulted once the signals have already proposed a
 * transition. Short of that, every run answers with a normal decision whatever
 * the replicates say. When it is consulted, a round that recorded enough gets a
 * verdict with a confidence, and a round that recorded none, too few, or a file
 * picked from outside this workspace lands on not_assessable, which names how
 * many were on record and how many the estimate needs.
 */

import { useState, useCallback, useEffect, useMemo, useRef } from "react";
import { useTranslation } from "react-i18next";
import { open } from "@tauri-apps/plugin-dialog";
import { InfoIcon, FileSpreadsheet, RotateCcw, X, PlayCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import { classifyRound } from "@/lib/ipc";
import { listArtifacts } from "@/lib/workspace";
import {
  normalizePath,
  roundEvolveproFiles,
  roundFilesPathSignature,
  roundFilesSignature,
  roundOutputStamps,
  unstampedFiles,
} from "@/lib/round/roundArtifacts";
import { useRoundStore } from "@/store/round/roundSlice";
import { Button } from "@/components/ui/button";
import type {
  ClassifyDecisionResult,
  ClassifyNotAssessableResult,
  ClassifyRoundResult,
  DecisionLabel,
  MissingClassifierInput,
  RoundFileEntry,
} from "@/types/mame/strategy";
import type { RoundAdvisoryRecord } from "@/types/round";

/** Narrowed shape of the i18next translator this file needs. */
type Translate = (key: string, options?: Record<string, unknown>) => string;

/** Where the list on screen came from, which the note under it states. */
type PrefillSource = "none" | "rounds" | "manifest" | "manual";

/**
 * Reason codes kuma_core/strategy/classify.py can emit, each with a phrase in
 * the locale files. bootstrap_inputs_missing is absent on purpose: the handler
 * converts that one into the not_assessable state before it reaches the UI.
 */
const REASON_CODES: ReadonlySet<string> = new Set([
  "calibration_period",
  "insufficient_data",
  "mixed_signals",
  "no_saturation_signal",
  "hysteresis_pending",
  "low_confidence",
  "stop_low_confidence",
  "saturated_with_throughput",
  "saturated_no_throughput",
]);

/** Maps DecisionLabel to a Tailwind color pair (bg/text). */
function labelColorClass(label: DecisionLabel): string {
  switch (label) {
    case "continue_walking":
      return "bg-emerald-100 text-emerald-800 dark:bg-emerald-900 dark:text-emerald-200";
    case "switch_combinatorial":
      return "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200";
    case "stop":
      return "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200";
    case "deferred":
      return "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200";
    default:
      return "bg-muted text-muted-foreground";
  }
}

/** Last-resort rendering for a code with no phrase, so no snake_case reaches the user. */
function humanize(code: string): string {
  return code.replace(/_/g, " ");
}

function labelText(label: DecisionLabel, t: Translate): string {
  return t(`advisoryDecision.labels.${label}`);
}

function reasonText(reason: string, t: Translate): string {
  return REASON_CODES.has(reason)
    ? t(`advisoryDecision.reasons.${reason}`)
    : humanize(reason);
}

function missingInputsText(
  inputs: MissingClassifierInput[],
  t: Translate,
): string {
  return inputs.map((input) => t(`advisoryDecision.missingInputs.${input}`)).join(", ");
}

function blockedLabelsText(labels: DecisionLabel[], t: Translate): string {
  return labels.map((label) => labelText(label, t)).join(", ");
}

/** Extract filename from an absolute path for display. */
function basename(path: string): string {
  return path.split(/[\\/]/).pop() ?? path;
}

/** A stored timestamp in the reader locale, or the raw value if it will not parse. */
function formatDecidedAt(iso: string): string {
  const at = new Date(iso);
  return Number.isNaN(at.getTime()) ? iso : at.toLocaleString();
}

/**
 * Footnote carried by an answered decision.
 *
 * The classifier reached a verdict, but some of its signals were unavailable
 * the whole time, so the verdict rests on a narrower base than the full model.
 * Saying which inputs were absent keeps that visible without implying the
 * verdict is in doubt.
 */
function MissingInputsNote({
  missing,
}: {
  missing: MissingClassifierInput[];
}) {
  const { t } = useTranslation();
  if (missing.length === 0) return null;
  return (
    <p className="text-[11px] text-muted-foreground">
      {t("advisoryDecision.missingInputsNote", {
        missing: missingInputsText(missing, t),
      })}
    </p>
  );
}

function DecisionDisplay({ result }: { result: ClassifyDecisionResult }) {
  const { t } = useTranslation();

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <span
          className={cn(
            "rounded-full px-2.5 py-0.5 text-xs font-semibold",
            labelColorClass(result.label),
          )}
          aria-label={t("advisoryDecision.labelAriaLabel", {
            label: labelText(result.label, t),
          })}
        >
          {labelText(result.label, t)}
        </span>
        {/*
          Confidence only exists on the bootstrap-gated branches, so it renders
          exactly when the round carried enough WT replicates for the gate to
          run. It is the agreement between the point decision and its
          resamples, which is why it says nothing on the branches that never
          reach the gate.
        */}
        {result.confidence != null && (
          <span className="text-[11px] text-muted-foreground">
            {t("advisoryDecision.confidence", {
              value: (result.confidence * 100).toFixed(0),
            })}
          </span>
        )}
      </div>
      <p className="text-xs text-muted-foreground">
        {reasonText(result.reason, t)}
      </p>
      <MissingInputsNote missing={result.missing_inputs} />
    </div>
  );
}

/**
 * The classifier was never asked.
 *
 * Reaching this state means the core decision tree did propose a transition,
 * which is the only way the bootstrap gate gets evaluated at all. The gate then
 * found nothing to test with. Both halves of that are stated: the signals point
 * somewhere, and the confirming question cannot be put.
 *
 * A round that recorded no wild-type wells and one that recorded three are
 * different situations with different remedies, so the counts the handler
 * returns are shown rather than folded into one "absent" sentence.
 */
function NotAssessableDisplay({
  result,
}: {
  result: ClassifyNotAssessableResult;
}) {
  const { t } = useTranslation();
  const badge = t("advisoryDecision.notAssessableBadge");
  const summaryKey =
    result.reason === "wt_replicates_insufficient"
      ? "advisoryDecision.notAssessableInsufficientSummary"
      : "advisoryDecision.notAssessableSummary";

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <span
          className="rounded-full border border-dashed border-muted-foreground/60 px-2.5 py-0.5 text-xs font-semibold text-muted-foreground"
          aria-label={t("advisoryDecision.labelAriaLabel", { label: badge })}
        >
          {badge}
        </span>
      </div>
      <p className="text-xs text-muted-foreground">
        {t(summaryKey, {
          missing: missingInputsText(result.missing_inputs, t),
          blocked: blockedLabelsText(result.blocked_decisions, t),
          count: result.wt_replicate_count,
          required: result.wt_replicate_min,
        })}
      </p>
    </div>
  );
}

interface FileRowProps {
  entry: RoundFileEntry;
  onRemove: (n: number) => void;
}

function FileRow({ entry, onRemove }: FileRowProps) {
  return (
    <li className="flex items-center justify-between gap-2 rounded border bg-muted/40 px-2 py-1 text-xs">
      <div className="flex items-center gap-1.5 min-w-0">
        <FileSpreadsheet
          size={12}
          aria-hidden="true"
          className="shrink-0 text-muted-foreground"
        />
        <span className="font-mono text-muted-foreground shrink-0">
          R{entry.n}
        </span>
        <span className="truncate" title={entry.path}>
          {basename(entry.path)}
        </span>
      </div>
      <button
        type="button"
        aria-label={`Remove round ${entry.n} file`}
        onClick={() => onRemove(entry.n)}
        className="shrink-0 rounded p-0.5 hover:bg-destructive/10 hover:text-destructive focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <X size={11} aria-hidden="true" />
      </button>
    </li>
  );
}

export interface AdvisoryDecisionCardProps {
  className?: string;
}

/**
 * AdvisoryDecisionCard (Fork D)
 *
 * File list + advisory classification card. The list is prefilled with what the
 * rounds produced in step 4.1 (lib/round/roundArtifacts.ts) and stays fully
 * editable, so an older project or a file from outside this workspace can still
 * be classified.
 *
 * States: idle | loading | result | error
 * Read-only advice. No Confirm button, no PI decision recorded as a choice.
 */
export function AdvisoryDecisionCard({
  className,
}: AdvisoryDecisionCardProps) {
  const { t } = useTranslation();

  const rounds = useRoundStore((s) => s.rounds);
  const roundFiles = useMemo(() => roundEvolveproFiles(rounds), [rounds]);
  // When the app wrote each round file. A rebuild moves the stamp, which is how
  // a stored answer is told apart from one about the file now at that path.
  const stamps = useMemo(() => roundOutputStamps(rounds), [rounds]);

  const [files, setFiles] = useState<RoundFileEntry[]>([]);
  const [prefillSource, setPrefillSource] = useState<PrefillSource>("none");
  const [result, setResult] = useState<ClassifyRoundResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  /**
   * Whether the operator has touched the list. Prefill fills an untouched list
   * and stops there: a proposal must never overwrite a hand-built selection,
   * which is what lets a past project or an outside file be classified. The
   * reload button below puts the round list back on demand.
   */
  const edited = useRef(false);

  useEffect(() => {
    if (edited.current || roundFiles.length === 0) return;
    setFiles(roundFiles);
    setPrefillSource("rounds");
  }, [roundFiles]);

  // Projects built before rounds recorded their outputs have nothing to offer
  // above, but they do have the workspace manifest entry step 4.1 registered.
  // It is one slot with no round number, so it is offered as a single leading
  // entry and the note says where it came from rather than implying it is
  // round 1 of a series.
  useEffect(() => {
    if (edited.current || roundFiles.length > 0) return;
    let cancelled = false;
    void (async () => {
      try {
        const artifacts = await listArtifacts({ app: "mame", type: "evolvepro_csv" });
        if (cancelled || edited.current || artifacts.length === 0) return;
        const newest = artifacts
          .slice()
          .sort((a, b) => b.producedAt.localeCompare(a.producedAt))[0];
        setFiles([{ n: 1, path: newest.path }]);
        setPrefillSource("manifest");
      } catch {
        // No workspace open, or no manifest to read. Nothing to prefill.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [roundFiles.length]);

  const clearAnswer = useCallback(() => {
    setResult(null);
    setError(null);
  }, []);

  const handleAddFiles = useCallback(async () => {
    const selected = await open({
      directory: false,
      multiple: true,
      filters: [{ name: "Excel", extensions: ["xlsx"] }],
      title: t("advisoryDecision.filePickerTitle"),
    });
    if (!selected) return;
    const paths = Array.isArray(selected) ? selected : [selected];
    // Compared the way every other path comparison here is: separators and case
    // folded. Raw string equality lets the same file in twice under two
    // spellings on Windows, and the handler counts entries as rounds.
    const existing = new Set(files.map((entry) => normalizePath(entry.path)));
    const added = paths.filter((path) => !existing.has(normalizePath(path)));
    if (added.length === 0) return;
    // Appended after the highest number in the list instead of renumbering the
    // whole thing. A prefilled entry carries the number of the round that
    // produced it, and renumbering would relabel round 3 as round 2 the moment
    // an outside file joined. The handler sorts by n and counts entries, so a
    // gap orders correctly and does not inflate the round count.
    const highest = files.reduce((max, entry) => Math.max(max, entry.n), 0);
    edited.current = true;
    setPrefillSource("manual");
    setFiles([...files, ...added.map((path, i) => ({ n: highest + i + 1, path }))]);
    clearAnswer();
  }, [files, t, clearAnswer]);

  const handleRemove = useCallback(
    (n: number) => {
      edited.current = true;
      setPrefillSource("manual");
      setFiles((prev) => prev.filter((e) => e.n !== n));
      clearAnswer();
    },
    [clearAnswer],
  );

  const handleReloadRounds = useCallback(() => {
    edited.current = false;
    setFiles(roundFiles);
    setPrefillSource("rounds");
    clearAnswer();
  }, [roundFiles, clearAnswer]);

  const handleClassify = useCallback(async () => {
    if (files.length === 0 || loading) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await classifyRound(files);
      setResult(res);
      // File the answer on the round together with what it was computed from,
      // so it can be re-examined after a restart instead of vanishing with this
      // component local state. A run that threw records nothing: there is no
      // answer to keep, and the error is on screen.
      const roundStore = useRoundStore.getState();
      const roundId = roundStore.active_round_id;
      if (roundId) {
        const record: RoundAdvisoryRecord = {
          result: res,
          inputs: files,
          decided_at: new Date().toISOString(),
          input_signature: roundFilesSignature(files, stamps),
        };
        roundStore.updateRoundField(roundId, "advisory", record);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [files, loading, stamps]);

  // What the round already has on record, and whether it still describes the
  // list on screen. A stored answer is about one ordered set of file contents,
  // so either a changed list or a rebuild of a file still in it demotes the
  // answer to history: it is never redrawn as the current verdict, only
  // mentioned with the time and the files it came from.
  const storedRecord = useRoundStore(
    (s) => s.rounds.find((r) => r.id === s.active_round_id)?.advisory ?? null,
  );
  const currentSignature = useMemo(
    () => roundFilesSignature(files, stamps),
    [files, stamps],
  );
  const restoredRecord =
    storedRecord && storedRecord.input_signature === currentSignature
      ? storedRecord
      : null;
  // Held back while the list is empty: on mount it is empty for one frame
  // before prefill lands, and a note saying the stored answer describes other
  // files would be flashing a comparison against nothing.
  const supersededRecord =
    storedRecord && !restoredRecord && files.length > 0 ? storedRecord : null;
  // Which of the two things happened, because the operator sees the same file
  // names either way. Same round numbers and paths as the list on screen means
  // step 4.1 wrote over them since the answer was computed; anything else means
  // the list itself is a different one.
  const supersededByRebuild =
    supersededRecord !== null &&
    roundFilesPathSignature(supersededRecord.inputs) ===
      roundFilesPathSignature(files);
  // Entries in a restored answer that no round produced. Their paths match, so
  // the answer is shown, but nothing recorded here says the file behind such a
  // path still holds what it held then, and the note below says so rather than
  // presenting the whole list as verified.
  const unverifiedInputs = useMemo(
    () => (restoredRecord ? unstampedFiles(restoredRecord.inputs, stamps) : []),
    [restoredRecord, stamps],
  );

  const shownResult = result ?? restoredRecord?.result ?? null;

  return (
    <section
      aria-labelledby="advisory-decision-heading"
      className={cn("flex flex-col gap-3", className)}
    >
      <h4
        id="advisory-decision-heading"
        className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground"
      >
        {t("advisoryDecision.heading")}
        <span
          className="ml-1.5 rounded bg-blue-100 px-1 py-0.5 text-[9px] font-medium text-blue-700 dark:bg-blue-900 dark:text-blue-300"
          aria-label={t("advisoryDecision.readOnlyAriaLabel")}
        >
          {t("advisoryDecision.readOnlyBadge")}
        </span>
      </h4>

      {files.length > 0 && (
        <ul
          aria-label={t("advisoryDecision.fileListAriaLabel")}
          className="flex flex-col gap-1"
        >
          {files.map((entry) => (
            <FileRow key={entry.path} entry={entry} onRemove={handleRemove} />
          ))}
        </ul>
      )}

      {files.length > 0 && prefillSource === "rounds" && (
        <p className="text-[11px] text-muted-foreground">
          {t("advisoryDecision.prefillFromRounds", { n: files.length })}
        </p>
      )}
      {files.length > 0 && prefillSource === "manifest" && (
        <p className="text-[11px] text-muted-foreground">
          {t("advisoryDecision.prefillFromManifest")}
        </p>
      )}

      <div className="flex items-center gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={handleAddFiles}
          disabled={loading}
          className="h-7 gap-1.5 text-xs"
          aria-label={t("advisoryDecision.addFilesAriaLabel")}
        >
          <FileSpreadsheet size={12} aria-hidden="true" />
          {t("advisoryDecision.addFiles")}
        </Button>
        {roundFiles.length > 0 && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={handleReloadRounds}
            disabled={loading}
            className="h-7 gap-1.5 text-xs"
          >
            <RotateCcw size={12} aria-hidden="true" />
            {t("advisoryDecision.reloadFromRounds")}
          </Button>
        )}
        <Button
          type="button"
          size="sm"
          onClick={handleClassify}
          disabled={files.length === 0 || loading}
          className="h-7 gap-1.5 text-xs"
          aria-label={t("advisoryDecision.classifyAriaLabel")}
        >
          <PlayCircle size={12} aria-hidden="true" />
          {t("advisoryDecision.classify")}
        </Button>
      </div>

      {loading && (
        <p className="text-xs text-muted-foreground" aria-live="polite">
          {t("advisoryDecision.loading")}
        </p>
      )}

      {error && (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-800 dark:border-red-800 dark:bg-red-950 dark:text-red-300"
        >
          <InfoIcon
            size={13}
            aria-hidden="true"
            className="mt-0.5 shrink-0 text-red-600 dark:text-red-400"
          />
          <span>{t("advisoryDecision.error", { message: error })}</span>
        </div>
      )}

      {result === null && restoredRecord && (
        <p className="text-[11px] text-muted-foreground">
          {t("advisoryDecision.restoredNote", {
            when: formatDecidedAt(restoredRecord.decided_at),
            n: restoredRecord.inputs.length,
          })}
          {unverifiedInputs.length > 0 && (
            <>
              {" "}
              {t("advisoryDecision.restoredUnverifiedNote", {
                files: unverifiedInputs
                  .map((entry) => basename(entry.path))
                  .join(", "),
              })}
            </>
          )}
        </p>
      )}

      {supersededRecord && (
        <p className="rounded-md border border-dashed border-muted-foreground/40 px-3 py-2 text-[11px] text-muted-foreground">
          {supersededByRebuild
            ? t("advisoryDecision.rebuiltNote", {
                when: formatDecidedAt(supersededRecord.decided_at),
                files: supersededRecord.inputs
                  .map((entry) => basename(entry.path))
                  .join(", "),
              })
            : t("advisoryDecision.supersededNote", {
                when: formatDecidedAt(supersededRecord.decided_at),
                files: supersededRecord.inputs
                  .map((entry) => basename(entry.path))
                  .join(", "),
              })}
        </p>
      )}

      {shownResult?.advisory === "decision" && (
        <DecisionDisplay result={shownResult} />
      )}
      {shownResult?.advisory === "not_assessable" && (
        <NotAssessableDisplay result={shownResult} />
      )}
    </section>
  );
}
