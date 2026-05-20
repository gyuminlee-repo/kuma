import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { DestPlateView } from "./DestPlateView";
import type { DestCell } from "@/lib/echoJanusAdapter";

describe("DestPlateView", () => {
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
