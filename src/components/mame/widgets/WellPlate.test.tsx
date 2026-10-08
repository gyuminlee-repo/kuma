import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { WellEntry } from "@/types/mame/models";
import { WellPlate } from "./WellPlate";

function rec(
  well: string,
  nativeBarcode: string,
  verdict: WellEntry["verdict"],
  selected: boolean,
): WellEntry {
  return {
    well,
    barcode: "1_1",
    native_barcode: nativeBarcode,
    verdict,
    mutant_id: well,
    selected,
    notes: "",
    is_fallback: false,
    fallback_reason: null,
  };
}

describe("WellPlate per-well collapse", () => {
  it("shows the selected (winning) replicate per well, not the last native barcode", () => {
    // Same well position A1 sequenced across 3 replicates; NB13 is the winner.
    const wells = [
      rec("A1", "sort_barcode06", "WRONG_AA", false),
      rec("A1", "sort_barcode13", "PASS", true),
      rec("A1", "sort_barcode20", "AMBIGUOUS", false),
    ];
    render(<WellPlate wells={wells} />);

    // Badge reflects the winning native barcode (NB13), not the last (NB20).
    expect(screen.getByText("NB13")).toBeTruthy();
    expect(screen.queryByText("NB20")).toBeNull();
    expect(screen.queryByText("NB06")).toBeNull();
    // A1 cell verdict is the winner's PASS, not WRONG_AA/AMBIGUOUS.
    expect(screen.getByLabelText(/^Well A1: PASS$/)).toBeTruthy();
  });

  it("keeps the last-seen record when no replicate at a position is selected", () => {
    const wells = [
      rec("B2", "sort_barcode06", "WRONG_AA", false),
      rec("B2", "sort_barcode13", "MANY", false),
    ];
    render(<WellPlate wells={wells} />);
    // Last-seen record wins the cell (verdict MANY from NB13).
    expect(screen.getByLabelText(/^Well B2: MANY$/)).toBeTruthy();
  });
});

describe("WellPlate NB badge gating", () => {
  it("does not render an NB badge for fail wells", () => {
    const wells = [
      rec("A1", "sort_barcode06", "WRONG_AA", true), // fail (selected pick still fail)
      rec("A2", "sort_barcode13", "LOWDEPTH", false),
      rec("A3", "sort_barcode20", "PASS", true), // detected → badge
      rec("A4", "sort_barcode02", "AMBIGUOUS", false), // detected → badge
    ];
    render(<WellPlate wells={wells} />);
    // Fail wells: no NB badge.
    expect(screen.queryByText("NB06")).toBeNull();
    expect(screen.queryByText("NB13")).toBeNull();
    // Detected wells (PASS/AMBIGUOUS): NB badge shown.
    expect(screen.getByText("NB20")).toBeTruthy();
    expect(screen.getByText("NB02")).toBeTruthy();
  });
});
