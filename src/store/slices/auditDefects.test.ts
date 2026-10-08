import { beforeEach, describe, expect, it, vi } from "vitest";
import type { SdmPrimerResult } from "../../types/models";

const rpc = vi.hoisted(() => vi.fn());
const mameRpc = vi.hoisted(() => vi.fn());
vi.mock("../../lib/ipc-kuro", () => ({ sendRequest: rpc, setProgressHandler: vi.fn(), cancelAndRespawn: vi.fn() }));
vi.mock("../../lib/ipc-mame", () => ({ sendRequest: mameRpc, setProgressHandler: vi.fn(), cancelAndRespawn: vi.fn() }));
vi.mock("../../lib/notify", () => ({ notifyJobComplete: vi.fn() }));
vi.mock("../../lib/toast", () => ({ notifyJobDone: vi.fn(), notifyJobError: vi.fn() }));
vi.mock("../../lib/keepAwake", () => ({ startKeepAwake: vi.fn(), stopKeepAwake: vi.fn() }));

import { useAppStore } from "../appStore";
import { useMameAppStore } from "../mame/mameAppStore";
import { addDesignResultState, applyCustomPrimerToResults } from "./designSlice.helpers";

const primer: SdmPrimerResult = {
  mutation: "M1A", aa_position: 1, codon_pos: 0,
  forward_seq: "ATGC", reverse_seq: "GCAT", fwd_len: 4, rev_len: 4,
  tm_no_fwd: 62, tm_no_rev: 58, tm_overlap: 42, tm_condition_met: true,
  tolerance_used: 1, has_offtarget: false, penalty: 0, warnings: [],
  overlap_len: 4, gc_fwd: 50, gc_rev: 50, wt_codon: "ATG", mt_codon: "GCG", overlap_seq: "ATGC",
};
const csv = {
  variants: ["M1A"], y_preds: [1], total_count: 2, selected_count: 1,
  ranked_candidates: [{ variant: "M1A", y_pred: 1 }, { variant: "M2A", y_pred: 0.5 }],
};

beforeEach(() => {
  vi.clearAllMocks();
  useAppStore.setState(useAppStore.getInitialState(), true);
  useMameAppStore.setState(useMameAppStore.getInitialState(), true);
  useAppStore.setState({
    fastaPath: "same.gb", selectedGene: "0", mutationInputMode: "evolvepro",
    evolveproCsvPath: "input.csv", mutationText: "M1A", maxPrimers: 1,
    evolveproSelectedVariants: ["M1A"], evolveproRankedCandidates: csv.ranked_candidates,
  });
  rpc.mockImplementation(async (method: string) => {
    if (method === "load_evolvepro_csv") return csv;
    if (method === "design_sdm_primers") return { results: [primer], success_count: 1, total_count: 1, failed_mutations: [] };
    throw new Error(`Unexpected RPC: ${method}`);
  });
});

describe("store audit regressions", () => {
  it("WS-01 keeps successful results and mappings after the default post-run refresh", async () => {
    await useAppStore.getState().designPrimers();
    expect(useAppStore.getState().designResults).toEqual([primer]);
    expect(useAppStore.getState().successCount).toBe(1);
    expect(useAppStore.getState().plateMappings).toHaveLength(2);
    expect(useAppStore.getState().backendDesignStateSynced).toBe(true);
  });

  it("WS-01 does not invalidate results just because a reload reports status", async () => {
    await useAppStore.getState().loadEvolveproCsv("input.csv");
    useAppStore.setState({ designResults: [primer], backendDesignStateSynced: true });
    await useAppStore.getState().loadEvolveproCsv("input.csv");
    expect(useAppStore.getState().designResults).toEqual([primer]);
  });

  it.each([false, true])("WS-02 submits and retains the chosen buffer candidate with rescue=%s", async (fillOnFailure) => {
    useAppStore.setState({ fillOnFailure });
    useAppStore.getState().setEvolveproVariantSelected("M1A", false);
    useAppStore.getState().setEvolveproVariantSelected("M2A", true);
    await useAppStore.getState().designPrimers();
    expect(rpc).toHaveBeenCalledWith("design_sdm_primers", expect.objectContaining({ mutations_csv_or_text: "M2A" }), 300_000);
    expect(useAppStore.getState().evolveproSelectedVariants).toEqual(["M2A"]);
  });

  it("WS-02 refuses an intentionally empty selection", async () => {
    useAppStore.getState().setEvolveproVariantSelected("M1A", false);
    await useAppStore.getState().designPrimers();
    expect(rpc.mock.calls.some(([method]) => method === "design_sdm_primers")).toBe(false);
  });

  it("WS-02 normal CSV loads still initialize the automatic selection", async () => {
    useAppStore.setState({ evolveproSelectedVariants: ["M2A"] });
    await useAppStore.getState().loadEvolveproCsv("other.csv");
    expect(useAppStore.getState().evolveproSelectedVariants).toEqual(["M1A"]);
  });

  it("WS-03 same workbook pick preserves mapping and well selection", () => {
    useMameAppStore.setState({ expectedPath: "same.xlsx", variantSheet: "Chosen", variantColumn: "mut", variantSelectionExplicit: true, selectedWells: ["A1"] });
    const before = useMameAppStore.getState();
    before.setExpectedPath("same.xlsx");
    expect(useMameAppStore.getState()).toBe(before);
  });

  it("WS-03 reinspection after a same-path pick preserves explicit mapping", async () => {
    useMameAppStore.setState({ expectedPath: "same.xlsx", variantSheet: "Chosen", variantColumn: "mut", variantSelectionExplicit: true, selectedWells: ["A1"] });
    mameRpc.mockResolvedValue({ is_kuro_export: false, sheets: ["Default", "Chosen"], headers: {}, suggested_column: "other" });
    useMameAppStore.getState().setExpectedPath("same.xlsx");
    await useMameAppStore.getState().inspectVariantSource("same.xlsx");
    expect(useMameAppStore.getState()).toMatchObject({ variantSheet: "Chosen", variantColumn: "mut", variantSelectionExplicit: true, selectedWells: ["A1"] });
  });

  it("WS-04 invalidates even an identical sequence response on same-path reload", async () => {
    const info = { header: "same", seq_length: 6, genes: [] };
    rpc.mockResolvedValue(info);
    useAppStore.setState({ seqInfo: info, designResults: [primer], backendDesignStateSynced: true });
    await useAppStore.getState().loadSequence("same.gb");
    expect(useAppStore.getState().designResults).toEqual([]);
    expect(useAppStore.getState().backendDesignStateSynced).toBe(false);
  });

  it("WS-04 invalidates a completed all-failed run on reload", async () => {
    rpc.mockResolvedValue({ header: "same", seq_length: 6, genes: [] });
    useAppStore.setState({ failedMutations: [{ mutation: "M1A", rank: 1, reason: "failed" }], totalCount: 1, backendDesignStateSynced: true });
    await useAppStore.getState().loadSequence("same.gb");
    expect(useAppStore.getState()).toMatchObject({ failedMutations: [], totalCount: 0, backendDesignStateSynced: false });
  });

  it.each(["custom", "rescue"])("WS-05 updates reverse diagnostics and clears pair Ta for %s", (mode) => {
    const neighbour = { ...primer, mutation: "M1V", hairpin_tm_rev: 20, recommended_ta: 65, ta_detail: "old", warnings: ["Rev old", "Fwd retained"] };
    const incoming: SdmPrimerResult = { ...primer, reverse_seq: "TTTT", hairpin_tm_rev: 80, synthesis_score_rev: 44, warnings: ["Rev new", "Fwd source"], recommended_ta: 70,
      homodimer_tm_rev: 60, offtarget_rev: [{ position: 9, strand: "sense", match_seq: "TTTT", tm: 50, match_length: 4 }] };
    const results = mode === "custom"
      ? applyCustomPrimerToResults({ mutation: "M1A", result: incoming, designResults: [neighbour] })
      : addDesignResultState({ mutation: "M1A", result: incoming, designResults: [neighbour], failedMutations: [], rescuedMutations: [], wellName: (i) => `A${i + 1}` }).designResults;
    expect(results[0]).toMatchObject({ reverse_seq: "TTTT", hairpin_tm_rev: 80, synthesis_score_rev: 44, warnings: ["Fwd retained", "Rev new"] });
    expect(results[0]?.recommended_ta).toBeUndefined();
    expect(results[0]?.ta_detail).toBeUndefined();
    expect(results[0]?.offtarget_rev).toEqual(incoming.offtarget_rev);
    expect(results[0]?.has_offtarget).toBe(true);
    expect(results[0]?.homodimer_tm_rev).toBe(60);
    expect(results[0]?.forward_seq).toBe(neighbour.forward_seq);
  });
});
