/**
 * AppLayout.phaseC.test.tsx — Phase C integration tests (D1.1: 4-major)
 *
 * Tests:
 *   1. data-tool="kuro" attribute preserved
 *   2. sidebar region exists
 *   3. main content region exists
 *   4. MajorSubnav 4 major tabs rendered
 *   5. clicking plate tab changes currentMajor to plate
 *   6. SubStepNav click changes currentSubStep
 *   7. Ctrl+Enter auto-navigates to design.params
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

describe("AppLayout Phase C -- MajorSubnav navigation (4-major)", () => {
  it("renders at least 4 major tabs", () => {
    useAppStore.setState({ currentMajor: "design", currentSubStep: "design.load" });
    render(<AppLayout />);
    const tabs = getMajorTabs();
    expect(tabs.length).toBeGreaterThanOrEqual(4);
  });

  it("first major tab (design) is aria-selected when currentMajor='design'", () => {
    useAppStore.setState({ currentMajor: "design", currentSubStep: "design.load" });
    render(<AppLayout />);
    const tabs = getMajorTabs();
    expect(tabs[0].getAttribute("aria-selected")).toBe("true");
  });

  it("clicking plate tab changes currentMajor to plate", async () => {
    const user = userEvent.setup();
    useAppStore.setState({ currentMajor: "design", currentSubStep: "design.load" });
    render(<AppLayout />);
    const tabs = getMajorTabs();
    await user.click(tabs[2]); // plate is index 2 (design=0, report=1, plate=2, export=3)
    expect(useAppStore.getState().currentMajor).toBe("plate");
  });

  it("clicking export tab changes currentMajor to export", async () => {
    const user = userEvent.setup();
    useAppStore.setState({ currentMajor: "design", currentSubStep: "design.load" });
    render(<AppLayout />);
    const tabs = getMajorTabs();
    await user.click(tabs[3]); // export is index 3
    expect(useAppStore.getState().currentMajor).toBe("export");
  });
});

describe("AppLayout Phase C -- SubStepNav navigation", () => {
  it("SubStepNav items render for design major", () => {
    useAppStore.setState({ currentMajor: "design", currentSubStep: "design.load" });
    render(<AppLayout />);
    const subTabs = getSubStepTabs();
    // design has 4 sub-steps
    expect(subTabs.length).toBeGreaterThanOrEqual(4);
  });

  it("first sub-step tab is active for design.load", () => {
    useAppStore.setState({ currentMajor: "design", currentSubStep: "design.load" });
    render(<AppLayout />);
    const subTabs = getSubStepTabs();
    expect(subTabs[0].getAttribute("aria-selected")).toBe("true");
  });

  it("clicking second sub-step changes currentSubStep to design.variant", () => {
    useAppStore.setState({ currentMajor: "design", currentSubStep: "design.load" });
    render(<AppLayout />);
    const subTabs = getSubStepTabs();
    fireEvent.click(subTabs[1]); // design.variant
    expect(useAppStore.getState().currentSubStep).toBe("design.variant");
  });
});

describe("AppLayout Phase C -- keyboard shortcut auto-navigate", () => {
  it("Ctrl+Enter from non-design.params sub-step auto-navigates to design.params", () => {
    useAppStore.setState({ currentMajor: "design", currentSubStep: "design.load" });
    render(<AppLayout />);

    act(() => {
      document.body.dispatchEvent(
        new KeyboardEvent("keydown", { key: "Enter", ctrlKey: true, bubbles: true }),
      );
    });

    expect(useAppStore.getState().currentSubStep).toBe("design.params");
    expect(useAppStore.getState().currentMajor).toBe("design");
  });

  it("Ctrl+D from non-design.params sub-step auto-navigates to design.params", () => {
    useAppStore.setState({ currentMajor: "design", currentSubStep: "design.load" });
    render(<AppLayout />);

    act(() => {
      document.body.dispatchEvent(
        new KeyboardEvent("keydown", { key: "d", ctrlKey: true, bubbles: true }),
      );
    });

    expect(useAppStore.getState().currentSubStep).toBe("design.params");
  });
});
