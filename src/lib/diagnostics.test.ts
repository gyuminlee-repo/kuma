/**
 * diagnostics.test.ts, the bundle has to answer "which settings produced this
 * failure" without carrying anything else.
 *
 * Two regressions are pinned here. One: the MAME menu passed an empty array to
 * generateDiagnosticsBundle on the belief that MAME kept no log buffer, so
 * every `[MAME]` line it had written through useAppStore.appendLogLine
 * (hooks/mame/useMameSidecar.ts) was discarded at the one moment it mattered.
 * Two: the bundle held meta, crashLog and 50 log lines, none of which names a
 * parameter, a mutation or a failure reason, so a report of
 * "No valid primer pair - reverse: closest Tm 71.1C at 19 bp" could not be
 * answered from the file the reporter sent.
 *
 * The exclusion test is the only mechanical guard on the anonymisation policy
 * written in diagnostics.ts, so it seeds a sentinel for every excluded class
 * and searches the serialized bundle rather than individual fields.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { save } from "@tauri-apps/plugin-dialog";
import { writeTextFile } from "@tauri-apps/plugin-fs";
import {
  buildDiagnosticsRun,
  generateDiagnosticsBundle,
  type DiagnosticsBundle,
} from "./diagnostics";
import { buildKuroResultResetPatch } from "./kuroResultReset";
import { useAppStore } from "@/store/appStore";
import {
  EMPTY_RESCUE_STATS,
  buildDesignRequestPayload,
  pickDesignRequestSnapshot,
} from "@/store/slices/designSlice.helpers";
import type {
  FailedMutation,
  KuroDesignRequestSnapshot,
  SdmPrimerResult,
} from "@/types/models";

vi.mock("@tauri-apps/plugin-dialog", () => ({
  save: vi.fn(async () => "diagnostics-out.json"),
}));
vi.mock("@tauri-apps/plugin-fs", () => ({
  writeTextFile: vi.fn(async () => undefined),
}));

const savedDialog = vi.mocked(save);
const savedWrite = vi.mocked(writeTextFile);

/** The user's report: 95 designed, one reverse primer that no length reaches in tolerance. */
const REAL_FAILURE_REASON =
  "No valid primer pair - reverse: closest Tm 71.1C at 19 bp, outside 58+-4.0C (length 19-27 bp)";

const request: KuroDesignRequestSnapshot = {
  polymerase: "Q5",
  codon_strategy: "closest",
  organism: "ecoli",
  tm_fwd_target: 62,
  tm_rev_target: 58,
  tm_overlap_target: 42,
  tol_max: 4,
  gc_min: 40,
  gc_max: 60,
  fwd_len_min: 18,
  fwd_len_max: 39,
  rev_len_min: 19,
  rev_len_max: 27,
  overlap_mode: "partial",
  strict_offtarget: false,
  auto_relax: true,
  seed: null,
};

const failure: FailedMutation = { mutation: "K182N", rank: 7, reason: REAL_FAILURE_REASON };

/** Every key the bundle may carry about the request, and no other. */
const REQUEST_KEYS = [
  "auto_relax",
  "codon_strategy",
  "fwd_len_max",
  "fwd_len_min",
  "gc_max",
  "gc_min",
  "organism",
  "overlap_mode",
  "polymerase",
  "rev_len_max",
  "rev_len_min",
  "seed",
  "strict_offtarget",
  "tm_fwd_target",
  "tm_overlap_target",
  "tm_rev_target",
  "tol_max",
];

/** Sentinels for each excluded class; none of them may reach the file. */
const SECRET = {
  sequence: "ACGTACGTACGTACGTTTTGGGCCCAAA",
  fastaPath: "D:\\lab\\secret-campaign\\pET28a_target.fasta",
  csvPath: "D:\\lab\\secret-campaign\\variants.csv",
  fastaHeader: "UnpublishedEnzymeCampaign_target_CDS",
  mutationText: "K182N\nF385Y\nQ163W",
  successLabel: "F385Y",
};

function successResult(): SdmPrimerResult {
  return {
    mutation: SECRET.successLabel,
    aa_position: 385,
    codon_pos: 1152,
    forward_seq: SECRET.sequence,
    reverse_seq: SECRET.sequence,
    fwd_len: 28,
    rev_len: 28,
    overlap_len: 18,
    candidate_fwd_count: 1,
    candidate_rev_count: 1,
    candidate_count: 1,
    tm_no_fwd: 62,
    tm_no_rev: 58,
    tm_overlap: 42,
    tm_condition_met: true,
    tolerance_used: 3,
    has_offtarget: false,
    penalty: 0,
    gc_fwd: 50,
    gc_rev: 50,
    wt_codon: "TTT",
    mt_codon: "TAT",
    overlap_seq: SECRET.sequence,
    warnings: [],
  };
}

const pristine = useAppStore.getState();

beforeEach(() => {
  savedDialog.mockClear();
  savedWrite.mockClear();
  localStorage.clear();
  useAppStore.setState({
    logLines: [],
    designResults: [],
    successCount: 0,
    totalCount: 0,
    failedMutations: [],
    rescuedMutations: [],
    rescueStats: EMPTY_RESCUE_STATS,
    lastDesignRequest: null,
  });
});

afterEach(() => {
  useAppStore.setState(pristine, true);
});

/** Run the generator and parse what it wrote. */
async function writtenBundle(): Promise<DiagnosticsBundle> {
  const path = await generateDiagnosticsBundle();
  expect(path).toBe("diagnostics-out.json");
  expect(savedWrite).toHaveBeenCalledTimes(1);
  return JSON.parse(savedWrite.mock.calls[0][1] as string) as DiagnosticsBundle;
}

/** Seed a store that holds the reported run: 95 intended, 94 designed, K182N failed. */
function seedFailedRun(): void {
  useAppStore.setState({
    lastDesignRequest: request,
    // 94 designed rows: `summary.success` counts the table, not successCount.
    designResults: Array.from({ length: 94 }, successResult),
    successCount: 94,
    totalCount: 95,
    failedMutations: [failure],
    rescuedMutations: [],
    rescueStats: { pool_cascade: 0, auto_relax: 4, positions_attempted: 1, pool_variants_tried: 0 },
    mutationText: SECRET.mutationText,
    fastaPath: SECRET.fastaPath,
    evolveproCsvPath: SECRET.csvPath,
    seqInfo: { header: SECRET.fastaHeader, seq_length: 1281, genes: [] },
  });
}

describe("buildDiagnosticsRun", () => {
  it("reports no run data before any design", () => {
    expect(buildDiagnosticsRun({
      lastDesignRequest: null,
      designResults: [],
      totalCount: 0,
      failedMutations: [],
      rescueStats: EMPTY_RESCUE_STATS,
      rescuedMutationDetails: [],
    })).toEqual({ status: "no-run-data" });
  });

  it("caps an unparsable label and says it cut it", () => {
    const pasted = "A".repeat(200);
    const run = buildDiagnosticsRun({
      lastDesignRequest: request,
      designResults: [],
      totalCount: 1,
      failedMutations: [{ mutation: pasted, rank: 1, reason: "unparsable" }],
      rescueStats: EMPTY_RESCUE_STATS,
      rescuedMutationDetails: [],
    });
    expect(run.status).toBe("recorded");
    if (run.status !== "recorded") return;
    expect(run.failures[0].mutation).toBe(
      `${"A".repeat(64)} [truncated, 200 characters total]`,
    );
    expect(run.failures[0].mutation).not.toContain(pasted);
  });

  it("leaves a long but legitimate reason alone", () => {
    // 884 is the measured worst case; see MAX_FAILURE_REASON in diagnostics.ts.
    const longReason = `${REAL_FAILURE_REASON} ${"x".repeat(1200 - REAL_FAILURE_REASON.length - 1)}`;
    expect(longReason).toHaveLength(1200);
    const run = buildDiagnosticsRun({
      lastDesignRequest: request,
      designResults: [],
      totalCount: 1,
      failedMutations: [{ mutation: "K182N", rank: 1, reason: longReason }],
      rescueStats: EMPTY_RESCUE_STATS,
      rescuedMutationDetails: [],
    });
    expect(run.status).toBe("recorded");
    if (run.status !== "recorded") return;
    expect(run.failures[0].reason).toBe(longReason);
  });

  it("reports a rescue as a count, never as labels", () => {
    const run = buildDiagnosticsRun({
      lastDesignRequest: request,
      designResults: [successResult(), successResult()],
      totalCount: 2,
      failedMutations: [],
      rescueStats: { pool_cascade: 1, auto_relax: 0, positions_attempted: 1, pool_variants_tried: 3 },
      rescuedMutationDetails: [
        { original: "K182N", rescued_by: SECRET.successLabel, type: "same_position" },
      ],
    });
    expect(run.status).toBe("recorded");
    if (run.status !== "recorded") return;
    expect(run.rescue.rescuedCount).toBe(1);
    expect(run.rescue.rescuedByStage).toEqual({ same_position: 1 });
    expect(JSON.stringify(run)).not.toContain(SECRET.successLabel);
    expect(JSON.stringify(run)).not.toContain("K182N");
  });
});

describe("pickDesignRequestSnapshot", () => {
  /** The payload designPrimers sends, with sentinels in the two fields the policy excludes. */
  function payload(overrides: Partial<Parameters<typeof buildDesignRequestPayload>[0]> = {}) {
    return buildDesignRequestPayload({
      fastaPath: SECRET.fastaPath,
      targetStart: 0,
      limitedText: SECRET.mutationText,
      selectedPolymerase: "Q5",
      codonStrategy: "closest",
      organism: "ecoli",
      tmFwdTarget: 62,
      tmRevTarget: 58,
      tmOverlapTarget: 42,
      gcMin: 40,
      gcMax: 60,
      primerLenEnabled: true,
      fwdLenMin: 18,
      fwdLenMax: 39,
      revLenMin: 19,
      revLenMax: 27,
      overlapMode: "partial",
      strictOfftarget: false,
      rescuePool: [SECRET.successLabel],
      tolMax: 4,
      randomSeed: null,
      fillOnFailure: true,
      ...overrides,
    });
  }

  it("keeps exactly the allowlisted keys and drops the template path and the mutation text", () => {
    const snapshot = pickDesignRequestSnapshot(payload());
    expect(Object.keys(snapshot).sort()).toEqual(REQUEST_KEYS);
    const serialized = JSON.stringify(snapshot);
    expect(serialized).not.toContain(SECRET.fastaPath);
    expect(serialized).not.toContain("K182N");
    // The rescue pool is a list of candidate labels, none of which failed.
    expect(serialized).not.toContain(SECRET.successLabel);
  });

  it("says the length axes are unset rather than omitting them", () => {
    const snapshot = pickDesignRequestSnapshot(payload({ primerLenEnabled: false }));
    expect(snapshot.fwd_len_min).toBeNull();
    expect(snapshot.fwd_len_max).toBeNull();
    expect(snapshot.rev_len_min).toBeNull();
    expect(snapshot.rev_len_max).toBeNull();
    // Still the full key set: a reader can tell "unchecked" from "not recorded".
    expect(Object.keys(snapshot).sort()).toEqual(REQUEST_KEYS);
  });

  it("records the reverse range the sidecar was actually given in full overlap", () => {
    // buildPrimerLengthBounds mirrors the forward range, so reading revLenMin
    // out of the store would print 19-27 for a run that searched 18-39.
    const snapshot = pickDesignRequestSnapshot(payload({ overlapMode: "full" }));
    expect(snapshot.rev_len_min).toBe(18);
    expect(snapshot.rev_len_max).toBe(39);
  });

  it("records auto_relax as sent, which is the fill-on-failure box", () => {
    expect(pickDesignRequestSnapshot(payload()).auto_relax).toBe(true);
    expect(pickDesignRequestSnapshot(payload({ fillOnFailure: false })).auto_relax).toBe(false);
  });
});

describe("the request snapshot is cleared with the results it describes", () => {
  it("dies in buildKuroResultResetPatch, so parameters and failures cannot drift apart", () => {
    // Without this the bundle would report the parameters the panel holds now
    // next to the failures of an earlier run under different ones.
    const patch = buildKuroResultResetPatch();
    expect(Object.keys(patch)).toContain("lastDesignRequest");
    expect(patch.lastDesignRequest).toBeNull();
    expect(patch.failedMutations).toEqual([]);
  });

  it("is cleared together with the failures when a design input changes", () => {
    seedFailedRun();
    useAppStore.getState().setTmTolerance(6);
    expect(useAppStore.getState().lastDesignRequest).toBeNull();
    expect(useAppStore.getState().failedMutations).toEqual([]);
  });
});

describe("generateDiagnosticsBundle", () => {
  it("writes an explicit no-run-data section when no design has run", async () => {
    const bundle = await writtenBundle();
    // The key is present rather than omitted: "never ran" is not "zero failures".
    expect(bundle.run).toEqual({ status: "no-run-data" });
  });

  it("carries the parameters, counts and verbatim failure reason of the reported run", async () => {
    seedFailedRun();
    const bundle = await writtenBundle();
    expect(bundle.run.status).toBe("recorded");
    if (bundle.run.status !== "recorded") return;
    expect(bundle.run.request).toEqual(request);
    expect(Object.keys(bundle.run.request ?? {}).sort()).toEqual(REQUEST_KEYS);
    expect(bundle.run.summary).toEqual({ total: 95, success: 94, failed: 1 });
    expect(bundle.run.failures).toEqual([
      { mutation: "K182N", rank: 7, reason: REAL_FAILURE_REASON },
    ]);
    expect(bundle.run.rescue.requested).toBe(true);
    expect(bundle.run.rescue.stats.auto_relax).toBe(4);
  });

  it("reports a run where everything succeeded without inventing failures", async () => {
    useAppStore.setState({
      lastDesignRequest: request,
      designResults: Array.from({ length: 95 }, successResult),
      successCount: 95,
      totalCount: 95,
      failedMutations: [],
    });
    const bundle = await writtenBundle();
    expect(bundle.run.status).toBe("recorded");
    if (bundle.run.status !== "recorded") return;
    expect(bundle.run.summary).toEqual({ total: 95, success: 95, failed: 0 });
    expect(bundle.run.failures).toEqual([]);
  });

  it("holds no sequence, file path, FASTA header, pasted input or successful label", async () => {
    seedFailedRun();
    const serialized = JSON.stringify(await writtenBundle());
    for (const [label, secret] of Object.entries(SECRET)) {
      expect(serialized, `${label} leaked into the bundle`).not.toContain(secret);
    }
    // The pasted block is excluded as a whole and line by line.
    for (const line of SECRET.mutationText.split("\n")) {
      if (line === failure.mutation) continue;
      expect(serialized, `${line} is a non-failed label`).not.toContain(line);
    }
  });

  it("keeps the MAME log lines the menu used to throw away", async () => {
    // The same call hooks/mame/useMameSidecar.ts makes for every progress
    // message: one buffer, tagged by app.
    useAppStore.getState().appendLogLine("[10:00:01] [MAME] Demultiplexing barcode04");
    useAppStore.getState().appendLogLine("[10:00:02] [KURO] Designing SDM primers...");
    const bundle = await writtenBundle();
    expect(bundle.recentLogs).toEqual([
      "[10:00:01] [MAME] Demultiplexing barcode04",
      "[10:00:02] [KURO] Designing SDM primers...",
    ]);
  });

  it("writes nothing when the save dialog is cancelled", async () => {
    savedDialog.mockResolvedValueOnce(null);
    expect(await generateDiagnosticsBundle()).toBeNull();
    expect(savedWrite).not.toHaveBeenCalled();
  });
});
