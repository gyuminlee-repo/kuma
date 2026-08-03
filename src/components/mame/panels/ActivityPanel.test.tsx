/**
 * ActivityPanel.test.tsx — MergeSection forwards selected CDS translation as ref_seq.
 *
 * Proves that MergeSection reads seqInfo+selectedGene from useAppStore, derives
 * the translation, and passes it as ref_seq to mergeForEvolvepro.
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { create } from "zustand";
import type { ActivitySlice } from "@/store/mame/activitySlice";
import type { RoundSlice } from "@/store/round/roundSlice";
import type { Round } from "@/types/round";
import type { SequenceInfo } from "@/types/models";
import { useAppStore } from "@/store/appStore";

// Mock modules before importing component
vi.mock("@/store/mame/activitySlice");
vi.mock("@/store/round/roundSlice");
vi.mock("@/store/validation", () => ({
  validateMergeActivity: vi.fn(() => ({ ok: true, missing: [] })),
}));
vi.mock("@/lib/inputThresholds", () => ({
  checkMameInputSize: vi.fn(() => ({ level: "ok", message: "" })),
}));
// Stub child components that require further mocking
vi.mock("@/components/mame/panels/ActivityUploadPanel", () => ({
  ActivityUploadPanel: () => null,
}));
vi.mock("@/components/mame/panels/WtWellGrid", () => ({
  WtWellGrid: () => null,
}));
vi.mock("@/components/round/RoundSummaryPanel", () => ({
  RoundSummaryPanel: () => null,
}));

import { useActivityStore } from "@/store/mame/activitySlice";
import { useRoundStore } from "@/store/round/roundSlice";
import { MergeSection } from "./ActivityPanel";

const mockMergeForEvolvepro = vi.fn();

function makeActivityStore(overrides: Partial<ActivitySlice> = {}) {
  return create<ActivitySlice>()(() => ({
    isUploading: false,
    isExporting: false,
    isMerging: false,
    uploadError: null,
    mergeError: null,
    exportError: null,
    lastMergeStats: null,
    lastReplicateStats: null,
    uploadActivityFile: vi.fn(),
    setPlateMeta: vi.fn(),
    mergeActivity: vi.fn(),
    mergeForEvolvepro: mockMergeForEvolvepro,
    exportEvolveproXlsx: vi.fn(),
    ...overrides,
  }));
}

const baseRound: Round = {
  id: "round_1",
  n: 1,
  created_at: "2026-05-04T00:00:00Z",
  status: "design",
  error_info: null,
  plate_meta: { plates: [] },
  design: {},
  genotype: {},
  activity: {
    records: [
      { plate_id: "P01", well_id: "A01", value: 1.0, replicate_idx: 1, is_wt: true, source_file: "f.csv" },
    ],
    plate_meta: { plates: [] },
  },
  merged_table: [],
};

function makeRoundStore(rounds: Round[] = [], activeId: string | null = null) {
  return create<RoundSlice>()(() => ({
    rounds,
    active_round_id: activeId,
    addRound: vi.fn(),
    transitionStatus: vi.fn(),
    setActiveRound: vi.fn(),
    updateRoundField: vi.fn(),
    handoffNextRound: vi.fn(),
  }));
}

const FIRST_TRANSLATION = "MKTWQ";
const SELECTED_TRANSLATION = "MNNPK";
const EVOLVEPRO_BUTTON_NAME = /Run v0\.3 RPC/;

const mockSeqInfo: SequenceInfo = {
  header: "target construct",
  seq_length: 1717,
  genes: [
    { gene: "target_a", product: "target A", cds_start: 1, cds_end: 717, aa_length: 239, translation: FIRST_TRANSLATION },
    { gene: "target_b", product: "target B", cds_start: 1000, cds_end: 1717, aa_length: 239, translation: SELECTED_TRANSLATION },
  ],
};

describe("MergeSection — ref_seq forwarding", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockMergeForEvolvepro.mockResolvedValue(undefined);
  });

  it("passes the selected gene translation as ref_seq", () => {
    useAppStore.setState({ seqInfo: mockSeqInfo, selectedGene: "1000" });

    vi.mocked(useActivityStore).mockReturnValue(makeActivityStore());
    vi.mocked(useRoundStore).mockImplementation(
      (sel: (s: RoundSlice) => unknown) =>
        sel(makeRoundStore([baseRound], "round_1").getState()),
    );

    render(<MergeSection />);

    const btn = screen.getByRole("button", { name: EVOLVEPRO_BUTTON_NAME });
    fireEvent.click(btn);

    expect(mockMergeForEvolvepro).toHaveBeenCalledWith(
      "round_1",
      expect.objectContaining({ ref_seq: SELECTED_TRANSLATION }),
    );
  });

  it("does not guess a reference when selectedGene does not match", () => {
    useAppStore.setState({ seqInfo: mockSeqInfo, selectedGene: "9999" });

    vi.mocked(useActivityStore).mockReturnValue(makeActivityStore());
    vi.mocked(useRoundStore).mockImplementation(
      (sel: (s: RoundSlice) => unknown) =>
        sel(makeRoundStore([baseRound], "round_1").getState()),
    );

    render(<MergeSection />);

    fireEvent.click(screen.getByRole("button", { name: EVOLVEPRO_BUTTON_NAME }));

    expect(mockMergeForEvolvepro).toHaveBeenCalledWith("round_1", undefined);
  });

  it("passes undefined options (no ref_seq) when seqInfo is null", () => {
    useAppStore.setState({ seqInfo: null, selectedGene: "" });

    vi.mocked(useActivityStore).mockReturnValue(makeActivityStore());
    vi.mocked(useRoundStore).mockImplementation(
      (sel: (s: RoundSlice) => unknown) =>
        sel(makeRoundStore([baseRound], "round_1").getState()),
    );

    render(<MergeSection />);

    fireEvent.click(screen.getByRole("button", { name: EVOLVEPRO_BUTTON_NAME }));

    // refSeq is "" → falsy → options is undefined
    expect(mockMergeForEvolvepro).toHaveBeenCalledWith("round_1", undefined);
  });
});
