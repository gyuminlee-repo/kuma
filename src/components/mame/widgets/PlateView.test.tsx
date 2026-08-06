import { render, screen, fireEvent } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { create } from "zustand";
import en from "@/locales/en.json";
import type { AppState as MameAppStore } from "@/store/mame/mameAppStore";
import type { VerdictClass, WellEntry } from "@/types/mame/models";

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

function mockStore(wells: WellEntry[]) {
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
}

function setup(wells: WellEntry[]) {
  mockStore(wells);
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

const ALL_CLASSES: VerdictClass[] = [
  "PASS",
  "AMBIGUOUS",
  "MIXED",
  "WRONG_AA",
  "FRAMESHIFT",
  "MANY",
  "LOWDEPTH",
  "NO_CALL",
];

/**
 * The eight explanations, read from the locale source instead of retyped here.
 * Two consequences worth keeping: rewording a sentence (the FRAMESHIFT text was
 * wrong once) needs no test edit, and a chip wired to the wrong VERDICT_HELP_KEY
 * entry still fails, because the expectation is not derived from that same map.
 */
const HELP = en.mame.verdictBadge.help;

/** Classes absent from WELLS, rendered with count 0 and disabled. */
const ZERO_COUNT: VerdictClass[] = ["AMBIGUOUS", "FRAMESHIFT", "MANY", "LOWDEPTH", "NO_CALL"];

/** Nearest self-or-ancestor carrying a title: the element a hover reads from. */
function hoverHost(chip: HTMLElement): HTMLElement {
  const host = chip.closest("[title]");
  if (!host) throw new Error(`no titled element at or above chip ${chip.getAttribute("aria-label")}`);
  return host as HTMLElement;
}

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

  it("disables (and dims) a legend class with no matching wells", () => {
    setup(WELLS); // PASS, MIXED, WRONG_AA present — LOWDEPTH/MANY/etc. absent
    const empty = filterBtn("LOWDEPTH");
    expect(empty).toBeDisabled();
    // Clicking a disabled class does nothing — no wells get dimmed.
    fireEvent.click(empty);
    expect(empty).toHaveAttribute("aria-pressed", "false");
    expect(wellButton("A1")).not.toHaveStyle({ opacity: "0.3" });
    expect(wellButton("A2")).not.toHaveStyle({ opacity: "0.3" });
    // A present class stays enabled.
    expect(filterBtn("PASS")).toBeEnabled();
  });
});

/**
 * (D) The verdict legend explains itself on hover.
 *
 * jsdom renders no native tooltip, so the hover cannot be observed here. These
 * assert the `title` attribute the browser turns into one, and which element
 * carries it. Attribute contracts, not rendering tests. Seeing them pass says
 * nothing about whether a tooltip is legible on screen.
 *
 * Hover (not click) is the operator request for the legend; the Confidence
 * metrics are the click-opened surface. Do not collapse the two.
 */
describe("PlateView verdict legend hover help", () => {
  beforeEach(() => vi.clearAllMocks());

  it("exposes every one of the eight classes' explanation as a hover title", () => {
    setup(WELLS); // PASS / MIXED / WRONG_AA present, the other five at count 0
    for (const cls of ALL_CLASSES) {
      expect(hoverHost(filterBtn(cls))).toHaveAttribute("title", HELP[cls]);
    }
  });

  it("puts the zero-count classes' title on a hoverable wrapper, not on the disabled button", () => {
    setup(WELLS);
    for (const cls of ZERO_COUNT) {
      const chip = filterBtn(cls);
      expect(chip).toBeDisabled();
      // A disabled control dispatches no mouse events in Chromium, for itself
      // or for its descendants, so a title on the button (or on the badge
      // inside it) never surfaces, which is how the classes an operator is
      // least likely to recognise ended up being the silent ones. The title
      // has to sit on an ancestor, and the button has to stop swallowing the
      // pointer for the hover to reach that ancestor.
      expect(hoverHost(chip)).not.toBe(chip);
      expect(chip.className).toContain("pointer-events-none");
    }
  });

  it("gives every class the same explanation as an accessible description", () => {
    setup(WELLS);
    // aria-label ("Filter wells by X") wins the accessible NAME computation, so
    // the title is invisible to a screen reader. The sentence is reachable only
    // as a DESCRIPTION, via aria-describedby → sr-only span.
    for (const cls of ALL_CLASSES) {
      expect(filterBtn(cls)).toHaveAccessibleDescription(HELP[cls]);
    }
  });
});

describe("PlateView expand toggle", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders no expand button when onToggleExpand is absent", () => {
    setup(WELLS);
    expect(screen.queryByRole("button", { name: /Expand/i })).toBeNull();
  });

  it("renders Expand button (Maximize icon, aria-pressed false) and fires onToggleExpand on click", () => {
    mockStore(WELLS);
    const onToggle = vi.fn();
    render(<PlateView expanded={false} onToggleExpand={onToggle} />);
    const btn = screen.getByRole("button", { name: "Expand" });
    expect(btn).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(btn);
    expect(onToggle).toHaveBeenCalledTimes(1);
  });

  it("renders Collapse button with aria-pressed true when expanded", () => {
    mockStore(WELLS);
    const onToggle = vi.fn();
    render(<PlateView expanded onToggleExpand={onToggle} />);
    const btn = screen.getByRole("button", { name: "Collapse" });
    expect(btn).toHaveAttribute("aria-pressed", "true");
    expect(screen.queryByRole("button", { name: "Expand" })).toBeNull();
    fireEvent.click(btn);
    expect(onToggle).toHaveBeenCalledTimes(1);
  });
});
