/**
 * SubStepNav.test.tsx — sub-step 클릭 + badge status 어설션
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

const VARIANT_SUBSTEPS: SubNavItem[] = [
  { id: "variant.load",     labelKey: "phaseC.subSteps.variant.load" },
  { id: "variant.select",   labelKey: "phaseC.subSteps.variant.select" },
  { id: "variant.adaptive", labelKey: "phaseC.subSteps.variant.adaptive" },
  { id: "variant.domain",   labelKey: "phaseC.subSteps.variant.domain" },
  { id: "variant.pareto",   labelKey: "phaseC.subSteps.variant.pareto" },
];

describe("SubStepNav", () => {
  beforeEach(() => {
    useAppStore.setState({
      currentMajor: "variant",
      currentSubStep: "variant.load",
      stepStatus: Object.fromEntries(
        ["variant.load", "variant.select", "variant.adaptive", "variant.domain", "variant.pareto",
         "sdm.mutations", "sdm.codon", "sdm.polymerase", "sdm.gc", "sdm.run",
         "plate.size", "plate.layout", "plate.labels",
         "export.format", "export.summary", "export.workspace"].map((id) => [
          id,
          { done: false, reachable: true },
        ]),
      ),
    });
  });

  it("renders 5 sub-step tabs", () => {
    render(<SubStepNav major="variant" subSteps={VARIANT_SUBSTEPS} />);
    const tabs = screen.getAllByRole("tab");
    expect(tabs).toHaveLength(5);
  });

  it("first tab is aria-selected when currentSubStep=variant.load", () => {
    render(<SubStepNav major="variant" subSteps={VARIANT_SUBSTEPS} />);
    const tabs = screen.getAllByRole("tab");
    expect(tabs[0].getAttribute("aria-selected")).toBe("true");
    expect(tabs[1].getAttribute("aria-selected")).toBe("false");
  });

  it("clicking variant.select changes currentSubStep", () => {
    render(<SubStepNav major="variant" subSteps={VARIANT_SUBSTEPS} />);
    const tabs = screen.getAllByRole("tab");
    fireEvent.click(tabs[1]); // variant.select
    expect(useAppStore.getState().currentSubStep).toBe("variant.select");
  });

  it("active badge (index=1) for first sub-step by default", () => {
    render(<SubStepNav major="variant" subSteps={VARIANT_SUBSTEPS} />);
    // First tab should show active badge with index "1"
    // StepBadge active renders the index number
    const badge = screen.getAllByText("1");
    expect(badge.length).toBeGreaterThan(0);
  });

  it("done badge shown when stepStatus.done=true", () => {
    useAppStore.setState((s) => ({
      stepStatus: {
        ...s.stepStatus,
        "variant.load": { done: true, reachable: true },
      },
    }));
    render(<SubStepNav major="variant" subSteps={VARIANT_SUBSTEPS} />);
    // StepBadge done renders "DONE" text (i18n key phaseC.badge.done)
    expect(screen.getByText("DONE")).toBeTruthy();
  });

  it("pending badges rendered for non-active non-done steps", () => {
    render(<SubStepNav major="variant" subSteps={VARIANT_SUBSTEPS} />);
    // Steps 2-5 should be pending; their indices 2,3,4,5 should appear
    expect(screen.getByText("2")).toBeTruthy();
    expect(screen.getByText("3")).toBeTruthy();
  });
});
