import { render, screen, waitFor } from "@testing-library/react";
import { fireEvent } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { create } from "zustand";
import type { ActivitySlice } from "@/store/mame/activitySlice";
import type { RoundSlice } from "@/store/round/roundSlice";
import type { Round } from "@/types/round";

// Mock modules before importing component
vi.mock("@/store/mame/activitySlice");
vi.mock("@/store/round/roundSlice");
vi.mock("@tauri-apps/plugin-dialog", () => ({
  open: vi.fn().mockResolvedValue("/fake/path/activity.csv"),
}));

import { useActivityStore } from "@/store/mame/activitySlice";
import { useRoundStore } from "@/store/round/roundSlice";
import { ActivityUploadPanel } from "./ActivityUploadPanel";

const mockUpload = vi.fn();

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
    uploadActivityFile: mockUpload,
    setPlateMeta: vi.fn(),
    mergeActivity: vi.fn(),
    mergeForEvolvepro: vi.fn(),
    exportEvolveproCsv: vi.fn(),
    exportEvolveproXlsx: vi.fn(),
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
    updateRoundField: vi.fn(),
    handoffNextRound: vi.fn(),
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
  activity: null,
  merged_table: [],
};

describe("ActivityUploadPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders upload button and format select", () => {
    vi.mocked(useActivityStore).mockReturnValue(makeActivityStore());
    vi.mocked(useRoundStore).mockImplementation(
      (sel: (s: RoundSlice) => unknown) => sel(makeRoundStore([baseRound], "round_1").getState())
    );

    render(<ActivityUploadPanel />);

    expect(screen.getByRole("button", { name: /Browse & Upload/i })).toBeTruthy();
    expect(screen.getByRole("combobox")).toBeTruthy();
  });

  it("shows disabled state when no active round", () => {
    vi.mocked(useActivityStore).mockReturnValue(makeActivityStore());
    vi.mocked(useRoundStore).mockImplementation(
      (sel: (s: RoundSlice) => unknown) => sel(makeRoundStore([], null).getState())
    );

    render(<ActivityUploadPanel />);

    const btn = screen.getByRole("button", { name: /Browse & Upload/i });
    expect(btn.hasAttribute("disabled")).toBe(true);
  });

  it("shows record count after upload", () => {
    vi.mocked(useActivityStore).mockReturnValue(makeActivityStore());
    vi.mocked(useRoundStore).mockImplementation(
      (sel: (s: RoundSlice) => unknown) =>
        sel(
          makeRoundStore(
            [
              {
                ...baseRound,
                activity: {
                  records: [
                    { plate_id: "P01", well_id: "A01", value: 1.0, replicate_idx: 1, is_wt: false, source_file: "f.csv" },
                    { plate_id: "P01", well_id: "A02", value: 1.2, replicate_idx: 1, is_wt: false, source_file: "f.csv" },
                  ],
                  plate_meta: { plates: [] },
                },
              },
            ],
            "round_1"
          ).getState()
        )
    );

    render(<ActivityUploadPanel />);

    expect(screen.getByText(/2 wells loaded/i)).toBeTruthy();
  });

  it("shows upload error", () => {
    vi.mocked(useActivityStore).mockReturnValue(
      makeActivityStore({ uploadError: "Parse error: column missing" })
    );
    vi.mocked(useRoundStore).mockImplementation(
      (sel: (s: RoundSlice) => unknown) => sel(makeRoundStore([baseRound], "round_1").getState())
    );

    render(<ActivityUploadPanel />);

    expect(screen.getByRole("alert")).toBeTruthy();
    expect(screen.getByText(/Parse error: column missing/i)).toBeTruthy();
  });

  it("shows loading state while uploading", () => {
    vi.mocked(useActivityStore).mockReturnValue(
      makeActivityStore({ isUploading: true })
    );
    vi.mocked(useRoundStore).mockImplementation(
      (sel: (s: RoundSlice) => unknown) => sel(makeRoundStore([baseRound], "round_1").getState())
    );

    render(<ActivityUploadPanel />);

    expect(screen.getByRole("button", { name: /Uploading/i })).toBeTruthy();
  });

  it("calls uploadActivityFile on button click with file path", async () => {
    mockUpload.mockResolvedValueOnce(undefined);

    vi.mocked(useActivityStore).mockReturnValue(makeActivityStore());
    vi.mocked(useRoundStore).mockImplementation(
      (sel: (s: RoundSlice) => unknown) => sel(makeRoundStore([baseRound], "round_1").getState())
    );

    render(<ActivityUploadPanel />);

    fireEvent.click(screen.getByRole("button", { name: /Browse & Upload/i }));

    await waitFor(() => {
      expect(mockUpload).toHaveBeenCalledWith(
        "round_1",
        "/fake/path/activity.csv",
        "long_csv"
      );
    });
  });
});
