import { render, screen, fireEvent } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { create } from "zustand";
import type { AppState as MameAppStore } from "@/store/mame/mameAppStore";
import type { WellEntry } from "@/types/mame/models";

vi.mock("@/store/mame/mameAppStore");

import { useMameAppStore } from "@/store/mame/mameAppStore";
import { PlateView } from "./PlateView";

function well(w: string, verdict: WellEntry["verdict"]): WellEntry {
  return {
    well: w,
    barcode: "1_1",
    native_barcode: "barcode01",
    verdict,
    mutant_id: w,
    selected: false,
    notes: "",
    is_fallback: false,
    fallback_reason: null,
  };
}

function setup(wells: WellEntry[]) {
  vi.mocked(useMameAppStore).mockImplementation(
    (sel: (s: MameAppStore) => unknown) =>
      sel(
        create<MameAppStore>()(
          () =>
            ({
              verdicts: [],
              wells,
              selectedWell: null,
              setSelectedWell: vi.fn(),
              loadPlateData: vi.fn(),
            }) as unknown as MameAppStore,
        ).getState(),
      ),
  );
  render(<PlateView />);
}

/** The dimmable element is the <button> inside the gridcell labelled "Well <id>: ...". */
function wellButton(id: string): HTMLElement {
  const cell = screen.getByLabelText(new RegExp(`^Well ${id}: `));
  const btn = cell.querySelector("button");
  if (!btn) throw new Error(`no button for ${id}`);
  return btn;
}

const filterBtn = (cls: string) =>
  screen.getByRole("button", { name: new RegExp(`Filter wells by ${cls}`, "i") });

const WELLS = [well("A1", "PASS"), well("A2", "MIXED"), well("A3", "WRONG_AA")];

describe("PlateView legend filter", () => {
  beforeEach(() => vi.clearAllMocks());

  it("legend items are toggle buttons (aria-pressed, default false)", () => {
    setup(WELLS);
    expect(filterBtn("PASS")).toHaveAttribute("aria-pressed", "false");
  });

  it("clicking a class dims non-matching wells and keeps matching ones", () => {
    setup(WELLS);
    fireEvent.click(filterBtn("PASS"));
    expect(filterBtn("PASS")).toHaveAttribute("aria-pressed", "true");
    expect(wellButton("A1")).not.toHaveStyle({ opacity: "0.3" }); // PASS — kept
    expect(wellButton("A2")).toHaveStyle({ opacity: "0.3" }); // MIXED — dimmed
    expect(wellButton("A3")).toHaveStyle({ opacity: "0.3" }); // WRONG_AA — dimmed
  });

  it("re-clicking the same class clears the filter (all undimmed)", () => {
    setup(WELLS);
    fireEvent.click(filterBtn("PASS"));
    fireEvent.click(filterBtn("PASS"));
    expect(filterBtn("PASS")).toHaveAttribute("aria-pressed", "false");
    expect(wellButton("A1")).not.toHaveStyle({ opacity: "0.3" });
    expect(wellButton("A2")).not.toHaveStyle({ opacity: "0.3" });
    expect(wellButton("A3")).not.toHaveStyle({ opacity: "0.3" });
  });

  it("MIXED filter is class-precise (dims PASS and the same-shape WRONG_AA)", () => {
    setup(WELLS);
    fireEvent.click(filterBtn("MIXED"));
    expect(wellButton("A2")).not.toHaveStyle({ opacity: "0.3" }); // MIXED — kept
    expect(wellButton("A1")).toHaveStyle({ opacity: "0.3" }); // PASS — dimmed
    expect(wellButton("A3")).toHaveStyle({ opacity: "0.3" }); // WRONG_AA — dimmed
  });
});
