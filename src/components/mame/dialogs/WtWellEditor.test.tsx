import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { create } from "zustand";
import type { ActivitySlice } from "@/store/mame/activitySlice";
import type { RoundSlice } from "@/store/round/roundSlice";
import type { Round } from "@/types/round";

vi.mock("@/store/mame/activitySlice");
vi.mock("@/store/round/roundSlice");

import { useActivityStore } from "@/store/mame/activitySlice";
import { useRoundStore } from "@/store/round/roundSlice";
import { WtWellEditor } from "./WtWellEditor";

const mockSetPlateMeta = vi.fn();
const mockUpdateRoundField = vi.fn();

const baseRound: Round = {
  id: "round_1",
  n: 1,
  created_at: "2026-05-04T00:00:00Z",
  status: "design",
  error_info: null,
  plate_meta: { plates: [{ plate_id: "P01", wt_wells: ["A01", "A12"], control_wells: [] }] },
  design: {},
  genotype: {},
  activity: null,
  merged_table: [],
};

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
    setPlateMeta: mockSetPlateMeta,
    mergeActivity: vi.fn(),
    mergeForEvolvepro: vi.fn(),
    exportEvolveproCsv: vi.fn(),
    ...overrides,
  }));
}

function makeRoundStore(rounds: Round[] = [], activeId: string | null = null) {
  return create<RoundSlice>()(() => ({
    rounds,
    active_round_id: activeId,
    addRound: vi.fn(),
    transitionStatus: vi.fn(),
    setActiveRound: vi.fn(),
    updateRoundField: mockUpdateRoundField,
    handoffNextRound: vi.fn(),
  }));
}

describe("WtWellEditor", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders trigger button", () => {
    vi.mocked(useActivityStore).mockReturnValue(makeActivityStore());
    vi.mocked(useRoundStore).mockImplementation(
      (sel: (s: RoundSlice) => unknown) => sel(makeRoundStore([baseRound], "round_1").getState())
    );

    render(<WtWellEditor />);

    expect(screen.getByRole("button", { name: /Set WT Wells/i })).toBeTruthy();
  });

  it("opens dialog on trigger click", async () => {
    vi.mocked(useActivityStore).mockReturnValue(makeActivityStore());
    vi.mocked(useRoundStore).mockImplementation(
      (sel: (s: RoundSlice) => unknown) => sel(makeRoundStore([baseRound], "round_1").getState())
    );

    render(<WtWellEditor />);

    fireEvent.click(screen.getByRole("button", { name: /Set WT Wells/i }));

    await waitFor(() => {
      expect(screen.getByRole("dialog")).toBeTruthy();
    });
  });

  it("shows 96-well grid (96 cells) inside dialog", async () => {
    vi.mocked(useActivityStore).mockReturnValue(makeActivityStore());
    vi.mocked(useRoundStore).mockImplementation(
      (sel: (s: RoundSlice) => unknown) => sel(makeRoundStore([baseRound], "round_1").getState())
    );

    render(<WtWellEditor />);
    fireEvent.click(screen.getByRole("button", { name: /Set WT Wells/i }));

    await waitFor(() => screen.getByRole("dialog"));

    // 96 well toggle buttons (A01–H12)
    const wellButtons = screen.getAllByRole("button", { name: /^[A-H](0[1-9]|1[0-2])$/ });
    expect(wellButtons.length).toBe(96);
  });

  it("highlights pre-existing WT wells (A01, A12)", async () => {
    vi.mocked(useActivityStore).mockReturnValue(makeActivityStore());
    vi.mocked(useRoundStore).mockImplementation(
      (sel: (s: RoundSlice) => unknown) => sel(makeRoundStore([baseRound], "round_1").getState())
    );

    render(<WtWellEditor />);
    fireEvent.click(screen.getByRole("button", { name: /Set WT Wells/i }));

    await waitFor(() => screen.getByRole("dialog"));

    const a01 = screen.getByRole("button", { name: "A01" });
    const a02 = screen.getByRole("button", { name: "A02" });
    expect(a01.getAttribute("aria-pressed")).toBe("true");
    expect(a02.getAttribute("aria-pressed")).toBe("false");
  });

  it("calls setPlateMeta and updateRoundField on save", async () => {
    mockSetPlateMeta.mockResolvedValueOnce(undefined);

    vi.mocked(useActivityStore).mockReturnValue(makeActivityStore());
    vi.mocked(useRoundStore).mockImplementation(
      (sel: (s: RoundSlice) => unknown) => sel(makeRoundStore([baseRound], "round_1").getState())
    );

    render(<WtWellEditor />);
    fireEvent.click(screen.getByRole("button", { name: /Set WT Wells/i }));

    await waitFor(() => screen.getByRole("dialog"));

    fireEvent.click(screen.getByRole("button", { name: /Save/i }));

    await waitFor(() => {
      expect(mockSetPlateMeta).toHaveBeenCalledWith(
        "round_1",
        expect.objectContaining({ plates: expect.any(Array) })
      );
      expect(mockUpdateRoundField).toHaveBeenCalled();
    });
  });
});
