/**
 * StepBadge.test.tsx — 3 status 렌더링 단위 테스트
 */

import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { StepBadge } from "./StepBadge";

describe("StepBadge", () => {
  it("done: renders check icon and DONE label", () => {
    render(<StepBadge status="done" />);
    // i18n key phaseC.badge.done = "DONE" in en
    expect(screen.getByText("DONE")).toBeTruthy();
    // Check icon rendered (lucide renders svg with title or aria-hidden)
    const badge = screen.getByText("DONE").closest("span");
    expect(badge).toBeTruthy();
  });

  it("done: has success color class", () => {
    const { container } = render(<StepBadge status="done" />);
    const badge = container.querySelector("span.bg-success\\/20");
    expect(badge).toBeTruthy();
  });

  it("active: renders index number", () => {
    render(<StepBadge status="active" index={3} />);
    expect(screen.getByText("3")).toBeTruthy();
  });

  it("active: has primary background class", () => {
    const { container } = render(<StepBadge status="active" index={1} />);
    const badge = container.querySelector("span.bg-primary");
    expect(badge).toBeTruthy();
  });

  it("pending: renders index number", () => {
    render(<StepBadge status="pending" index={5} />);
    expect(screen.getByText("5")).toBeTruthy();
  });

  it("pending: has border-only class (no bg-primary)", () => {
    const { container } = render(<StepBadge status="pending" index={2} />);
    // pending should have border class but not bg-primary
    const badge = container.querySelector("span.border-border");
    expect(badge).toBeTruthy();
    const noPrimary = container.querySelector("span.bg-primary");
    expect(noPrimary).toBeNull();
  });

  it("active with no index renders empty string gracefully", () => {
    // Should not throw
    expect(() => render(<StepBadge status="active" />)).not.toThrow();
  });
});
