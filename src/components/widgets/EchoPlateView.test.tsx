import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect } from "vitest";
import { PLATE_FILL_RESERVED } from "@/lib/platePreviewStyles";
import { EchoPlateView } from "./EchoPlateView";
import { PLATE_FILL_FORWARD, PLATE_PREVIEW_FRAME } from "@/lib/platePreviewStyles";
import {
  expectCellSizeClass,
  expectFramedScroller,
  expectGridSemantics,
  expectGridTemplate,
} from "@/test-utils/platePreviewGrid";

const ECHO_TEMPLATE =
  "auto repeat(24, minmax(var(--plate-preview-cell-min-tiny), var(--plate-preview-cell-cap)))";

const FILLED_CELL = {
  well: "A01",
  rowLetter: "A",
  colNumber: 1,
  isFwd: true,
  sourceWellName: "Q232A_F",
  destPlate: "Destination [1]",
  destWell: "A1",
  transferVolNl: 100,
  mutation: "Q232A",
};


describe("EchoPlateView", () => {
  it("frames the grid and keeps the scroll inside that frame", () => {
    const { container } = render(<EchoPlateView cells={[]} />);
    expectFramedScroller(
      container.firstElementChild as HTMLElement,
      PLATE_PREVIEW_FRAME,
      "min-w-[700px]",
    );
  });

  it("renders the title caption it is given", () => {
    render(<EchoPlateView cells={[]} title="Echo source plate" />);
    expect(screen.getByText("Echo source plate")).toBeInTheDocument();
  });

  it("fills a forward well from the shared colour constant", () => {
    const { container } = render(
      <EchoPlateView
        cells={[
          {
            well: "A01",
            rowLetter: "A",
            colNumber: 1,
            isFwd: true,
            sourceWellName: "P1-fw",
            destPlate: "D1",
            destWell: "A1",
            transferVolNl: 100,
            mutation: "P1",
          },
        ]}
      />,
    );
    const filled = container.querySelector("button[data-testid='echo-cell']") as HTMLElement;
    expect(filled.className).toContain(PLATE_FILL_FORWARD);
  });

  it("renders 16 rows x 24 cols (384 cells)", () => {
    const { container } = render(<EchoPlateView cells={[]} />);
    expect(container.querySelectorAll("[data-testid='echo-cell']")).toHaveLength(384);
  });

  it("applies fwd stripe to odd rows (row A)", () => {
    const { container } = render(<EchoPlateView cells={[]} />);
    const rowACells = container.querySelectorAll("[data-row='A']");
    expect(rowACells.length).toBeGreaterThan(0);
    const className = (rowACells[0] as HTMLElement).className;
    expect(className).toMatch(/blue/);
  });

  it("applies rev stripe to even rows (row B)", () => {
    const { container } = render(<EchoPlateView cells={[]} />);
    const rowBCells = container.querySelectorAll("[data-row='B']");
    expect(rowBCells.length).toBeGreaterThan(0);
    const className = (rowBCells[0] as HTMLElement).className;
    expect(className).toMatch(/orange/);
  });

  it("renders cell tooltip for filled well A01", () => {
    render(
      <EchoPlateView
        cells={[
          {
            well: "A01",
            rowLetter: "A",
            colNumber: 1,
            isFwd: true,
            sourceWellName: "P1-fw",
            destPlate: "D1",
            destWell: "A1",
            transferVolNl: 100,
            mutation: "P1",
          },
        ]}
      />,
    );
    expect(screen.getByTitle(/P1-fw/)).toBeInTheDocument();
  });

  it("renders boundary well P24 (last cell)", () => {
    const { container } = render(<EchoPlateView cells={[]} />);
    const rowPCells = container.querySelectorAll("[data-row='P']");
    expect(rowPCells).toHaveLength(24);
  });

  it("renders mutation code inside well cell", () => {
    const cells = [
      {
        well: "A01",
        rowLetter: "A",
        colNumber: 1,
        isFwd: true,
        sourceWellName: "Q232A_F",
        destPlate: "Destination [1]",
        destWell: "A1",
        transferVolNl: 100,
        mutation: "Q232A",
      },
    ];
    render(<EchoPlateView cells={cells} />);
    expect(screen.getByText("Q232A")).toBeInTheDocument();
  });

  it("opens popover with primer details on cell click", async () => {
    const cells = [
      {
        well: "A01",
        rowLetter: "A",
        colNumber: 1,
        isFwd: true,
        sourceWellName: "Q232A_F",
        destPlate: "Destination [1]",
        destWell: "A1",
        transferVolNl: 100,
        mutation: "Q232A",
      },
    ];
    render(<EchoPlateView cells={cells} />);
    await userEvent.click(screen.getByText("Q232A"));
    expect(await screen.findByText(/Q232A_F/)).toBeInTheDocument();
    expect(screen.getByText(/Destination \[1\] A1/)).toBeInTheDocument();
    expect(screen.getByText(/100 nL/)).toBeInTheDocument();
  });

  it("wraps every well in a gridcell and labels its row header", () => {
    const { container } = render(<EchoPlateView cells={[FILLED_CELL]} />);
    expectGridSemantics(container, "echo-cell");
  });

  it("keeps exactly one query container, on the frame", () => {
    const { container } = render(<EchoPlateView cells={[]} />);
    const root = container.firstElementChild as HTMLElement;
    expect(root.className).toContain("plate-preview-grid");
    expect(container.querySelectorAll(".plate-preview-grid")).toHaveLength(1);
  });

  it("keeps the tuned 24-column track template", () => {
    const { container } = render(<EchoPlateView cells={[]} />);
    expectGridTemplate(container, ECHO_TEMPLATE);
  });

  it("keeps its own cell size class after the shared-cell refactor", () => {
    const { container } = render(<EchoPlateView cells={[FILLED_CELL]} />);
    const filled = container.querySelector<HTMLElement>("button[data-testid='echo-cell']");
    expect(filled).not.toBeNull();
    expectCellSizeClass(filled!, "plate-preview-cell-tiny", [
      "plate-preview-cell",
      "plate-preview-cell-narrow",
    ]);
  });

  it("renders its popover through the shared popover component", async () => {
    render(<EchoPlateView cells={[FILLED_CELL]} />);
    await userEvent.click(screen.getByText("Q232A"));
    expect(await screen.findByTestId("plate-popover-body")).toBeInTheDocument();
  });

  // A run spends a quadrant *pair* sharing a column offset (A1 with B1), so
  // "this run can reach it" is a column-parity question. The A1 and A2 cases
  // below disagree on exactly the wells that separate that rule from a
  // "selected quadrant only" rule, which would call every reverse-primer well
  // reserved.
  describe("empty-well classification", () => {
    function stateOf(container: HTMLElement, well: string): string | null {
      const idx = wellIndex(well);
      const cells = container.querySelectorAll("[data-testid='echo-cell']");
      return (cells[idx] as HTMLElement).getAttribute("data-state");
    }

    /** Index of a 384 well in render order (row-major, A01 first). */
    function wellIndex(well: string): number {
      const row = "ABCDEFGHIJKLMNOP".indexOf(well[0]);
      const col = Number(well.slice(1));
      return row * 24 + (col - 1);
    }

    it("marks odd columns free and even columns reserved for quadrant A1", () => {
      const { container } = render(<EchoPlateView cells={[]} quadrant="A1" />);
      // A01: forward quadrant. B01: its paired reverse quadrant B1, same
      // column offset, so also this run's.
      expect(stateOf(container, "A01")).toBe("free");
      expect(stateOf(container, "B01")).toBe("free");
      expect(stateOf(container, "A02")).toBe("reserved");
    });

    it("flips that split for quadrant A2", () => {
      const { container } = render(<EchoPlateView cells={[]} quadrant="A2" />);
      expect(stateOf(container, "A02")).toBe("free");
      expect(stateOf(container, "B02")).toBe("free");
      expect(stateOf(container, "A01")).toBe("reserved");
    });

    it("draws the two empty kinds with different classes, not colour alone", () => {
      const { container } = render(<EchoPlateView cells={[]} quadrant="A1" />);
      const reserved = container.querySelector<HTMLElement>("[data-state='reserved']");
      const free = container.querySelector<HTMLElement>("[data-state='free']");
      expect(reserved).not.toBeNull();
      expect(free).not.toBeNull();
      expect(reserved!.className).toContain(PLATE_FILL_RESERVED);
      expect(reserved!.className).toContain("border-dashed");
      expect(free!.className).not.toContain("border-dashed");
      expect(free!.className).not.toBe(reserved!.className);
    });

    it("says in the tooltip which quadrants a reserved well is held for", () => {
      const { container } = render(<EchoPlateView cells={[]} quadrant="A1" />);
      const reserved = container.querySelector<HTMLElement>("[data-state='reserved']");
      expect(reserved!.getAttribute("title")).toContain("A2, B2");
    });

    it("claims nothing about quadrants when none is selected", () => {
      const { container } = render(<EchoPlateView cells={[]} />);
      expect(container.querySelectorAll("[data-state='reserved']")).toHaveLength(0);
      expect(container.querySelectorAll("[data-state='free']")).toHaveLength(0);
    });
  });
});
