/**
 * §16 Local Diagnostics, diagnostics bundle generator.
 *
 * Collects app meta, crash log, recent log lines and the last KURO design run
 * into a JSON file. The file is written to a user-chosen path via save dialog.
 * No external data transmission, local file only (§16 [필수]).
 *
 * Returns the saved file path, or null if the user cancelled.
 */

import { save } from "@tauri-apps/plugin-dialog";
import { writeTextFile } from "@tauri-apps/plugin-fs";
import { getCrashLog, type CrashEntry } from "./crashLog";
import { useAppStore } from "@/store/appStore";
import type {
  DesignRunOutcome,
  DesignRunRecord,
  FailedMutation,
  KuroDesignRequestSnapshot,
  RescueStats,
  RescuedMutation,
  SdmPrimerResult,
} from "@/types/models";

// Tauri global declared in vite-env.d.ts / via window.__APP_VERSION__
declare const __APP_VERSION__: string;

export interface DiagnosticsMeta {
  appVersion: string;
  generatedAt: string;
  userAgent: string;
  platform: string;
}

/** One failed mutation, as the sidecar reported it. */
export interface DiagnosticsFailure {
  /**
   * The mutation label, e.g. `K182N`, when the row looks like one; otherwise
   * `row 7 (61 characters, content withheld)`.
   *
   * A row the parser could not read at all is labelled with that row, because
   * design_sdm_primers_batch keys its parse_failures by the raw text. The
   * mutation box is split on newlines before it is sent
   * (designSlice.helpers.prepareDesignInput), so a pasted FASTA arrives as one
   * failure per line, and quoting those back reproduces the sequence. See
   * isQuotableRow for which rows are quoted.
   */
  mutation: string;
  rank: number;
  /**
   * Failure text from the sidecar, never reworded: the Tm, length and candidate
   * counts inside it are the diagnosis. Two things happen to it. A row that is
   * not quotable is removed from it by exact substring replacement, because
   * resolve_mutation_row quotes the row back into the message
   * (`Invalid mutation notation: '...'`, `Row: '...'`). And it is cut past
   * MAX_FAILURE_REASON, visibly.
   *
   * What remains, checked against every producer: a design failure from
   * _diagnose_design_failure carries numbers only, and a wild-type mismatch
   * names the three-base WT codon at the failed position.
   */
  reason: string;
}

/**
 * The last KURO design run, or an explicit statement that none is held.
 *
 * `no-run-data` covers two cases that look the same from here and read the same
 * to the recipient: no design has run in this session, and a design ran but an
 * input changed afterwards, which discards the results together with the
 * request snapshot (lib/kuroResultReset.ts). Either way no run exists whose
 * parameters and failures belong together. The key is always present, so "no
 * run" stays distinct from a run with zero failures.
 *
 * `request` is null when the results were restored from disk. No snapshot and
 * no workspace persists the design request, and both restore paths null it
 * (hooks/useAutosaveHydration.ts, store/slices/exportSlice.ts) rather than let
 * an earlier run's parameters stand next to the restored failures. The
 * failures are still worth sending, so this is a filled section with a stated
 * hole, not a dropped one.
 */
export type DiagnosticsRun =
  | { status: "no-run-data" }
  | {
      status: "recorded";
      /**
       * How the run ended, or `"running"` while one is in flight. Null when the
       * results came back from a saved project, which carries no run record.
       *
       * This is what separates a run that failed or was cancelled from one that
       * never happened. The request snapshot is written before the sidecar call
       * rather than after it, so a run the sidecar never answered still has one
       * and reports `"failed"` or `"interrupted"` here.
       */
      outcome: "running" | DesignRunOutcome | null;
      /** Null when the results came back from a saved project; see above. */
      request: KuroDesignRequestSnapshot | null;
      summary: { total: number; success: number; failed: number };
      failures: DiagnosticsFailure[];
      rescue: {
        /**
         * `auto_relax` as sent: the fill-on-failure box, minus strict spatial
         * mode. Null when the request is null, for the same reason.
         */
        requested: boolean | null;
        /**
         * How many mutations a rescue recovered, and by which stage. Those
         * mutations succeeded, so their labels stay out and only counts are
         * reported. Counted from rescuedMutationDetails rather than from
         * rescuedMutations, which designSlice writes once from the sidecar
         * reply and never updates again, while cascadeFailedRetry appends a
         * detail entry for every mutation it recovers.
         */
        rescuedCount: number;
        rescuedByStage: Record<string, number>;
        stats: RescueStats;
      };
    };

export interface DiagnosticsBundle {
  meta: DiagnosticsMeta;
  /** Crash entries with their message and stack capped; see MAX_CRASH_TEXT. */
  crashLog: CrashEntry[];
  /** Most recent 50 lines from the shared log buffer (both apps write to it). */
  recentLogs: string[];
  run: DiagnosticsRun;
}

/**
 * Longest row text quoted back verbatim.
 *
 * A mutation notation is a handful of characters (`K182N`, `A40P/E61Y`), and a
 * typo that fails to parse is the same size. Anything longer is not what this
 * field is for.
 */
const MAX_QUOTED_ROW = 32;

/**
 * Characters a mutation notation is written with. A row holding anything else
 * is not quoted back.
 */
const QUOTABLE_ROW_CHARS = /^[A-Za-z0-9/:*+\-_.,;() ]+$/;

/**
 * Total characters of quoted row text the whole bundle may carry, counting only
 * rows longer than BUDGET_EXEMPT_ROW.
 *
 * This exists because the first attempt at this protection was a per-field cap,
 * and a per-field cap cannot bound a leak that is spread over many fields. A
 * pasted gene arrives as one failure per line, so seventeen 64-character labels
 * passed seventeen separate caps and reassembled the sequence between them.
 * isQuotableRow is the real defence; this is what holds if it is ever wrong.
 *
 * Sized against the legitimate case rather than the leak: ninety-five failures
 * labelled `K182N` cost nothing, because a label that short is exempt. A run
 * that does exhaust the budget still reports every failure, with the tail
 * withheld rather than dropped.
 */
const QUOTED_ROW_BUDGET = 1024;

/** Rows this short cannot reconstruct anything, so they never spend the budget. */
const BUDGET_EXEMPT_ROW = 16;

/**
 * Longest crash-log message or stack kept.
 *
 * main.tsx and SourceColumnErrorBoundary store `error.message` and
 * `error.stack` as the runtime produced them. No render error was found that
 * quotes an input value into either, so this is a bound rather than a fix for a
 * known leak, and it is set well above a real stack trace.
 */
const MAX_CRASH_TEXT = 4000;

/**
 * Longest failure reason kept. A sanity bound, not the privacy mechanism: what
 * keeps a pasted sequence out is isQuotableRow and withholdRow above.
 *
 * It has to sit above every reason the sidecar legitimately produces, or it
 * would cut the Tm and length figures the bundle exists to carry. Measured
 * rather than guessed, with inputs deliberately pushed past what the request
 * model accepts. `_auto_relax_wall_clause` was called over a grid of tolerance,
 * length-floor and GC-window combinations covering each of its branches, and
 * the longest it returned was 573 characters. The engine reason it is appended
 * to tops out at 407: the strict off-target branch, whose site list reaches
 * four examples (the `len(offtarget_examples) < 3` guard is checked before an
 * iteration that can append twice), at 7-digit positions. 980 together, so
 * 1500 leaves half of that again in headroom.
 */
const MAX_FAILURE_REASON = 1500;

/**
 * Cut `value` to `limit`, saying so in the value itself.
 *
 * A silent cut reads as a complete string, and a reason that ends mid-number
 * would be read as the number. No pattern matching on the text: the sidecar
 * wording changes often and a parser over it would break quietly.
 */
function capText(value: string, limit: number): string {
  if (value.length <= limit) return value;
  return `${value.slice(0, limit)} [truncated, ${value.length} characters total]`;
}

/**
 * Whether a failed row may be quoted back as it was typed.
 *
 * The separation this leans on: a nucleotide or protein sequence has no digits
 * in it, and a mutation notation cannot be written without one. A FASTA header
 * fails on its `>`; a sequence line fails on both the digit test and, usually,
 * the length. A typo an operator actually needs to see (`K182`, `K182X/`,
 * `k 182 n`) keeps its digit and its length, so the diagnostic value stays.
 */
export function isQuotableRow(raw: string): boolean {
  const row = raw.trim();
  return row.length > 0
    && row.length <= MAX_QUOTED_ROW
    && /[0-9]/.test(row)
    && QUOTABLE_ROW_CHARS.test(row);
}

/**
 * Remove `raw` from `reason`, replacing each occurrence with `placeholder`.
 *
 * Exact substring replacement of a string already in hand, not a pattern over
 * the sidecar's wording: the wording changes and a parser over it would break
 * quietly. Both the row and its trimmed form are removed, because
 * resolve_mutation_row interpolates the row unchanged in one message
 * (`Invalid mutation notation: '{notation}'`) and `.strip()`ed in another
 * (`Row: {notation.strip()!r}`).
 *
 * The last check is a net under the two above: if the row survives in any form
 * this function did not anticipate, the whole reason goes rather than the row.
 */
export function withholdRow(reason: string, raw: string, placeholder: string): string {
  let out = reason;
  for (const form of new Set([raw, raw.trim()])) {
    if (form.length > 0) out = out.split(form).join(placeholder);
  }
  const trimmed = raw.trim();
  if (out.includes(raw) || (trimmed.length > 0 && out.includes(trimmed))) {
    return `reason withheld: it quoted ${placeholder} in a form that could not be removed`;
  }
  return out;
}

/** The store fields buildDiagnosticsRun reads. Narrow on purpose: it is a pure function over them. */
export interface DiagnosticsRunSource {
  lastDesignRequest: KuroDesignRequestSnapshot | null;
  designResults: SdmPrimerResult[];
  totalCount: number;
  failedMutations: FailedMutation[];
  rescueStats: RescueStats;
  rescuedMutationDetails: RescuedMutation[];
  /** True while a design is in flight, which is what `outcome: "running"` reports. */
  isDesigning: boolean;
  lastDesignRun: DesignRunRecord | null;
}

/**
 * Turn the sidecar's failure list into the bundle's, withholding any row that
 * does not look like a mutation notation from both the label and the reason.
 */
function buildFailures(failedMutations: FailedMutation[]): DiagnosticsFailure[] {
  let spent = 0;
  return failedMutations.map((failure) => {
    const raw = failure.mutation;
    const row = raw.trim();
    const cost = row.length > BUDGET_EXEMPT_ROW ? row.length : 0;
    if (isQuotableRow(raw) && spent + cost <= QUOTED_ROW_BUDGET) {
      spent += cost;
      return {
        mutation: row,
        rank: failure.rank,
        reason: capText(failure.reason, MAX_FAILURE_REASON),
      };
    }
    const placeholder = `row ${failure.rank} (${raw.length} characters, content withheld)`;
    return {
      mutation: placeholder,
      rank: failure.rank,
      reason: capText(withholdRow(failure.reason, raw, placeholder), MAX_FAILURE_REASON),
    };
  });
}

/**
 * Build the `run` section.
 *
 * `request` is taken from `lastDesignRequest` and never re-read from the panel,
 * because buildKuroResultResetPatch clears that snapshot in the same patch as
 * designResults, failedMutations, totalCount and rescueStats. A present
 * snapshot is therefore exactly the condition under which the parameters and
 * the failures came from one run.
 *
 * The section is filled whenever either a request or any result is held, so a
 * project reopened from disk still reports its failures with `request: null`.
 * A snapshot-only test would drop those; a result-only test would call a
 * never-run session a run that produced nothing.
 *
 * `success` counts the result rows rather than reading `successCount`, which is
 * what designSlice re-stamps lastDesignRun from after the rescue cascade, for
 * the same reason: the table is what the user is looking at.
 *
 * `lastDesignRun` is deliberately not read here. It is excluded from that patch
 * on purpose (types/models.ts, DesignRunRecord), so it outlives the results it
 * describes, and its `detail` field is raw error text that can quote a path.
 */
export function buildDiagnosticsRun(source: DiagnosticsRunSource): DiagnosticsRun {
  const request = source.lastDesignRequest;
  const hasResults =
    source.designResults.length > 0
    || source.failedMutations.length > 0
    || source.totalCount > 0;
  if (!request && !hasResults) return { status: "no-run-data" };
  return {
    status: "recorded",
    // runDesign writes lastDesignRun on every exit, and the reset patch at the
    // top of a run clears the snapshot, so a present snapshot and a finished
    // run belong together. While one is in flight the record is still the
    // previous run's, hence the explicit "running".
    outcome: source.isDesigning ? "running" : source.lastDesignRun?.outcome ?? null,
    request,
    summary: {
      total: source.totalCount,
      success: source.designResults.length,
      failed: source.failedMutations.length,
    },
    failures: buildFailures(source.failedMutations),
    rescue: {
      requested: request ? request.auto_relax : null,
      rescuedCount: source.rescuedMutationDetails.length,
      rescuedByStage: source.rescuedMutationDetails.reduce<Record<string, number>>(
        (tally, detail) => {
          tally[detail.type] = (tally[detail.type] ?? 0) + 1;
          return tally;
        },
        {},
      ),
      stats: source.rescueStats,
    },
  };
}

/**
 * Generate a diagnostics bundle and prompt the user to save it.
 *
 * Anonymisation policy. The bundle answers "which settings produced which
 * failure", so it carries settings and failures and nothing else.
 *
 * Included:
 * - Log messages, and crash-log component + message + optional stack.
 * - The design parameters the run was launched with. These are settings chosen
 *   in the panel, not data the user supplied.
 * - Failure reason strings, verbatim: their Tm, length and count figures are
 *   the whole point of sending the file.
 * - Labels of the *failed* mutations only, truncated, so the disclosure stays
 *   the size of the question being asked.
 *
 * Excluded:
 * - `fasta_path` and `mutations_csv_or_text`, the two payload fields carrying a
 *   file path and the pasted mutation text. pickDesignRequestSnapshot picks
 *   around them field by field rather than spreading the payload.
 * - Primer and template sequences, FASTA/CSV content, FASTA headers, project
 *   names. Two traces of a sequence can still appear, both belonging to a line
 *   that failed: the three-base wild-type codon a WT-mismatch reason names, and
 *   the row a parse failure quotes back, which is whatever the operator typed
 *   on that line. The second is why both the label and the reason are capped.
 * - Labels of mutations that succeeded, the rescued ones included: a rescue is
 *   reported as a count, because a recovered mutation is not the question.
 * - `lastDesignRun.detail`, raw error text that can quote a path.
 *
 * diagnostics.test.ts asserts the exclusions against a store seeded with
 * sentinels, which is the only mechanical guard on this list.
 *
 * @returns Saved file path, or null if the user cancelled the save dialog.
 */
export async function generateDiagnosticsBundle(): Promise<string | null> {
  const meta: DiagnosticsMeta = {
    appVersion: __APP_VERSION__,
    generatedAt: new Date().toISOString(),
    userAgent: navigator.userAgent,
    platform: navigator.platform,
  };

  const crashLog: CrashEntry[] = getCrashLog().map((entry) => ({
    ...entry,
    message: capText(entry.message, MAX_CRASH_TEXT),
    ...(entry.stack === undefined ? {} : { stack: capText(entry.stack, MAX_CRASH_TEXT) }),
  }));

  // One buffer for both apps. KURO progress messages arrive tagged `[KURO]`
  // (store/appStore.ts, setProgressHandler) and MAME sidecar lines tagged
  // `[MAME]` (hooks/mame/useMameSidecar.ts), both through appendLogLine on this
  // same store. The MAME menu used to pass an empty array in, on the belief
  // that MAME had no buffer, which threw away every line it had written; the
  // parameter is gone so that mistake is now a compile error.
  const state = useAppStore.getState();
  const recentLogs = state.logLines.slice(-50);

  const bundle: DiagnosticsBundle = {
    meta,
    crashLog,
    recentLogs,
    run: buildDiagnosticsRun(state),
  };

  const defaultFilename = `kuma-diagnostics-${new Date().toISOString().slice(0, 10)}.json`;

  const filePath = await save({
    defaultPath: defaultFilename,
    filters: [{ name: "Diagnostics JSON", extensions: ["json"] }],
    title: "Save Diagnostics",
  });

  if (!filePath) return null;

  await writeTextFile(filePath, JSON.stringify(bundle, null, 2));

  return filePath;
}
