/**
 * DataPanel body overflow.
 *
 * The body used to be `overflow-hidden` unconditionally, so a child taller than
 * the panel (the per-plate verdict breakdown, in a resizable PanelGroup) was cut
 * off with no scrollbar to reach the rest. `scrollBody` is the opt-in fix, kept
 * opt-in because most DataPanel children scroll themselves.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DataPanel } from "./Panel";

/** The body wrapper is the element that owns the overflow class. */
function bodyOf(testId: string): HTMLElement {
  const child = screen.getByTestId(testId);
  const body = child.parentElement;
  if (!body) throw new Error("DataPanel body wrapper not found");
  return body;
}

describe("DataPanel scrollBody", () => {
  it("clips the body by default so self-scrolling children keep one scrollbar", () => {
    render(
      <DataPanel title="Verdict table">
        <div data-testid="child" />
      </DataPanel>,
    );

    const body = bodyOf("child");
    expect(body.className).toContain("overflow-hidden");
    expect(body.className).not.toContain("overflow-auto");
    expect(body).not.toHaveAttribute("data-scroll-body");
  });

  it("gives the body a scroll container when opted in", () => {
    render(
      <DataPanel title="Per-plate verdict breakdown" scrollBody>
        <div data-testid="child" />
      </DataPanel>,
    );

    const body = bodyOf("child");
    expect(body.className).toContain("overflow-auto");
    expect(body.className).not.toContain("overflow-hidden");
    expect(body).toHaveAttribute("data-scroll-body", "true");
  });

  it("keeps min-h-0 either way so the body can shrink below its content", () => {
    const { rerender } = render(
      <DataPanel title="Panel">
        <div data-testid="child" />
      </DataPanel>,
    );
    expect(bodyOf("child").className).toContain("min-h-0");

    rerender(
      <DataPanel title="Panel" scrollBody>
        <div data-testid="child" />
      </DataPanel>,
    );
    expect(bodyOf("child").className).toContain("min-h-0");
  });
});
