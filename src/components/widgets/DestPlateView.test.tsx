import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect } from "vitest";
import { DestPlateView } from "./DestPlateView";
import type { DestCell } from "@/lib/echoJanusAdapter";
import {
  PLATE_FILL_DEST_COMPLETE,
  PLATE_PREVIEW_FRAME,
} from "@/lib/platePreviewStyles";
import {
  expectCellSizeClass,
  expectFramedScroller,
  expectGridSemantics,
  expectGridTemplate,
} from "@/test-utils/platePreviewGrid";

const DEST_TEMPLATE =
  "auto repeat(12, minmax(var(--plate-preview-cell-min), var(--plate-preview-cell-cap)))";

const FILLED_CELLS: DestCell[] = [
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


describe("DestPlateView", () => {
  it("frames the grid and keeps the scroll inside that frame", () => {
    const { container } = render(<DestPlateView cells={[]} sourceMethod="echo" />);
    expectFramedScroller(
      container.firstElementChild as HTMLElement,
      PLATE_PREVIEW_FRAME,
      "min-w-[400px]",
    );
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

  it("wraps every well in a gridcell and labels its row header", () => {
    const { container } = render(<DestPlateView cells={FILLED_CELLS} sourceMethod="echo" />);
    expectGridSemantics(container, "dest-cell");
  });

  it("keeps exactly one query container, on the frame", () => {
    const { container } = render(<DestPlateView cells={[]} sourceMethod="echo" />);
    const root = container.firstElementChild as HTMLElement;
    expect(root.className).toContain("plate-preview-grid");
    expect(container.querySelectorAll(".plate-preview-grid")).toHaveLength(1);
  });

  it("keeps the tuned 12-column track template", () => {
    const { container } = render(<DestPlateView cells={[]} sourceMethod="echo" />);
    expectGridTemplate(container, DEST_TEMPLATE);
  });

  it("keeps its own cell size class after the shared-cell refactor", () => {
    const { container } = render(<DestPlateView cells={FILLED_CELLS} sourceMethod="echo" />);
    const filled = container.querySelector<HTMLElement>("button[data-testid='dest-cell']");
    expect(filled).not.toBeNull();
    expectCellSizeClass(filled!, "plate-preview-cell", [
      "plate-preview-cell-tiny",
      "plate-preview-cell-narrow",
    ]);
  });

  it("renders its popover through the shared popover component", async () => {
    render(<DestPlateView cells={FILLED_CELLS} sourceMethod="echo" />);
    await userEvent.click(screen.getByText("Q232A"));
    expect(await screen.findByTestId("plate-popover-body")).toBeInTheDocument();
  });
});
