/**
 * The MAME client refuses a result that does not match its declared shape.
 *
 * Before this, `sendRequest` cast the payload straight to `T`, so anything the
 * sidecar returned became the declared type by assertion. The KURO client has
 * checked its side all along (`src/lib/ipc-kuro/index.ts`), which is what made
 * the gap a gap rather than a design.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const mocks = vi.hoisted(() => ({ rpc: vi.fn(), killSidecar: vi.fn() }));

vi.mock("../ipc", () => ({
  rawSidecarRpc: mocks.rpc,
  killSidecar: mocks.killSidecar,
}));

import { classifyRound, sendRequest } from "./index";
import {
  MAME_UNVALIDATED_METHODS,
  getMameRpcResultValidator,
  validatedMameMethods,
} from "@/types/mame/validators";

const BUILD_EVOLVEPRO_METHOD = "mame.activity.build_evolvepro_input";

function goodBuildEvolveproResult(): Record<string, unknown> {
  return {
    output_path: "/tmp/out.xlsx",
    n_variants: 12,
    n_authoritative: 10,
    n_fallback_only: 2,
    warnings: [],
    mismatched: [],
    n_ngs_excluded: 0,
    ngs_excluded: [],
    gc_export_path: "",
    label_audit: null,
    manifest_path: "/tmp/out.json",
    primary_format: "activity_path",
    input_count: 12,
    evaluable_count: 12,
    exclusion_reason_counts: {},
    normalization_sources: ["activity_path"],
    evidence_hash: "abc",
    artifact_hashes: {},
    wt_values: [1.0, 0.98, 1.02],
  };
}

beforeEach(() => {
  mocks.rpc.mockReset();
});

describe("MAME RPC result validation", () => {
  it("accepts a payload that matches the declared shape", async () => {
    mocks.rpc.mockResolvedValue(goodBuildEvolveproResult());
    const result = await sendRequest<{ n_variants: number }>(
      BUILD_EVOLVEPRO_METHOD,
      {},
    );
    expect(result.n_variants).toBe(12);
  });

  it("refuses a payload missing a field the UI reads", async () => {
    const bad = goodBuildEvolveproResult();
    delete bad.wt_values;
    mocks.rpc.mockResolvedValue(bad);
    await expect(sendRequest(BUILD_EVOLVEPRO_METHOD, {})).rejects.toThrow(
      /Invalid RPC result shape/,
    );
  });

  it("refuses a non-finite number where a measurement belongs", async () => {
    // `typeof NaN === "number"`, so only an explicit finiteness check catches
    // this. It is what a broken normalisation produces, and step 4.2 would
    // bootstrap on it.
    const bad = goodBuildEvolveproResult();
    bad.wt_values = [1.0, Number.NaN];
    mocks.rpc.mockResolvedValue(bad);
    await expect(sendRequest(BUILD_EVOLVEPRO_METHOD, {})).rejects.toThrow(
      /Invalid RPC result shape/,
    );
  });

  it("refuses a classify_round payload that is neither success shape", async () => {
    mocks.rpc.mockResolvedValue({ label: "stop", reason: "why" });
    await expect(classifyRound([{ n: 1, path: "/tmp/r1.xlsx" }])).rejects.toThrow(
      /Invalid RPC result shape/,
    );
  });

  it("accepts both classify_round success shapes", async () => {
    mocks.rpc.mockResolvedValue({
      advisory: "decision",
      label: "stop",
      reason: "plateau",
      confidence: 0.8,
      missing_inputs: [],
    });
    await expect(
      classifyRound([{ n: 1, path: "/tmp/r1.xlsx" }]),
    ).resolves.toMatchObject({ advisory: "decision" });

    mocks.rpc.mockResolvedValue({
      advisory: "not_assessable",
      reason: "wt_replicates_missing",
      missing_inputs: ["wt_replicates"],
      blocked_decisions: ["switch_combinatorial", "stop"],
    });
    await expect(
      classifyRound([{ n: 1, path: "/tmp/r1.xlsx" }]),
    ).resolves.toMatchObject({ advisory: "not_assessable" });
  });

  it("reproduces what the unchecked cast used to do with the same payload", async () => {
    // The pre-change client body, kept as the defect this file removes: the
    // result was cast to `T` and handed on, so a payload with no `wt_values`
    // became a `BuildEvolveproInputResult` whose `wt_values` was `undefined`,
    // and the failure surfaced inside a component rather than at the boundary.
    async function oldSendRequest<T>(method: string): Promise<T> {
      return (await mocks.rpc("mame", method, {}, 60_000)) as T;
    }
    const bad = goodBuildEvolveproResult();
    delete bad.wt_values;
    mocks.rpc.mockResolvedValue(bad);

    const stale = await oldSendRequest<{ wt_values: number[] }>(
      BUILD_EVOLVEPRO_METHOD,
    );
    expect(stale.wt_values).toBeUndefined();
    // The same payload through the current client is refused instead.
    mocks.rpc.mockResolvedValue(bad);
    await expect(sendRequest(BUILD_EVOLVEPRO_METHOD, {})).rejects.toThrow(
      /Invalid RPC result shape/,
    );
  });

  it("passes a method the table does not cover through unchanged", async () => {
    // The gap is real and named rather than papered over: an uncovered method
    // behaves exactly as every MAME method did before.
    expect(getMameRpcResultValidator("ping")).toBeNull();
    mocks.rpc.mockResolvedValue({ anything: true });
    await expect(sendRequest("ping", {})).resolves.toEqual({ anything: true });
  });
});

describe("coverage of the MAME dispatcher", () => {
  it("classifies every dispatcher method as validated or listed", () => {
    // The point of `MAME_UNVALIDATED_METHODS` is that the gap is visible. A
    // method in neither list is one nobody has looked at, which is the state
    // this whole change is about.
    const source = readFileSync(
      resolve(__dirname, "../../../python-core/sidecar_mame/dispatcher.py"),
      "utf-8",
    );
    const block = source.slice(
      source.indexOf("_METHODS = {"),
      source.indexOf("_ASYNC_METHODS"),
    );
    const dispatcherMethods = new Set(
      [...block.matchAll(/^\s{4}"([\w.]+)":/gm)].map((m) => m[1]),
    );
    expect(dispatcherMethods.size).toBeGreaterThan(20);

    const covered = new Set([
      ...validatedMameMethods(),
      ...MAME_UNVALIDATED_METHODS,
    ]);
    const unclassified = [...dispatcherMethods].filter((m) => !covered.has(m));
    expect(unclassified).toEqual([]);

    const stale = [...covered].filter((m) => !dispatcherMethods.has(m));
    expect(stale).toEqual([]);
  });
});
