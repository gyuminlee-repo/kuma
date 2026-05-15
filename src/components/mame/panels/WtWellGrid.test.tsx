import { render, screen, fireEvent, act } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { create } from "zustand";
import type { ActivitySlice } from "@/store/mame/activitySlice";
import type { RoundSlice } from "@/store/round/roundSlice";
import type { Round } from "@/types/round";

vi.mock("@/store/mame/activitySlice");
vi.mock("@/store/round/roundSlice");
vi.mock("sonner", () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

import { useActivityStore } from "@/store/mame/activitySlice";
import { useRoundStore } from "@/store/round/roundSlice";
import { toast } from "sonner";
import { WtWellGrid } from "./WtWellGrid";

const mockSetPlateMeta = vi.fn();
const mockUpdateRoundField = vi.fn();

function makeRound(id: string, wtWells: string[] = []): Round {
  return {
    id,
    n: 1,
    created_at: "2026-05-15T00:00:00Z",
    status: "design",
    error_info: null,
    plate_meta: {
      plates: [{ plate_id: "P01", wt_wells: wtWells, control_wells: [] }],
    },
    design: {},
    genotype: {},
    activity: null,
    merged_table: [],
  } as Round;
}

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
    exportEvolveproXlsx: vi.fn(),
    ...overrides,
  }));
}

function setupRoundStore(rounds: Round[], activeId: string | null) {
  const state: RoundSlice = {
    rounds,
    active_round_id: activeId,
    addRound: vi.fn(),
    transitionStatus: vi.fn(),
    setActiveRound: vi.fn(),
    updateRoundField: mockUpdateRoundField,
    handoffNextRound: vi.fn(),
  } as unknown as RoundSlice;
  vi.mocked(useRoundStore).mockImplementation(
    (sel?: (s: RoundSlice) => unknown) => (sel ? sel(state) : state),
  );
  (useRoundStore as unknown as { getState: () => RoundSlice }).getState = () => state;
}

describe("WtWellGrid — active round toggle", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useActivityStore).mockReturnValue(makeActivityStore());
    setupRoundStore([makeRound("r1")], "r1");
  });

  it("renders 96 buttons and toggles WT label on click", () => {
    render(<WtWellGrid />);
    const wellButtons = screen.getAllByRole("button", {
      name: /^[A-H](0[1-9]|1[0-2])$/,
    });
    expect(wellButtons.length).toBe(96);
    const a03 = screen.getByRole("button", { name: "A03" });
    expect(a03.textContent).not.toContain("WT");
    fireEvent.click(a03);
    expect(a03.textContent).toContain("WT");
  });
});

describe("WtWellGrid — debounce save", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useActivityStore).mockReturnValue(makeActivityStore());
    setupRoundStore([makeRound("r1")], "r1");
  });

  it("calls setPlateMeta once 400ms after last click (debounce coalesces)", async () => {
    vi.useFakeTimers();
    mockSetPlateMeta.mockResolvedValue(undefined);
    render(<WtWellGrid />);
    fireEvent.click(screen.getByRole("button", { name: "A03" }));
    vi.advanceTimersByTime(200);
    fireEvent.click(screen.getByRole("button", { name: "B05" }));
    vi.advanceTimersByTime(399);
    expect(mockSetPlateMeta).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(2);
    expect(mockSetPlateMeta).toHaveBeenCalledTimes(1);
    const call = mockSetPlateMeta.mock.calls[0];
    expect(call[0]).toBe("r1");
    expect(call[1].plates[0].wt_wells).toEqual(["A03", "B05"]);
    vi.useRealTimers();
  });

  it("aborts save when active round changes mid-debounce", async () => {
    vi.useFakeTimers();
    mockSetPlateMeta.mockResolvedValue(undefined);
    render(<WtWellGrid />);
    fireEvent.click(screen.getByRole("button", { name: "A03" }));
    // Simulate round change before debounce fires
    setupRoundStore([makeRound("r2")], "r2");
    await vi.advanceTimersByTimeAsync(500);
    expect(mockSetPlateMeta).not.toHaveBeenCalled();
    vi.useRealTimers();
  });
});

describe("WtWellGrid — unmount flush", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useActivityStore).mockReturnValue(makeActivityStore());
    setupRoundStore([makeRound("r1")], "r1");
  });

  it("flushes pending save on unmount", async () => {
    vi.useFakeTimers();
    mockSetPlateMeta.mockResolvedValue(undefined);
    const { unmount } = render(<WtWellGrid />);
    fireEvent.click(screen.getByRole("button", { name: "A03" }));
    unmount();
    await vi.advanceTimersByTimeAsync(1);
    expect(mockSetPlateMeta).toHaveBeenCalledTimes(1);
    expect(mockSetPlateMeta.mock.calls[0][1].plates[0].wt_wells).toEqual(["A03"]);
    vi.useRealTimers();
  });
});

describe("WtWellGrid — RPC failure", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useActivityStore).mockReturnValue(makeActivityStore());
    setupRoundStore([makeRound("r1")], "r1");
  });

  it("rolls back localWt and shows error toast on RPC fail", async () => {
    vi.useFakeTimers();
    mockSetPlateMeta.mockRejectedValue(new Error("boom"));
    render(<WtWellGrid />);
    const a03 = screen.getByRole("button", { name: "A03" });
    fireEvent.click(a03);
    expect(a03.textContent).toContain("WT");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });
    expect(toast.error).toHaveBeenCalled();
    expect(
      screen.getByRole("button", { name: "A03" }).textContent,
    ).not.toContain("WT");
    vi.useRealTimers();
  });
});

describe("WtWellGrid — no active round", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useActivityStore).mockReturnValue(makeActivityStore());
    setupRoundStore([], null);
  });

  it("renders disabled grid with noActiveRound message", () => {
    render(<WtWellGrid />);
    const grid = screen.getByLabelText(/96-well plate/i);
    expect(grid.className).toMatch(/opacity-50/);
    expect(grid.className).toMatch(/pointer-events-none/);
    expect(screen.getByText(/Activate a round/i)).toBeTruthy();
  });
});
