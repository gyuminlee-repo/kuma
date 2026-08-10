/**
 * RunQualityNotice, the statement that stands above the verdict table.
 *
 * Three states, three different claims, and the silent one matters as much as
 * the loud one: a clean run must render nothing, or the notice becomes furniture
 * and the shallow run it exists for scrolls past unread.
 *
 * On wording vs content. The prose lives in the locale files and is edited
 * independently, so nothing here pins a sentence. What is pinned is the
 * severity that reaches the DOM, the numbers, and two copy-edit-proof guards:
 * `i18n-lint` proves a key exists and `i18n-parity` compares key SETS, so a
 * placeholder renamed on one side of `t(...)` ships a literal `{{floor}}` to the
 * operator with every gate green.
 */
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/ipc-mame", () => ({
  sendRequest: vi.fn(),
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
}));

import type { RunQuality } from "@/types/mame/run_quality";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import { RunQualityNotice } from "./RunQualityNotice";

/** The thresholds block, as the sidecar sends it. */
const THRESHOLDS: RunQuality["thresholds"] = {
  floor: {
    value: 30,
    source: "ONT wf-amplicon minimum_mean_depth default",
    kind: "vendor_default",
    provisional: true,
  },
  recommended: {
    value: 1500,
    source: "ONT wf-amplicon: >150X, 1500 reads per amplicon",
    kind: "vendor_recommendation",
    provisional: false,
  },
};

function quality(patch: Partial<RunQuality> = {}): RunQuality {
  return {
    severity: null,
    median_well_reads: 4777,
    min_read_count: 30,
    depth_ok: true,
    wells_under_floor: 0,
    wells_total: 96,
    recommended_reads: 1500,
    flow_cell_id: "FBF10847",
    pore_start: 1150,
    pore_end: 975,
    pore_warranty_min: 800,
    reused_from: null,
    thresholds: THRESHOLDS,
    findings: [],
    ...patch,
  };
}

describe("RunQualityNotice", () => {
  beforeEach(() => {
    useMameAppStore.setState({ runQuality: null });
  });

  it("says nothing for the run that worked", () => {
    // 02-12: 4777 reads a well, clean, pores fell 1150 to 975 as they do.
    useMameAppStore.setState({ runQuality: quality() });

    render(<RunQualityNotice />);

    expect(screen.queryByTestId("run-quality-notice")).toBeNull();
  });

  it("says nothing when no run has reported quality", () => {
    render(<RunQualityNotice />);

    expect(screen.queryByTestId("run-quality-notice")).toBeNull();
  });

  it("raises an alert for the shallow plate and names the numbers", () => {
    // 08-04: four reads a well on a re-used cell that started at 40 pores.
    useMameAppStore.setState({
      runQuality: quality({
        severity: "blocking",
        median_well_reads: 4,
        depth_ok: false,
        wells_under_floor: 96,
        flow_cell_id: "FBF91250",
        pore_start: 40,
        pore_end: 42,
        reused_from: { run_dir: "/runs/20260729", pore_end: 188 },
        findings: [
          { code: "median_depth_below_floor", severity: "blocking" },
          { code: "flow_cell_reused", severity: "warning" },
        ],
      }),
    });

    render(<RunQualityNotice />);

    const notice = screen.getByTestId("run-quality-notice");
    expect(notice).toHaveAttribute("data-severity", "blocking");
    // An alert role, not a status: this one must interrupt.
    expect(notice.getAttribute("role")).toBe("alert");
    expect(notice).toHaveTextContent("4");
    expect(notice).toHaveTextContent("30");
    expect(notice).toHaveTextContent("96");
    // The cell and its history, so the cause is on screen beside the effect.
    expect(notice).toHaveTextContent("FBF91250");
    expect(notice).toHaveTextContent("40");
    expect(notice).toHaveTextContent("188");
    // Copy-edit-proof: no unresolved placeholder, no raw key echoed back.
    expect(notice.textContent).not.toContain("{{");
    expect(notice.textContent).not.toContain("mame.runQuality.");
  });

  it("states that the floor is a vendor default held provisionally", () => {
    // The whole point of carrying provenance: a workflow default must not read
    // as a specification, which is the overstatement this project already made
    // once in a code comment.
    useMameAppStore.setState({
      runQuality: quality({
        severity: "blocking",
        median_well_reads: 4,
        depth_ok: false,
        wells_under_floor: 96,
        findings: [{ code: "median_depth_below_floor", severity: "blocking" }],
      }),
    });

    render(<RunQualityNotice />);

    const notice = screen.getByTestId("run-quality-notice");
    expect(notice).toHaveTextContent("minimum_mean_depth");
    expect(notice).toHaveTextContent("1500");
  });

  it("keeps the under-powered run quiet rather than alarming", () => {
    // 07-29: 515 reads a well, over the floor and under the recommendation, on
    // a cell that started at 343 pores. Scorable, and worth knowing about.
    useMameAppStore.setState({
      runQuality: quality({
        severity: "warning",
        median_well_reads: 515,
        flow_cell_id: "FBF91250",
        pore_start: 343,
        pore_end: 188,
        findings: [
          { code: "median_depth_below_recommended", severity: "warning" },
        ],
      }),
    });

    render(<RunQualityNotice />);

    const notice = screen.getByTestId("run-quality-notice");
    expect(notice).toHaveAttribute("data-severity", "warning");
    expect(notice.getAttribute("role")).toBe("status");
    expect(notice).toHaveTextContent("515");
    expect(notice).toHaveTextContent("1500");
    expect(notice.textContent).not.toContain("{{");
  });
});
