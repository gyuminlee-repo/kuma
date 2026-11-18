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
import { getCrashLog } from "./crashLog";
import { useAppStore } from "@/store/appStore";
import type {
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
   * The mutation label, e.g. `K182N`. For a line the parser could not read at
   * all this is that raw input line, because design_sdm_primers_batch keys its
   * parse_failures by the raw row, so it is truncated to MAX_FAILURE_LABEL
   * characters.
   */
  mutation: string;
  rank: number;
  /**
   * Failure text from the sidecar, never reworded: the Tm, length and candidate
   * counts inside it are the diagnosis. Cut only past MAX_FAILURE_REASON, and
   * then visibly.
   *
   * What that admits, checked against every producer: a design failure from
   * _diagnose_design_failure carries numbers only. A parse failure carries the
   * message resolve_mutation_row raised, which quotes the offending row back
   * (`Invalid mutation notation: '...'`, `Row: '...'`), and a wild-type
   * mismatch names the three-base WT codon at that position. All of those
   * belong to a line that failed, which is the line being asked about, so they
   * stay; the cap is what keeps a pasted sequence from arriving whole.
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
  crashLog: ReturnType<typeof getCrashLog>;
  /** Most recent 50 lines from the shared log buffer (both apps write to it). */
  recentLogs: string[];
  run: DiagnosticsRun;
}

/**
 * Longest failure label kept.
 *
 * A design failure is labelled `K182N`. A row the parser could not read at all
 * is labelled with that row, because design_sdm_primers_batch keys its
 * parse_failures by the raw text, so an operator who pastes a FASTA line into
 * the mutation box labels a failure with that sequence.
 */
const MAX_FAILURE_LABEL = 64;

/**
 * Longest failure reason kept.
 *
 * The same raw row reaches the reason as well, because resolve_mutation_row
 * quotes it back (`Invalid mutation notation: '...'`, `Row: '...'`), so capping
 * only the label leaves the paste in the file through the other field.
 *
 * The cap has to sit above every reason the sidecar legitimately produces, or
 * it would cut the Tm and length figures the bundle exists to carry. Measured
 * rather than guessed, with inputs deliberately pushed past what the request
 * model accepts: `_auto_relax_wall_clause` was called over a grid of tolerance,
 * length-floor and GC-window combinations covering each of its branches, and
 * the longest it returned was 573 characters (7-digit floors, 5-digit
 * tolerance). The engine reason it is appended to tops out around 311: three
 * clauses joined, or the off-target branch with its three site examples at
 * 7-digit positions. 884 together, so 1200 leaves a third of that again in
 * headroom and still bounds a pasted coding sequence.
 */
const MAX_FAILURE_REASON = 1200;

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

/** The store fields buildDiagnosticsRun reads. Narrow on purpose: it is a pure function over them. */
export interface DiagnosticsRunSource {
  lastDesignRequest: KuroDesignRequestSnapshot | null;
  designResults: SdmPrimerResult[];
  totalCount: number;
  failedMutations: FailedMutation[];
  rescueStats: RescueStats;
  rescuedMutationDetails: RescuedMutation[];
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
    request,
    summary: {
      total: source.totalCount,
      success: source.designResults.length,
      failed: source.failedMutations.length,
    },
    failures: source.failedMutations.map((f) => ({
      mutation: capText(f.mutation, MAX_FAILURE_LABEL),
      rank: f.rank,
      reason: capText(f.reason, MAX_FAILURE_REASON),
    })),
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

  const crashLog = getCrashLog();

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
