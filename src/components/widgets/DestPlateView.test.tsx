import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { DestPlateView } from "./DestPlateView";
import type { DestCell } from "@/lib/echoJanusAdapter";
import {
  PLATE_FILL_DEST_COMPLETE,
  PLATE_PREVIEW_FRAME,
} from "@/lib/platePreviewStyles";

/**
 * The frame/scroller contract these previews now share with WellPlate: the
 * outermost element carries the card frame and the horizontal scroll, and
 * `min-w-*` sits on a descendant, so a plate wider than the viewport scrolls
 * inside its own frame instead of pushing the page.
 */
function expectFramedScroller(root: HTMLElement, minWidthClass: string): void {
  expect(root.className).toContain(PLATE_PREVIEW_FRAME);
  expect(root.className).toContain("overflow-x-auto");
  expect(root.className).not.toMatch(/min-w-/);
  expect(root.querySelector(`.${CSS.escape(minWidthClass)}`)).not.toBeNull();
}

describe("DestPlateView", () => {
  it("frames the grid and keeps the scroll inside that frame", () => {
    const { container } = render(<DestPlateView cells={[]} sourceMethod="echo" />);
    expectFramedScroller(container.firstElementChild as HTMLElement, "min-w-[400px]");
  });

  it("renders the title caption it is given", () => {
    render(<DestPlateView cells={[]} sourceMethod="echo" title="Destination plate" />);
    expect(screen.getByText("Destination plate")).toBeInTheDocument();
  });

  it("renders 96 wells (8 rows x 12 cols) when cells are empty", () => {
    const { container } = render(<DestPlateView cells={[]} sourceMethod="echo" />);
    expect(container.querySelectorAll("[data-testid='dest-cell']")).toHaveLength(96);
  });

  it("marks well as 'complete' when both F and R are present", () => {
    const cells: DestCell[] = [
      {
        well: "A1",
        rowLetter: "A",
        colNumber: 1,
        mutation: "Q232A",
        hasF: true,
        hasR: true,
        fwdVol: 100,
        revVol: 100,
        fwdSource: "A01",
        revSource: "B01",
      },
    ];
    const { container } = render(<DestPlateView cells={cells} sourceMethod="echo" />);
    const cell = container.querySelector("[data-well='A1']") as HTMLElement;
    expect(cell).toBeTruthy();
    expect(cell.getAttribute("data-state")).toBe("complete");
    expect(cell.className).toContain(PLATE_FILL_DEST_COMPLETE);
    expect(screen.getByText("Q232A")).toBeInTheDocument();
  });

  it("marks well as 'partial' when only F or only R is present (amber warning)", () => {
    const cells: DestCell[] = [
      {
        well: "B2",
        rowLetter: "B",
        colNumber: 2,
        mutation: "K47R",
        hasF: true,
        hasR: false,
        fwdVol: 100,
        fwdSource: "C01",
      },
    ];
    const { container } = render(<DestPlateView cells={cells} sourceMethod="janus" />);
    const cell = container.querySelector("[data-well='B2']") as HTMLElement;
    expect(cell.getAttribute("data-state")).toBe("partial");
    expect(cell.className).toMatch(/amber/);
  });
});
