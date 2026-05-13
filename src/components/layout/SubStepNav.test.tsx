/**
 * SubStepNav.test.tsx — Phase G: sub-step 클릭 + badge status 어설션
 * [source: spec Phase G — Design 4 sub-step 재배치 (design.variant 제거, design.submit 신규)]
 */

import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("@/lib/ipc-kuro", () => ({
  sendRequest: vi.fn(),
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
}));

import { SubStepNav } from "./SubStepNav";
import { useAppStore } from "@/store/appStore";
import type { SubNavItem } from "./SubStepNav";
import type { SubStepId, StepStatus } from "@/store/slices/navigationSlice";

const DESIGN_SUBSTEPS: SubNavItem[] = [
  { id: "design.load",     labelKey: "phaseC.subSteps.design.load" },
  { id: "design.mutation", labelKey: "phaseC.subSteps.design.mutation" },
  { id: "design.params",   labelKey: "phaseC.subSteps.design.params" },
  { id: "design.submit",   labelKey: "phaseC.subSteps.design.submit" },
];

const ALL_SUB_STEPS: SubStepId[] = [
  "design.load", "design.mutation", "design.params", "design.submit",
  "output.summary",
  "export.all",
];

function makeStepStatus(overrides?: Partial<Record<SubStepId, StepStatus>>): Record<SubStepId, StepStatus> {
  const base = Object.fromEntries(
    ALL_SUB_STEPS.map((id) => [id, { done: false, reachable: true }]),
  ) as Record<SubStepId, StepStatus>;
  return { ...base, ...overrides };
}

describe("SubStepNav (Phase G)", () => {
  beforeEach(() => {
    useAppStore.setState({
      currentMajor: "design",
      currentSubStep: "design.load",
      stepStatus: makeStepStatus(),
    });
  });

  it("renders 4 sub-step tabs for design", () => {
    render(<SubStepNav major="design" subSteps={DESIGN_SUBSTEPS} />);
    const tabs = screen.getAllByRole("tab");
    expect(tabs).toHaveLength(4);
  });

  it("first tab is aria-selected when currentSubStep=design.load", () => {
    render(<SubStepNav major="design" subSteps={DESIGN_SUBSTEPS} />);
    const tabs = screen.getAllByRole("tab");
    expect(tabs[0].getAttribute("aria-selected")).toBe("true");
    expect(tabs[1].getAttribute("aria-selected")).toBe("false");
  });

  it("clicking design.mutation changes currentSubStep", () => {
    render(<SubStepNav major="design" subSteps={DESIGN_SUBSTEPS} />);
    const tabs = screen.getAllByRole("tab");
    fireEvent.click(tabs[1]); // design.mutation
    expect(useAppStore.getState().currentSubStep).toBe("design.mutation");
  });

  it("clicking design.submit changes currentSubStep", () => {
    render(<SubStepNav major="design" subSteps={DESIGN_SUBSTEPS} />);
    const tabs = screen.getAllByRole("tab");
    fireEvent.click(tabs[3]); // design.submit
    expect(useAppStore.getState().currentSubStep).toBe("design.submit");
  });

  it("active badge (index=1) for first sub-step by default", () => {
    render(<SubStepNav major="design" subSteps={DESIGN_SUBSTEPS} />);
    const badge = screen.getAllByText("1");
    expect(badge.length).toBeGreaterThan(0);
  });

  it("done badge shown when stepStatus.done=true", () => {
    useAppStore.setState((_s) => ({
      stepStatus: makeStepStatus({ "design.load": { done: true, reachable: true } }),
    }));
    render(<SubStepNav major="design" subSteps={DESIGN_SUBSTEPS} />);
    expect(screen.getByText("DONE")).toBeTruthy();
  });

  it("pending badges rendered for non-active non-done steps", () => {
    render(<SubStepNav major="design" subSteps={DESIGN_SUBSTEPS} />);
    expect(screen.getByText("2")).toBeTruthy();
    expect(screen.getByText("3")).toBeTruthy();
  });
});
