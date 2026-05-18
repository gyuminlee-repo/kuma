import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { JanusPlateView } from "./JanusPlateView";

describe("JanusPlateView", () => {
  it("renders 2 racks of 96 cells (192 total)", () => {
    const { container } = render(<JanusPlateView rack1={[]} rack2={[]} />);
    expect(container.querySelectorAll("[data-testid='janus-cell']")).toHaveLength(192);
  });

  it("renders rack 1 with 96 cells (8 rows x 12 cols)", () => {
    const { container } = render(<JanusPlateView rack1={[]} rack2={[]} />);
    expect(container.querySelectorAll("[data-rack='1']")).toHaveLength(96);
  });

  it("renders rack 2 with 96 cells (8 rows x 12 cols)", () => {
    const { container } = render(<JanusPlateView rack1={[]} rack2={[]} />);
    expect(container.querySelectorAll("[data-rack='2']")).toHaveLength(96);
  });

  it("renders boundary well H12 in both racks", () => {
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
          },
        ]}
      />,
    );
    expect(screen.getByTitle(/P1-fw/)).toBeInTheDocument();
    expect(screen.getByTitle(/2\.5/)).toBeInTheDocument();
    expect(screen.getByTitle(/P1-dest/)).toBeInTheDocument();
  });

  it("renders rack labels via i18n keys", () => {
    const { container } = render(<JanusPlateView rack1={[]} rack2={[]} />);
    // Labels rendered via t(); since keys not yet in locale, i18next returns key as fallback.
    // Look for label elements by data-testid so test stays robust whether key is resolved or not.
    expect(container.querySelector("[data-testid='janus-rack1-label']")).not.toBeNull();
    expect(container.querySelector("[data-testid='janus-rack2-label']")).not.toBeNull();
  });

  it("empty racks still render the full grid", () => {
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
