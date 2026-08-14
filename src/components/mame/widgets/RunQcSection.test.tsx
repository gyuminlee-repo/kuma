import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import en from "@/locales/en.json";
import type { RunHealthData } from "@/types/mame/models";
import { RunQcSection } from "./RunQcSection";

function makeHealth(overrides: Partial<RunHealthData> = {}): RunHealthData {
  return {
    per_plate_summary: {},
    file_size_distribution: { min: 10, p05: 12, p25: 20, median: 40, p75: 60, p95: 80, max: 90 },
    suggested_cutoff_kb: 50,
    bimodal: false,
    suggested_method: "p05",
    pore_yield_pct: null,
    throughput_timeline: null,
    barcode_distribution: null,
    cross_talk_candidates: [],
    recovered_mutants: 0,
    total_mutants: 0,
    recovery_rate: 0,
    ...overrides,
  };
}

/** The disclosure renders its children only while open, so open it first. */
function open() {
  fireEvent.click(screen.getByRole("button", { name: en.mame.runHealth.qcSectionAriaLabel }));
}

describe("RunQcSection", () => {
  it("starts collapsed so the verdict table keeps the screen", () => {
    render(<RunQcSection runHealth={makeHealth()} />);

    const toggle = screen.getByRole("button", {
      name: en.mame.runHealth.qcSectionAriaLabel,
    });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByTestId("run-qc-section")).not.toBeInTheDocument();
  });

  it("shows the five non-verdict health sections once opened", () => {
    render(<RunQcSection runHealth={makeHealth({ pore_yield_pct: 42.5 })} />);
    open();

    const block = screen.getByTestId("run-qc-health");
    expect(block).toHaveAttribute("data-state", "present");
    // File size and pore yield are two of the five; the verdict breakdown is
    // not among them, it is drawn beside the plate.
    expect(screen.getByText("42.5%")).toBeInTheDocument();
    expect(screen.queryByTestId("run-health-class-counts")).not.toBeInTheDocument();
  });

  it("says why the health block is missing rather than drawing nothing", () => {
    render(<RunQcSection runHealth={null} />);
    open();

    const block = screen.getByTestId("run-qc-health");
    expect(block).toHaveAttribute("data-state", "unavailable");
    expect(block.textContent ?? "").toContain(en.mame.runHealth.qcHealthAbsent);
  });

  it("leaks no interpolation placeholder and no raw key", () => {
    render(<RunQcSection runHealth={makeHealth()} />);
    open();

    const text = screen.getByTestId("run-qc-section").textContent ?? "";
    expect(text).not.toContain("{{");
    expect(text).not.toContain("mame.");
  });
});
