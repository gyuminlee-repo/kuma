/**
 * A MAME analysis belongs to the workspace that started it.
 *
 * Clear All, or opening another project (hydration resets the store too), used
 * to leave the analyze RPC running; its reply then refilled the cleared table
 * and wrote its result file into whichever project was open. A reset now ends
 * the run: the backend is killed, the user is told, and the late reply is
 * dropped. A plain cancel ends native-barcode detection as well, because the
 * update guard reads that flag.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

const ipc = vi.hoisted(() => ({
  sendRequest: vi.fn(),
  cancelAndRespawn: vi.fn(async () => undefined),
  isSidecarRunning: vi.fn(() => false),
}));
const writeResult = vi.hoisted(() => vi.fn(async () => undefined));
const toasts = vi.hoisted(() => ({ info: vi.fn(), error: vi.fn(), warning: vi.fn() }));

vi.mock("@/lib/ipc-mame", () => ipc);
vi.mock("@/lib/mame/resultSnapshot", () => ({ writeMameResultSnapshot: writeResult }));
vi.mock("@/lib/workspace", () => ({ clearWorkspace: vi.fn(), getActiveWorkspace: () => null }));
vi.mock("sonner", () => ({ toast: toasts }));

import { resetMameAll } from "./resetAll";
import { useMameAppStore } from "./mameAppStore";
import { buildMameSnapshot } from "@/lib/mame/autosaveSnapshot";
import type { VerdictRecord } from "@/types/mame/models";

const VERDICT = { native_barcode: "barcode01", custom_barcode: "1_1", verdict: "PASS" } as unknown as VerdictRecord;
const RESULT = {
  verdicts: [VERDICT],
  replicates: [],
  summary: { total: 1, pass_count: 1, ambiguous_count: 0, fail_count: 0 },
  output_path: "/p/out/run.xlsx",
};

/** Holds every call of `method` until released; other methods answer at once. */
function holdCalls(method: string) {
  const pending: Array<{ resolve: (v: unknown) => void; reject: (e: Error) => void }> = [];
  ipc.sendRequest.mockImplementation((name: string) =>
    name === method
      ? new Promise((resolve, reject) => { pending.push({ resolve, reject }); })
      : Promise.resolve({ wells: [] }));
  return pending;
}

function consensusInputs() {
  useMameAppStore.setState({ inputMode: "consensus", inputDir: "/p/run", outputPath: "/p/out" });
}

beforeEach(async () => {
  vi.clearAllMocks();
  ipc.sendRequest.mockResolvedValue({});
  await resetMameAll();
  vi.clearAllMocks();
});

describe("a reset ends the running analysis", () => {
  it("Clear All cancels the run, says so, and its late reply neither refills nor persists", async () => {
    consensusInputs();
    const pending = holdCalls("analyze");
    const run = useMameAppStore.getState().runAnalysis();
    await vi.waitFor(() => expect(pending).toHaveLength(1));

    await resetMameAll();
    expect(ipc.cancelAndRespawn).toHaveBeenCalledTimes(1);
    expect(toasts.info).toHaveBeenCalledTimes(1);
    expect(useMameAppStore.getState().isAnalyzing).toBe(false);

    pending[0].resolve(RESULT);
    await run;
    const state = useMameAppStore.getState();
    expect(state.verdicts).toEqual([]);
    expect(state.summary).toBeNull();
    expect(state.isAnalyzing).toBe(false);
    expect(writeResult).not.toHaveBeenCalled();
  });

  it("a reset with no analysis running cancels nothing", async () => {
    await resetMameAll();
    expect(ipc.cancelAndRespawn).not.toHaveBeenCalled();
    expect(toasts.info).not.toHaveBeenCalled();
  });

  it("an analysis nobody interrupts lands its results and writes the result file", async () => {
    consensusInputs();
    const pending = holdCalls("analyze");
    const run = useMameAppStore.getState().runAnalysis();
    await vi.waitFor(() => expect(pending).toHaveLength(1));
    pending[0].resolve(RESULT);
    await run;

    const state = useMameAppStore.getState();
    expect(state.verdicts).toEqual([VERDICT]);
    expect(state.isAnalyzing).toBe(false);
    expect(state.analyzeMessage).toBe("Analysis complete");
    expect(writeResult).toHaveBeenCalledTimes(1);
    // The result file and the input snapshot must name these inputs the same
    // way, or a restore would read every saved run as superseded.
    const identity = buildMameSnapshot(state, undefined, state.projectPath).input_identity;
    expect(identity).toEqual(expect.any(String));
    expect(writeResult).toHaveBeenCalledWith(state.projectPath, expect.anything(), identity);
  });

  it("counts every reset, so consecutive resets stay distinguishable", async () => {
    const before = useMameAppStore.getState().resetEpoch;
    await resetMameAll();
    await resetMameAll();
    expect(useMameAppStore.getState().resetEpoch).toBe(before + 2);
  });

  it("drops a plate-data reply for results a reset replaced", async () => {
    useMameAppStore.setState({ verdicts: [VERDICT] });
    const pending = holdCalls("get_plate_data");
    const load = useMameAppStore.getState().loadPlateData();
    await vi.waitFor(() => expect(pending).toHaveLength(1));
    await resetMameAll();
    pending[0].resolve({ wells: [{ well: "A1", selected: true }] });
    await load;
    expect(useMameAppStore.getState().wells).toEqual([]);
  });
});

describe("an input changed while the analysis ran", () => {
  it("lands the results, says they are for the starting inputs, and stamps the file with those", async () => {
    consensusInputs();
    const startIdentity = buildMameSnapshot(useMameAppStore.getState(), undefined, useMameAppStore.getState().projectPath).input_identity;
    const pending = holdCalls("analyze");
    const run = useMameAppStore.getState().runAnalysis();
    await vi.waitFor(() => expect(pending).toHaveLength(1));
    useMameAppStore.getState().setReferencePath("/p/other-ref.fa");
    pending[0].resolve(RESULT);
    await run;

    expect(useMameAppStore.getState().verdicts).toEqual([VERDICT]);
    expect(toasts.warning).toHaveBeenCalledTimes(1);
    expect(writeResult).toHaveBeenCalledWith(useMameAppStore.getState().projectPath, expect.anything(), startIdentity);
  });
});

describe("cancelling during native-barcode detection", () => {
  it("ends the detection and does not report the killed request as a failure", async () => {
    useMameAppStore.setState({
      inputMode: "raw_run",
      inputDir: "/p/run",
      expectedPath: "/p/expected.xlsx",
      referencePath: "/p/ref.fa",
      outputPath: "/p/out",
      rawRunParams: { ...useMameAppStore.getState().rawRunParams, customBarcodesPath: "/p/barcodes.xlsx" },
    });
    const pending = holdCalls("mame.detect_native_barcodes");
    const run = useMameAppStore.getState().runAnalysis();
    await vi.waitFor(() => expect(useMameAppStore.getState().isDetectingBarcodes).toBe(true));

    await useMameAppStore.getState().cancelAnalysis();
    expect(useMameAppStore.getState().isDetectingBarcodes).toBe(false);
    expect(useMameAppStore.getState().isAnalyzing).toBe(false);

    pending[0].reject(new Error("Sidecar killed"));
    await run;
    const state = useMameAppStore.getState();
    expect(state.analyzeMessage).toBe("Analysis cancelled");
    expect(state.validationErrors).toEqual([]);
  });
});
