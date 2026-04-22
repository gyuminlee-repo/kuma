import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
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
