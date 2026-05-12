/**
 * AppLayout.phaseC.test.tsx — Phase C integration tests
 *
 * Tests:
 *   1. data-tool="kuro" attribute preserved (Phase A token selector)
 *   2. sidebar region exists
 *   3. main content region exists
 *   4. MajorSubnav 4 major tabs rendered
 *   5. clicking sdm tab → currentMajor = "sdm"
 *   6. SubStepNav click → currentSubStep changes
 *   7. Ctrl+Enter → auto-navigate to sdm.run
 *   8. SummaryMetric / WorkflowStep not in DOM (regression)
 */

import { render, screen, fireEvent, act } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";

// ipc-kuro dependency shim (required for all AppLayout tests)
vi.mock("@/lib/ipc-kuro", () => ({
  sendRequest: vi.fn(),
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
  spawnSidecar: vi.fn(() => Promise.resolve()),
  getLastProgressAt: vi.fn(() => Date.now()),
}));

import { AppLayout } from "./AppLayout";
import { useAppStore } from "@/store/appStore";

// Helper: select major tabs (aria-controls="major-step-main" + no data-active attr = MajorSubnav buttons)
// SubStepNav buttons also have aria-controls="major-step-main" but have data-active attr
function getMajorTabs() {
  return screen
    .getAllByRole("tab")
    .filter(
      (el) =>
        el.getAttribute("aria-controls") === "major-step-main" &&
        el.getAttribute("data-active") === null,
    );
}

function getSubStepTabs() {
  return screen
    .getAllByRole("tab")
    .filter(
      (el) =>
        el.getAttribute("aria-controls") === "major-step-main" &&
        el.hasAttribute("data-active"),
    );
}

describe("AppLayout Phase C — layout structure", () => {
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

describe("AppLayout Phase C — MajorSubnav navigation", () => {
  it("renders at least 4 major tabs", () => {
    useAppStore.setState({ currentMajor: "variant", currentSubStep: "variant.load" });
    render(<AppLayout />);
    const tabs = getMajorTabs();
    expect(tabs.length).toBeGreaterThanOrEqual(4);
  });

  it("first major tab is aria-selected when currentMajor='variant'", () => {
    useAppStore.setState({ currentMajor: "variant", currentSubStep: "variant.load" });
    render(<AppLayout />);
    const tabs = getMajorTabs();
    expect(tabs[0].getAttribute("aria-selected")).toBe("true");
  });

  it("clicking sdm tab changes currentMajor to sdm", () => {
    useAppStore.setState({ currentMajor: "variant", currentSubStep: "variant.load" });
    render(<AppLayout />);
    const tabs = getMajorTabs();
    fireEvent.click(tabs[1]); // sdm is index 1
    expect(useAppStore.getState().currentMajor).toBe("sdm");
  });

  it("clicking plate tab changes currentMajor to plate", () => {
    useAppStore.setState({ currentMajor: "variant", currentSubStep: "variant.load" });
    render(<AppLayout />);
    const tabs = getMajorTabs();
    fireEvent.click(tabs[2]); // plate is index 2
    expect(useAppStore.getState().currentMajor).toBe("plate");
  });
});

describe("AppLayout Phase C — SubStepNav navigation", () => {
  it("SubStepNav items render for current major", () => {
    useAppStore.setState({ currentMajor: "variant", currentSubStep: "variant.load" });
    render(<AppLayout />);
    const subTabs = getSubStepTabs();
    // variant has 5 sub-steps
    expect(subTabs.length).toBeGreaterThanOrEqual(5);
  });

  it("first sub-step tab is active for variant.load", () => {
    useAppStore.setState({ currentMajor: "variant", currentSubStep: "variant.load" });
    render(<AppLayout />);
    const subTabs = getSubStepTabs();
    expect(subTabs[0].getAttribute("aria-selected")).toBe("true");
  });

  it("clicking second sub-step changes currentSubStep to variant.select", () => {
    useAppStore.setState({ currentMajor: "variant", currentSubStep: "variant.load" });
    render(<AppLayout />);
    const subTabs = getSubStepTabs();
    fireEvent.click(subTabs[1]); // variant.select
    expect(useAppStore.getState().currentSubStep).toBe("variant.select");
  });
});

describe("AppLayout Phase C — keyboard shortcut sdm.run auto-navigate", () => {
  it("Ctrl+Enter from non-sdm.run sub-step auto-navigates to sdm.run", () => {
    useAppStore.setState({ currentMajor: "variant", currentSubStep: "variant.load" });
    render(<AppLayout />);

    act(() => {
      // Dispatch on document.body so e.target instanceof Element is true and tagName is "BODY"
      document.body.dispatchEvent(
        new KeyboardEvent("keydown", { key: "Enter", ctrlKey: true, bubbles: true }),
      );
    });

    expect(useAppStore.getState().currentSubStep).toBe("sdm.run");
    expect(useAppStore.getState().currentMajor).toBe("sdm");
  });

  it("Ctrl+D from non-sdm.run sub-step auto-navigates to sdm.run", () => {
    useAppStore.setState({ currentMajor: "variant", currentSubStep: "variant.load" });
    render(<AppLayout />);

    act(() => {
      document.body.dispatchEvent(
        new KeyboardEvent("keydown", { key: "d", ctrlKey: true, bubbles: true }),
      );
    });

    expect(useAppStore.getState().currentSubStep).toBe("sdm.run");
  });
});
