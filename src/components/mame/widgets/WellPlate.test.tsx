import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { WellEntry } from "@/types/mame/models";
import { WellPlate } from "./WellPlate";
import { copiesByWell } from "@/lib/mame/plateWells";
import { VERDICT_FILL } from "@/lib/mame/verdictColors";

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

describe("WellPlate copy strip", () => {
  const cell = (id: string) => screen.getByLabelText(new RegExp(`^Well ${id}: `));

  it("draws one segment per copy in plate order, coloured by verdict, with the pick marked", () => {
    const wells = [
      rec("A1", "sort_barcode09", "AMBIGUOUS", false),
      rec("A1", "sort_barcode07", "WRONG_AA", false),
      rec("A1", "sort_barcode08", "PASS", true),
    ];
    render(<WellPlate wells={wells} copies={copiesByWell(wells)} />);
    const segs = cell("A1").querySelectorAll<HTMLElement>('[data-testid="copy-segment"]');
    expect([...segs].map((s) => s.dataset.plate)).toEqual([
      "sort_barcode07",
      "sort_barcode08",
      "sort_barcode09",
    ]);
    expect([...segs].map((s) => s.dataset.selected)).toEqual(["false", "true", "false"]);
    expect(segs[0]).toHaveStyle({ backgroundColor: VERDICT_FILL.WRONG_AA.bg });
    expect(segs[1]).toHaveStyle({ backgroundColor: VERDICT_FILL.PASS.bg });
    // The strip sits in normal flow as the last child, so it cannot cover the badge row.
    const strip = cell("A1").querySelector('[data-testid="copy-strip"]');
    expect(strip?.parentElement?.lastElementChild).toBe(strip);
  });

  it("lists every copy in the accessible label and the tooltip", () => {
    const wells = [rec("A1", "sort_barcode07", "WRONG_AA", false), rec("A1", "sort_barcode08", "PASS", true)];
    render(<WellPlate wells={wells} copies={copiesByWell(wells)} />);
    expect(cell("A1").getAttribute("aria-label")).toBe(
      "Well A1: PASS; NB07 WRONG_AA, NB08 PASS (selected)",
    );
    expect(cell("A1").querySelector("button")?.title).toContain("NB07 WRONG_AA\nNB08 PASS (selected)");
  });

  it("adds nothing for a single-copy well", () => {
    const wells = [rec("A1", "sort_barcode07", "PASS", true)];
    render(<WellPlate wells={wells} copies={copiesByWell(wells)} />);
    expect(cell("A1").querySelector('[data-testid="copy-strip"]')).toBeNull();
    expect(cell("A1").querySelector('[data-testid="copy-count"]')).toBeNull();
  });

  it("falls back to a count above four copies", () => {
    const wells = [6, 7, 8, 9, 10].map((n) =>
      rec("A1", `sort_barcode${String(n).padStart(2, "0")}`, "PASS", n === 6),
    );
    render(<WellPlate wells={wells} copies={copiesByWell(wells)} />);
    expect(cell("A1").querySelector('[data-testid="copy-segment"]')).toBeNull();
    const count = cell("A1").querySelector('[data-testid="copy-count"]');
    expect(count?.textContent).toBe("×5");
    // The count lives inside the badge row (a child of a wrapper), not directly on the cell.
    expect(count?.closest("button")).not.toBe(count?.parentElement);
  });

  it("marks the viewed copy separately from the winner, only in the focused well", () => {
    const wells = [
      { ...rec("A1", "sort_barcode07", "WRONG_AA", false), barcode: "b07" },
      { ...rec("A1", "sort_barcode08", "PASS", true), barcode: "b08" },
      { ...rec("A2", "sort_barcode07", "PASS", true), barcode: "b07" },
      { ...rec("A2", "sort_barcode08", "PASS", false), barcode: "b08" },
    ];
    render(
      <WellPlate wells={wells} copies={copiesByWell(wells)} selectedWellId="A1" viewedKey="sort_barcode07|b07" />,
    );
    const a1 = [...cell("A1").querySelectorAll<HTMLElement>('[data-testid="copy-segment"]')];
    expect(a1.map((s) => s.dataset.viewed)).toEqual(["true", "false"]);
    expect(a1.map((s) => s.dataset.selected)).toEqual(["false", "true"]);
    // The same copy key in another well is not marked.
    const a2 = [...cell("A2").querySelectorAll<HTMLElement>('[data-testid="copy-segment"]')];
    expect(a2.map((s) => s.dataset.viewed)).toEqual(["false", "false"]);
  });
});
