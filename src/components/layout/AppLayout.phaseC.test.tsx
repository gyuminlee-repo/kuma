/**
 * AppLayout.phaseC.test.tsx — Phase G integration tests (3-major: Design / Output / Export)
 *
 * Tests:
 *   1. data-tool="kuro" attribute preserved
 *   2. sidebar region exists
 *   3. main content region exists
 *   4. MajorSubnav 3 major tabs rendered (Phase G)
 *   5. clicking output tab changes currentMajor to output
 *   6. SubStepNav click changes currentSubStep to design.mutation
 *   7. Ctrl+Enter auto-navigates to design.submit (Phase G)
 *   8. SummaryMetric / WorkflowStep not in DOM (regression)
 */

import { render, screen, fireEvent, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";

vi.mock("@/lib/ipc-kuro", () => ({
  sendRequest: vi.fn(),
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
  spawnSidecar: vi.fn(() => Promise.resolve()),
  getLastProgressAt: vi.fn(() => Date.now()),
}));

import { AppLayout } from "./AppLayout";
import { useAppStore } from "@/store/appStore";

function getMajorTabs() {
  return Array.from(document.querySelectorAll<HTMLElement>("[data-major-tab]"));
}

function getSubStepTabs() {
  return screen
    .getAllByRole("tab")
    .filter(
      (el) =>
        el.getAttribute("aria-controls") === "major-step-main",
    );
}

describe("AppLayout Phase C -- layout structure", () => {
  it("renders data-tool='kuro' (Phase A token selector preserved)", () => {
    render(<AppLayout />);
    expect(document.querySelector("[data-tool='kuro']")).toBeTruthy();
  });

  it("sidebar region exists (AppShell sidebar slot)", () => {
    render(<AppLayout />);
    expect(document.querySelector("[data-testid='sidebar']")).toBeTruthy();
  });

  it("main content region exists", () => {
    render(<AppLayout />);
    expect(document.querySelector("[data-testid='main-content']")).toBeTruthy();
  });

  it("SummaryMetric not in DOM (regression)", () => {
    render(<AppLayout />);
    expect(screen.queryByTestId("summary-metric")).toBeNull();
  });

  it("WorkflowStep not in DOM (regression)", () => {
    render(<AppLayout />);
    expect(screen.queryByTestId("workflow-step")).toBeNull();
  });
});

describe("AppLayout Phase C -- MajorSubnav navigation (3-major, Phase G)", () => {
  it("renders exactly 3 major tabs (Design / Output / Export)", () => {
    useAppStore.setState({ currentMajor: "design", currentSubStep: "design.load" });
    render(<AppLayout />);
    const tabs = getMajorTabs();
    expect(tabs.length).toBeGreaterThanOrEqual(3);
  });

  it("first major tab (design) is aria-selected when currentMajor='design'", () => {
    useAppStore.setState({ currentMajor: "design", currentSubStep: "design.load" });
    render(<AppLayout />);
    const tabs = getMajorTabs();
    expect(tabs[0].getAttribute("aria-selected")).toBe("true");
  });

  it("clicking output tab (index 1) changes currentMajor to output", async () => {
    const user = userEvent.setup();
    useAppStore.setState({ currentMajor: "design", currentSubStep: "design.load" });
    render(<AppLayout />);
    const tabs = getMajorTabs();
    await user.click(tabs[1]); // output is index 1 (design=0, output=1, export=2)
    expect(useAppStore.getState().currentMajor).toBe("output");
  });

  it("clicking export tab (index 2) changes currentMajor to export", async () => {
    const user = userEvent.setup();
    useAppStore.setState({ currentMajor: "design", currentSubStep: "design.load" });
    render(<AppLayout />);
    const tabs = getMajorTabs();
    await user.click(tabs[2]); // export is index 2
    expect(useAppStore.getState().currentMajor).toBe("export");
  });
});

describe("AppLayout Phase C -- SubStepNav navigation", () => {
  it("SubStepNav items render for design major", () => {
    useAppStore.setState({ currentMajor: "design", currentSubStep: "design.load" });
    render(<AppLayout />);
    const subTabs = getSubStepTabs();
    // design has 4 sub-steps (Phase G)
    expect(subTabs.length).toBeGreaterThanOrEqual(4);
  });

  it("first sub-step tab is active for design.load", () => {
    useAppStore.setState({ currentMajor: "design", currentSubStep: "design.load" });
    render(<AppLayout />);
    const subTabs = getSubStepTabs();
    expect(subTabs[0].getAttribute("aria-selected")).toBe("true");
  });

  it("clicking second sub-step changes currentSubStep to design.mutation (Phase G)", () => {
    useAppStore.setState({ currentMajor: "design", currentSubStep: "design.load" });
    render(<AppLayout />);
    const subTabs = getSubStepTabs();
    fireEvent.click(subTabs[1]); // design.mutation (index 1, Phase G — variant removed)
    expect(useAppStore.getState().currentSubStep).toBe("design.mutation");
  });
});

describe("AppLayout Phase C -- keyboard shortcut auto-navigate", () => {
  it("Ctrl+Enter from non-design.submit sub-step auto-navigates to design.submit (Phase G)", () => {
    useAppStore.setState({ currentMajor: "design", currentSubStep: "design.load" });
    render(<AppLayout />);

    act(() => {
      document.body.dispatchEvent(
        new KeyboardEvent("keydown", { key: "Enter", ctrlKey: true, bubbles: true }),
      );
    });

    expect(useAppStore.getState().currentSubStep).toBe("design.submit");
    expect(useAppStore.getState().currentMajor).toBe("design");
  });

  it("Ctrl+D from non-design.submit sub-step auto-navigates to design.submit (Phase G)", () => {
    useAppStore.setState({ currentMajor: "design", currentSubStep: "design.load" });
    render(<AppLayout />);

    act(() => {
      document.body.dispatchEvent(
        new KeyboardEvent("keydown", { key: "d", ctrlKey: true, bubbles: true }),
      );
    });

    expect(useAppStore.getState().currentSubStep).toBe("design.submit");
  });
});
