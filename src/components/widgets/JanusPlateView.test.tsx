import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect } from "vitest";
import { JanusPlateView } from "./JanusPlateView";

describe("JanusPlateView", () => {
  it("renders 2 source plate panels of 96 cells (192 total)", () => {
    const { container } = render(<JanusPlateView rack1={[]} rack2={[]} />);
    expect(container.querySelectorAll("[data-testid='janus-cell']")).toHaveLength(192);
  });

  it("renders the forward source panel with 96 cells (8 rows x 12 cols)", () => {
    const { container } = render(<JanusPlateView rack1={[]} rack2={[]} />);
    expect(container.querySelectorAll("[data-rack='1']")).toHaveLength(96);
  });

  it("renders the reverse source panel with 96 cells (8 rows x 12 cols)", () => {
    const { container } = render(<JanusPlateView rack1={[]} rack2={[]} />);
    expect(container.querySelectorAll("[data-rack='2']")).toHaveLength(96);
  });

  it("renders boundary well H12 in both panels", () => {
    const { container } = render(<JanusPlateView rack1={[]} rack2={[]} />);
    const rack1Last = container.querySelector("[data-rack='1'][data-well='H12']");
    const rack2Last = container.querySelector("[data-rack='2'][data-well='H12']");
    expect(rack1Last).not.toBeNull();
    expect(rack2Last).not.toBeNull();
  });

  it("renders cell tooltip with name and volume for filled well", () => {
    render(
      <JanusPlateView
        rack1={[
          {
            well: "A1",
            rowLetter: "A",
            colNumber: 1,
            rack: 1,
            name: "P1-fw",
            volumeUl: 2.5,
            mutation: "P1",
          },
        ]}
        rack2={[
          {
            well: "B2",
            rowLetter: "B",
            colNumber: 2,
            rack: 2,
            name: "P1-dest",
            volumeUl: 5.0,
            mutation: "P1",
          },
        ]}
      />,
    );
    expect(screen.getByTitle(/P1-fw/)).toBeInTheDocument();
    expect(screen.getByTitle(/2\.5/)).toBeInTheDocument();
    expect(screen.getByTitle(/P1-dest/)).toBeInTheDocument();
  });

  it("renders source plate labels via i18n keys", () => {
    const { container } = render(<JanusPlateView rack1={[]} rack2={[]} />);
    // Labels rendered via t(); since keys not yet in locale, i18next returns key as fallback.
    // Look for label elements by data-testid so test stays robust whether key is resolved or not.
    expect(
      container.querySelector("[data-testid='janus-forward-source-label']"),
    ).not.toBeNull();
    expect(
      container.querySelector("[data-testid='janus-reverse-source-label']"),
    ).not.toBeNull();
  });

  it("renders mutation code and F/R tag in each well", () => {
    const rack1 = [
      {
        well: "A1",
        rowLetter: "A",
        colNumber: 1,
        rack: 1 as const,
        name: "Q232A-fw",
        volumeUl: 2.0,
        mutation: "Q232A",
      },
    ];
    const { container } = render(<JanusPlateView rack1={rack1} rack2={[]} />);
    expect(screen.getByText("Q232A")).toBeInTheDocument();
    // "F" is not unique on the page: row F's own label (a real text node,
    // matching DestPlateView's pattern) also reads "F". Scope to the filled
    // cell's F/R tag specifically.
    const cell = container.querySelector<HTMLElement>("[data-testid='janus-cell'][data-well='A1']");
    expect(cell).not.toBeNull();
    expect(cell!.querySelector(".text-\\[0\\.85em\\]")?.textContent).toBe("F");
  });

  it("opens popover with details on cell click", async () => {
    const rack1 = [
      {
        well: "A1",
        rowLetter: "A",
        colNumber: 1,
        rack: 1 as const,
        name: "Q232A-fw",
        volumeUl: 2.0,
        mutation: "Q232A",
      },
    ];
    render(<JanusPlateView rack1={rack1} rack2={[]} />);
    await userEvent.click(screen.getByText("Q232A"));
    expect(await screen.findByText(/Q232A-fw/)).toBeInTheDocument();
    expect(screen.getByText(/2(\.0)? ?[μu]L/i)).toBeInTheDocument();
    // The popover used to print "Rack: 1", the index of the panel the cell sits
    // in. The deck is addressed by plate name, so a number there named a
    // position the instrument does not have. Nothing on this view says rack.
    expect(screen.queryByText(/rack/i)).toBeNull();
  });

  it("empty panels still render the full grid", () => {
    const { container } = render(<JanusPlateView rack1={[]} rack2={[]} />);
    const cells = container.querySelectorAll("[data-testid='janus-cell']");
    expect(cells).toHaveLength(192);
    // No filled cells should have a name in their title
    cells.forEach((cell) => {
      const title = cell.getAttribute("title") ?? "";
      // Empty cells display only the well coordinate (e.g., "A1"), no µL
      expect(title).not.toMatch(/µL/);
    });
  });
});
