import { render, screen, fireEvent } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { create } from "zustand";
import en from "@/locales/en.json";
import type { AppState as MameAppStore } from "@/store/mame/mameAppStore";
import type { VerdictClass, VerdictRecord, WellEntry } from "@/types/mame/models";

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

function mockStore(wells: WellEntry[], extra: Partial<MameAppStore> = {}) {
  vi.mocked(useMameAppStore).mockImplementation(
    (sel: (s: MameAppStore) => unknown) =>
      sel(
        create<MameAppStore>()(
          () =>
            ({
              verdicts: [],
              wells,
              selectedWell: null,
              replicates: [],
              setSelectedWell: vi.fn(),
              loadPlateData: vi.fn(),
              ...extra,
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

describe("PlateView selected well read at designed site", () => {
  beforeEach(() => vi.clearAllMocks());

  const LABEL = en.mame.verdictDetail.labelReadAtSite;

  function verdict(nativeBarcode: string, overrides: Partial<VerdictRecord> = {}): VerdictRecord {
    return {
      native_barcode: nativeBarcode,
      custom_barcode: "1_1",
      file_size_kb: 100,
      read_count: 500,
      n_mixed_positions: 0,
      max_minor_allele_fraction: 0,
      n_low_depth_positions: 0,
      consensus_n_fraction: 0,
      n_low_quality_bases: 0,
      n_input_reads: 500,
      n_aligned_reads: 490,
      n_mapq_failed: 0,
      n_span_failed: 0,
      source_path: "",
      aa_sequence: "",
      observed_nt_changes: [],
      observed_aa_changes: [],
      n_no_call_aa: 0,
      expected_mutations: ["L187G"],
      mutant_id: "L187G",
      verdict: "WRONG_AA",
      verdict_notes: "",
      ...overrides,
    };
  }

  /** The value cell of the DetailRow whose label is `label`. */
  function detailValue(label: string): string | null {
    const labelEl = screen.queryByText(label);
    return labelEl?.nextElementSibling?.textContent ?? null;
  }

  it("shows what this exact copy read at each designed site", () => {
    const selected = well("A3", "WRONG_AA");
    mockStore(WELLS, {
      selectedWell: selected,
      verdicts: [
        // Same custom barcode on another plate: must not be the one read.
        verdict("barcode02", {
          expected_site_reads: [{ label: "L187G", position: 187, read: "no call" }],
        }),
        verdict("barcode01", {
          expected_mutations: ["L187G", "A50T"],
          expected_site_reads: [
            { label: "L187G", position: 187, read: "WT" },
            { label: "A50T", position: 50, read: "A50S" },
          ],
        }),
      ],
    });
    render(<PlateView />);
    expect(detailValue(LABEL)).toBe("L187G: WT, A50T: A50S");
  });

  it("adds no row for a record that predates the field", () => {
    mockStore(WELLS, {
      selectedWell: well("A3", "WRONG_AA"),
      verdicts: [verdict("barcode01")],
    });
    render(<PlateView />);
    expect(screen.queryByText(LABEL)).toBeNull();
    // The rest of the aside still renders.
    expect(screen.getByText(en.mame.plateView.detailNotes)).toBeInTheDocument();
  });
});
