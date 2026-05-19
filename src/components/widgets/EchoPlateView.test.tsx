import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect } from "vitest";
import { EchoPlateView } from "./EchoPlateView";

describe("EchoPlateView", () => {
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
      },
    ];
    render(<EchoPlateView cells={cells} />);
    await userEvent.click(screen.getByText("Q232A"));
    expect(await screen.findByText(/Q232A_F/)).toBeInTheDocument();
    expect(screen.getByText(/Destination \[1\] A1/)).toBeInTheDocument();
    expect(screen.getByText(/100 nL/)).toBeInTheDocument();
  });
});
