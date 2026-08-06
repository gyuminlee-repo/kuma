/**
 * The rule this panel exists to keep: an unavailable signal shows its reason,
 * never a zero. So the cases here are the ones that separate those two states,
 * including the pair that a "render `value ?? 0`" implementation would collapse
 * into the same output.
 */
import { render, screen, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/ipc-mame", () => ({
  sendRequest: vi.fn(),
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
}));

import { useMameAppStore } from "@/store/mame/mameAppStore";
import type { ContaminationReport, ContaminationSignal } from "@/types/mame/models";
import { ContaminationPanel } from "./ContaminationPanel";

afterEach(cleanup);

const UNAVAILABLE: ContaminationSignal = {
  state: "unavailable",
  reason: "this run pooled its reads into one plate",
};

function report(overrides: Partial<ContaminationReport["signals"]> = {}): ContaminationReport {
  return {
    occupancy_source: "inferred_draft_layout",
    occupied_wells: 48,
    replicates: 3,
    plate_names: ["sort_barcode01", "sort_barcode02", "sort_barcode03"],
    signals: {
      unused_index_reads: { state: "ok", value: 55, wells: [{ well: "A09", reads: 55 }] },
      unexpected_well_reads: { state: "ok", value: 20, wells: [{ well: "A03", reads: 20 }] },
      ambiguity_rate: { state: "ok", value: 0.125 },
      chimera_rate: { state: "ok", value: 0.04 },
      leak_well_sharing: {
        state: "ok",
        value: 2,
        label: "shared_across_replicates",
        wells: [{ well: "A03", reads: 20, replicates_with_reads: 3 }],
      },
      plate_yield_skew: { state: "ok", value: 0.25 },
      ...overrides,
    },
  };
}

describe("ContaminationPanel", () => {
  it("renders nothing when the run could not measure it", () => {
    // Same null for "no run yet" and "a consensus-dir run, which never
    // demuxed": neither is a clean plate, and neither has a panel to draw.
    useMameAppStore.setState({ contamination: null });

    render(<ContaminationPanel />);

    expect(screen.queryAllByTestId("contamination-panel")).toHaveLength(0);
  });

  it("shows a measured count and the wells it came from", () => {
    useMameAppStore.setState({ contamination: report() });

    render(<ContaminationPanel />);

    const panel = screen.getByTestId("contamination-panel");
    expect(panel).toHaveAttribute("data-occupancy-source", "inferred_draft_layout");
    const row = screen.getByTestId("contamination-signal-unexpected_well_reads");
    expect(row).toHaveAttribute("data-state", "ok");
    expect(row.textContent).toContain("20");
    expect(row.textContent).toContain("A03");
  });

  it("shows the reason instead of a number when a signal is unavailable", () => {
    useMameAppStore.setState({
      contamination: report({ leak_well_sharing: UNAVAILABLE }),
    });

    render(<ContaminationPanel />);

    const row = screen.getByTestId("contamination-signal-leak_well_sharing");
    expect(row).toHaveAttribute("data-state", "unavailable");
    expect(row.textContent).toContain("pooled its reads into one plate");
    expect(row.textContent).not.toContain("0");
  });

  it("keeps a measured zero and an unavailable signal visibly different", () => {
    // The case an implementation reading `value ?? 0` cannot distinguish: one
    // says "we looked and found none", the other says "we could not look".
    useMameAppStore.setState({
      contamination: report({
        unexpected_well_reads: { state: "ok", value: 0 },
        unused_index_reads: UNAVAILABLE,
      }),
    });

    render(<ContaminationPanel />);

    const measured = screen.getByTestId("contamination-signal-unexpected_well_reads");
    const unavailable = screen.getByTestId("contamination-signal-unused_index_reads");
    expect(measured.textContent).toContain("0");
    expect(unavailable.textContent).not.toContain("0");
    expect(unavailable.textContent).toContain("pooled its reads into one plate");
  });

  it("renders every signal the contract names, in order", () => {
    useMameAppStore.setState({ contamination: report() });

    render(<ContaminationPanel />);

    for (const name of [
      "unused_index_reads",
      "unexpected_well_reads",
      "ambiguity_rate",
      "chimera_rate",
      "leak_well_sharing",
      "plate_yield_skew",
    ]) {
      expect(screen.getByTestId(`contamination-signal-${name}`)).toBeTruthy();
    }
  });
});
