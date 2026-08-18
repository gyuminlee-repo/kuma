import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";

vi.mock("@/lib/ipc-kuro", () => ({
  // health_info rejects rather than resolving undefined. StatusBar polls it and
  // renders the result; the real sendRequest either returns a payload the
  // validator accepted or throws, and never resolves undefined. Before the
  // status bar was routed through this client it called the raw transport,
  // which threw "Tauri bridge unavailable" here, so a rejection is also what
  // this test used to see.
  sendRequest: vi.fn((method: string) =>
    method === "health_info"
      ? Promise.reject(new Error("sidecar unavailable in test"))
      : Promise.resolve(undefined),
  ),
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
  spawnSidecar: vi.fn(() => Promise.resolve()),
  getLastProgressAt: vi.fn(() => Date.now()),
}));

import { AppLayout } from "./AppLayout";

describe("AppLayout smoke", () => {
  it("renders without crash", () => {
    render(<AppLayout />);
  });
  it("sidebar region exists", () => {
    render(<AppLayout />);
    expect(document.querySelector("[data-testid='sidebar']")).toBeTruthy();
  });
  it("main content region exists", () => {
    render(<AppLayout />);
    expect(document.querySelector("[data-testid='main-content']")).toBeTruthy();
  });
  it("SummaryMetric is not in DOM", () => {
    render(<AppLayout />);
    expect(screen.queryByTestId("summary-metric")).toBeNull();
  });
  it("WorkflowStep is not in DOM", () => {
    render(<AppLayout />);
    expect(screen.queryByTestId("workflow-step")).toBeNull();
  });
});
