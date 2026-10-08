/**
 * A completed run's outputs (verdicts, wells, janusAutosave, ...) describe the
 * inputs that produced them. Swapping an input that the analyze/demux RPCs
 * actually read must clear those outputs, or the UI keeps showing a previous
 * run's conclusion (including its Janus autosave banner) as if it described
 * the newly picked file (2026-08-06 incident this guards against).
 *
 * NOT RUN: WSL sandbox has no node_modules here, so `vitest` cannot execute.
 * Written to the same store-double pattern as inputSlice.test.ts; expected to
 * pass once run in an environment with dependencies installed.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AppState } from "../types";
import { createInputSlice } from "./inputSlice";

vi.mock("@/lib/ipc-mame", () => ({
  sendRequest: vi.fn(),
  cancelAndRespawn: vi.fn(),
}));

function makeStore(initial: Partial<AppState> = {}) {
  const state: Partial<AppState> = {
    clearResults: vi.fn(),
    refreshAnalyzeCdsCandidates: vi.fn().mockResolvedValue(undefined),
    ...initial,
  };
  const set = (
    updater: Partial<AppState> | ((current: AppState) => Partial<AppState>),
  ) => {
    const updates = typeof updater === "function" ? updater(state as AppState) : updater;
    Object.assign(state, updates);
  };
  const get = () => state as AppState;
  const slice = createInputSlice(
    set as Parameters<typeof createInputSlice>[0],
    get as Parameters<typeof createInputSlice>[1],
    {} as Parameters<typeof createInputSlice>[2],
  );
  Object.assign(state, slice, initial);
  return state as AppState;
}

describe("inputSlice: clearing stale run outputs on input change", () => {
  let store: AppState;

  beforeEach(() => {
    store = makeStore();
  });

  it("setInputDir clears results when the folder actually changes", () => {
    store.setInputDir("/run/a");
    expect(store.clearResults).toHaveBeenCalledTimes(1);
  });

  it("setInputDir does not clear results when re-picking the same folder", () => {
    store.setInputDir("/run/a");
    (store.clearResults as ReturnType<typeof vi.fn>).mockClear();
    store.setInputDir("/run/a");
    expect(store.clearResults).not.toHaveBeenCalled();
  });

  it("setExpectedPath clears results when the workbook changes", () => {
    store.setExpectedPath("/wb/expected.xlsx");
    expect(store.clearResults).toHaveBeenCalledTimes(1);
  });

  it("setReferencePath clears results when the reference changes", () => {
    store.setReferencePath("/ref/gene.fasta");
    expect(store.clearResults).toHaveBeenCalledTimes(1);
  });

  it("setSelectedWells clears results when the declared wells change", () => {
    store.setSelectedWells(["A1", "B1"]);
    expect(store.clearResults).toHaveBeenCalledTimes(1);
  });

  it("setOutputPath (destination only) never clears results", () => {
    store.setOutputPath("/exports/out");
    expect(store.clearResults).not.toHaveBeenCalled();
  });

  it("setParams clears results when an RPC-relevant param changes", () => {
    store.setParams({ cdsStart: 10 });
    expect(store.clearResults).toHaveBeenCalledTimes(1);
  });

  it("setParams clears results when the minimum read depth changes", () => {
    store.setParams({ minFilteredDepth: 25 });
    expect(store.clearResults).toHaveBeenCalledTimes(1);
  });

  it("setWtPlacement clears results only when the analyzed placement changes", () => {
    store.setWtPlacement("after_last_variant");
    expect(store.clearResults).toHaveBeenCalledTimes(1);

    (store.clearResults as ReturnType<typeof vi.fn>).mockClear();
    store.setWtPlacement("after_last_variant");
    expect(store.clearResults).not.toHaveBeenCalled();
  });

  it("setVariantSheet clears results even when the declared wells are already null", () => {
    store.setVariantSheet("Variants");
    expect(store.clearResults).toHaveBeenCalledTimes(1);

    (store.clearResults as ReturnType<typeof vi.fn>).mockClear();
    store.setVariantSheet("Variants");
    expect(store.clearResults).not.toHaveBeenCalled();
  });

  it("setVariantColumn clears results even when the declared wells are already null", () => {
    store.setVariantColumn("Mutation");
    expect(store.clearResults).toHaveBeenCalledTimes(1);

    (store.clearResults as ReturnType<typeof vi.fn>).mockClear();
    store.setVariantColumn("Mutation");
    expect(store.clearResults).not.toHaveBeenCalled();
  });
});
