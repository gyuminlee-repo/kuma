import { afterEach, describe, expect, it } from "vitest";
import { useAppStore } from "../appStore";
import type { AppState } from "../types";
import type {
  FailedMutation,
  PlateMapping,
  RescuedMutation,
  SdmPrimerResult,
} from "../../types/models";

/** A completed design fixture makes stale derived state observable in every slice. */
const result: SdmPrimerResult = {
  mutation: "F385Y",
  aa_position: 385,
  codon_pos: 1152,
  forward_seq: "ATGCA",
  reverse_seq: "TGCAT",
  fwd_len: 20,
  rev_len: 20,
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
  overlap_seq: "ATGC",
  warnings: [],
};
const failedMutation: FailedMutation = { mutation: "Q163W", rank: 2, reason: "No candidate" };
const plateMapping: PlateMapping = {
  well: "A1",
  primer_name: "F385Y_F",
  sequence: result.forward_seq,
  primer_type: "forward",
  mutation: result.mutation,
};
const rescuedMutation: RescuedMutation = {
  original: result.mutation,
  rescued_by: result.mutation,
  type: "auto_relax",
};
const completedDesign: Pick<
  AppState,
  | "designResults"
  | "successCount"
  | "totalCount"
  | "failedMutations"
  | "plateMappings"
  | "dedupInfo"
  | "manuallySwapped"
  | "customCandidates"
  | "rescuedMutationDetails"
  | "backendDesignStateSynced"
> = {
  designResults: [result],
  successCount: 1,
  totalCount: 1,
  failedMutations: [failedMutation],
  plateMappings: [plateMapping],
  dedupInfo: { F385Y: ["F385Y"] },
  manuallySwapped: { F385Y: "both" as const },
  customCandidates: { F385Y: [] },
  rescuedMutationDetails: [rescuedMutation],
  backendDesignStateSynced: true,
};

function seedCompletedDesign() {
  useAppStore.setState(completedDesign);
}

function setInputDefaults() {
  useAppStore.setState({
    mutationText: "F385Y",
    tmFwdTarget: 62,
    organism: "ecoli",
    positionDiversityEnabled: true,
    evolveproCsvPath: "",
  });
}

function expectResultsCleared() {
  const state = useAppStore.getState();
  expect(state.designResults).toEqual([]);
  expect(state.successCount).toBe(0);
  expect(state.totalCount).toBe(0);
  expect(state.failedMutations).toEqual([]);
  expect(state.plateMappings).toEqual([]);
  expect(state.dedupInfo).toEqual({});
  expect(state.manuallySwapped).toEqual({});
  expect(state.customCandidates).toEqual({});
  expect(state.rescuedMutationDetails).toEqual([]);
  expect(state.backendDesignStateSynced).toBe(false);
}

afterEach(() => {
  useAppStore.getState().cancelDiversityReload();
  useAppStore.setState({
    ...completedDesign,
    mutationText: "F385Y",
    tmFwdTarget: 62,
    organism: "ecoli",
    positionDiversityEnabled: true,
    evolveproCsvPath: "",
  });
});

describe("KURO design-input result invalidation", () => {
  it("clears results for changed inputs from all four slices", () => {
    const store = useAppStore.getState();

    setInputDefaults();
    seedCompletedDesign();
    store.setMutationText("F385W");
    expectResultsCleared();

    seedCompletedDesign();
    store.setTmTargets(63, 58, 42);
    expectResultsCleared();

    seedCompletedDesign();
    store.setOrganism("bsubtilis");
    expectResultsCleared();

    seedCompletedDesign();
    store.setPositionDiversityEnabled(false);
    expectResultsCleared();
  });

  it("keeps results for an identical design-input value", () => {
    const store = useAppStore.getState();

    setInputDefaults();
    seedCompletedDesign();
    store.setMutationText("F385Y");
    store.setTmTargets(62, 58, 42);
    store.setOrganism("ecoli");
    store.setPositionDiversityEnabled(true);

    expect(useAppStore.getState().designResults).toEqual([result]);
    expect(useAppStore.getState().backendDesignStateSynced).toBe(true);
  });
});
