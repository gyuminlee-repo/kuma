import { render, screen, fireEvent } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { create } from "zustand";
import type { RoundSlice } from "@/store/round/roundSlice";
import type { Round } from "@/types/round";

vi.mock("@/store/round/roundSlice");

import { useRoundStore } from "@/store/round/roundSlice";
import { RoundHandoffButton } from "./RoundHandoffButton";

const mockHandoff = vi.fn().mockReturnValue(null);

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

function makeRoundStore(rounds: Round[] = [], activeId: string | null = null) {
  return create<RoundSlice>()(() => ({
    rounds,
    active_round_id: activeId,
    addRound: vi.fn(),
    transitionStatus: vi.fn(),
    setActiveRound: vi.fn(),
    updateRoundField: vi.fn(),
    handoffNextRound: mockHandoff,
  }));
}

describe("RoundHandoffButton", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders button with correct round number label", () => {
    vi.mocked(useRoundStore).mockImplementation(
      (sel: (s: RoundSlice) => unknown) =>
        sel(makeRoundStore([baseRound], "round_1").getState())
    );

    render(<RoundHandoffButton round_id="round_1" />);

    expect(screen.getByRole("button", { name: /Start Round 2/i })).toBeTruthy();
  });

  it("is disabled when merged_table is empty", () => {
    vi.mocked(useRoundStore).mockImplementation(
      (sel: (s: RoundSlice) => unknown) =>
        sel(makeRoundStore([baseRound], "round_1").getState())
    );

    render(<RoundHandoffButton round_id="round_1" />);

    const btn = screen.getByRole("button", { name: /Start Round 2/i });
    expect(btn.hasAttribute("disabled")).toBe(true);
  });

  it("is disabled when round not found", () => {
    vi.mocked(useRoundStore).mockImplementation(
      (sel: (s: RoundSlice) => unknown) =>
        sel(makeRoundStore([], null).getState())
    );

    render(<RoundHandoffButton round_id="round_99" />);

    const btn = screen.getByRole("button");
    expect(btn.hasAttribute("disabled")).toBe(true);
  });

  it("is enabled when merged_table has rows", () => {
    const roundWithData: Round = {
      ...baseRound,
      merged_table: [
        {
          plate_id: "P01",
          well_id: "A01",
          mutation: "F89W",
          mutation_source: "kuro_design",
          expected_mutation: "F89W",
          called_mutation: "F89W",
          ngs_success: true,
          activity_raw_mean: 2.0,
          activity_raw_sd: 0.1,
          activity_replicates: [1.9, 2.1],
          replicate_n: 2,
          fold_change: 2.0,
          log2_fc: 1.0,
        },
      ],
    };

    vi.mocked(useRoundStore).mockImplementation(
      (sel: (s: RoundSlice) => unknown) =>
        sel(makeRoundStore([roundWithData], "round_1").getState())
    );

    render(<RoundHandoffButton round_id="round_1" />);

    const btn = screen.getByRole("button", { name: /Start Round 2/i });
    expect(btn.hasAttribute("disabled")).toBe(false);
  });

  it("calls handoffNextRound with round_id on click", () => {
    const roundWithData: Round = {
      ...baseRound,
      merged_table: [
        {
          plate_id: "P01",
          well_id: "B01",
          mutation: "L70V",
          mutation_source: "kuro_design",
          expected_mutation: "L70V",
          called_mutation: "L70V",
          ngs_success: true,
          activity_raw_mean: 1.5,
          activity_raw_sd: 0.05,
          activity_replicates: [1.45, 1.55],
          replicate_n: 2,
          fold_change: 1.5,
          log2_fc: 0.58,
        },
      ],
    };

    vi.mocked(useRoundStore).mockImplementation(
      (sel: (s: RoundSlice) => unknown) =>
        sel(makeRoundStore([roundWithData], "round_1").getState())
    );

    render(<RoundHandoffButton round_id="round_1" />);

    fireEvent.click(screen.getByRole("button", { name: /Start Round 2/i }));

    expect(mockHandoff).toHaveBeenCalledWith("round_1");
  });
});
