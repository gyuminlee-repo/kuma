/**
 * useRunDesign.test.ts — unit tests for the shared Run Design hook.
 *
 * Covers:
 *   1. missingFields — seqInfo absent
 *   2. missingFields — mutationText blank
 *   3. missingFields — multi-gene sequence without selectedGene
 *   4. missingFields empty → hasBlockingIssue false when sidecar ready
 *   5. run() short-circuits (no designPrimers call) when missingFields present
 *   6. run() short-circuits when sidecar not ready (hasBlockingIssue)
 *   7. run() proceeds to designPrimers on success path
 */

import { renderHook, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { useAppStore } from "@/store/appStore";

// --- ipc-kuro shim ---
vi.mock("@/lib/ipc-kuro", () => ({
  sendRequest: vi.fn(),
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
  spawnSidecar: vi.fn(() => Promise.resolve()),
  getLastProgressAt: vi.fn(() => Date.now()),
}));

// --- useSidecar: default "ready" ---
vi.mock("./useSidecar", () => ({
  useSidecar: vi.fn(() => ({ status: "ready", retry: vi.fn() })),
}));

// --- useKuroAutosave: no-op flush ---
vi.mock("./useKuroAutosave", () => ({
  useFlushKuroBeforeDesign: vi.fn(() => () => Promise.resolve()),
}));

// --- preflight: always ok, no warnings ---
vi.mock("@/lib/preflight", () => ({
  runPreflightCheck: vi.fn(() =>
    Promise.resolve({ ok: true, warnings: [], errors: [] }),
  ),
}));

// --- inputThresholds: always "ok" ---
vi.mock("@/lib/inputThresholds", () => ({
  checkKuroInputSize: vi.fn(() => ({ level: "ok", message: "", estimatedSeconds: 0 })),
  KURO_INPUT_THRESHOLDS: { ROW_WARN: 1000, ROW_BLOCK: 10000, FASTA_WARN_MB: 50, AVG_SECONDS_PER_ROW: 0.5 },
}));

import { useRunDesign } from "./useRunDesign";
import { useSidecar } from "./useSidecar";

const mockUseSidecar = vi.mocked(useSidecar);

/** Minimal SequenceInfo with one gene (no gene-select required) */
const singleGeneSeqInfo = {
  header: "test",
  seq_length: 100,
  genes: [{ gene: "gene1", product: "", cds_start: 0, cds_end: 100, aa_length: 33 }],
};

/** Minimal SequenceInfo with two genes (requires selectedGene) */
const multiGeneSeqInfo = {
  header: "multi",
  seq_length: 300,
  genes: [
    { gene: "geneA", product: "", cds_start: 0, cds_end: 100, aa_length: 33 },
    { gene: "geneB", product: "", cds_start: 200, cds_end: 300, aa_length: 33 },
  ],
};

describe("useRunDesign — missingFields", () => {
  beforeEach(() => {
    // Reset store to blank state before each test
    useAppStore.setState({
      seqInfo: null,
      mutationText: "",
      selectedGene: "",
      isDesigning: false,
    });
    mockUseSidecar.mockReturnValue({ status: "ready", retry: vi.fn() });
  });

  it("1. reports missing seqInfo", () => {
    useAppStore.setState({ seqInfo: null, mutationText: "M1A" });
    const { result } = renderHook(() => useRunDesign());
    expect(result.current.missingFields.length).toBeGreaterThan(0);
    expect(result.current.missingFields.some((f) => /sequence/i.test(f))).toBe(true);
  });

  it("2. reports blank mutationText", () => {
    useAppStore.setState({ seqInfo: singleGeneSeqInfo, mutationText: "" });
    const { result } = renderHook(() => useRunDesign());
    expect(result.current.missingFields.length).toBeGreaterThan(0);
    expect(result.current.missingFields.some((f) => /mutation/i.test(f))).toBe(true);
  });

  it("3. reports missing selectedGene for multi-gene sequence", () => {
    useAppStore.setState({
      seqInfo: multiGeneSeqInfo,
      mutationText: "M1A",
      selectedGene: "",
    });
    const { result } = renderHook(() => useRunDesign());
    expect(result.current.missingFields.some((f) => /gene/i.test(f))).toBe(true);
  });

  it("4. missingFields empty and hasBlockingIssue false when all inputs present and sidecar ready", () => {
    useAppStore.setState({
      seqInfo: singleGeneSeqInfo,
      mutationText: "M1A",
      selectedGene: "",
    });
    const { result } = renderHook(() => useRunDesign());
    expect(result.current.missingFields).toHaveLength(0);
    expect(result.current.hasBlockingIssue).toBe(false);
  });
});

describe("useRunDesign — run() guard", () => {
  beforeEach(() => {
    useAppStore.setState({
      seqInfo: null,
      mutationText: "",
      selectedGene: "",
      isDesigning: false,
    });
    mockUseSidecar.mockReturnValue({ status: "ready", retry: vi.fn() });
  });

  it("5. run() does not call designPrimers when missingFields present", async () => {
    useAppStore.setState({ seqInfo: null, mutationText: "M1A" });
    const designPrimersSpy = vi.fn();
    useAppStore.setState({ designPrimers: designPrimersSpy } as unknown as Parameters<typeof useAppStore.setState>[0]);

    const { result } = renderHook(() => useRunDesign());
    await act(async () => { result.current.run(); });
    expect(designPrimersSpy).not.toHaveBeenCalled();
  });

  it("6. hasBlockingIssue true when sidecar not ready", () => {
    mockUseSidecar.mockReturnValue({ status: "connecting", retry: vi.fn() });
    useAppStore.setState({ seqInfo: singleGeneSeqInfo, mutationText: "M1A", selectedGene: "" });
    const { result } = renderHook(() => useRunDesign());
    expect(result.current.hasBlockingIssue).toBe(true);
  });

  it("7. run() calls designPrimers when inputs valid and sidecar ready", async () => {
    useAppStore.setState({
      seqInfo: singleGeneSeqInfo,
      mutationText: "M1A",
      selectedGene: "",
      isDesigning: false,
    });
    const designPrimersSpy = vi.fn(() => Promise.resolve());
    useAppStore.setState({ designPrimers: designPrimersSpy } as unknown as Parameters<typeof useAppStore.setState>[0]);

    const { result } = renderHook(() => useRunDesign());
    await act(async () => { result.current.run(); });
    // Preflight resolves async — wait a tick
    await act(async () => { await Promise.resolve(); });
    expect(designPrimersSpy).toHaveBeenCalledTimes(1);
  });

  it("9. run() skips parseMutations and calls designPrimers directly in evolvepro mode", async () => {
    useAppStore.setState({
      seqInfo: singleGeneSeqInfo,
      mutationText: "M1A",   // evolvepro mode still requires non-empty mutationText for missing-fields check
      selectedGene: "",
      isDesigning: false,
      mutationInputMode: "evolvepro",
    });
    const parseMutationsSpy = vi.fn(() => Promise.resolve());
    const designPrimersSpy = vi.fn(() => Promise.resolve());
    useAppStore.setState({
      parseMutations: parseMutationsSpy,
      designPrimers: designPrimersSpy,
    } as unknown as Parameters<typeof useAppStore.setState>[0]);

    const { result } = renderHook(() => useRunDesign());
    await act(async () => { result.current.run(); });
    await act(async () => { await new Promise<void>((r) => setTimeout(r, 0)); });

    expect(parseMutationsSpy).not.toHaveBeenCalled();
    expect(designPrimersSpy).toHaveBeenCalledTimes(1);
  });
});
