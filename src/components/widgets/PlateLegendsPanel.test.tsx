import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { PlateLegendsPanel } from "./PlateLegendsPanel";

describe("PlateLegendsPanel", () => {
  it("renders 4 legend chips and a heading", () => {
    const { container } = render(<PlateLegendsPanel />);
    expect(screen.getByText("Color legend")).toBeInTheDocument();
    expect(screen.getByText(/Forward primer/i)).toBeInTheDocument();
    expect(screen.getByText(/Reverse primer/i)).toBeInTheDocument();
    // DestPlateView only ever draws two states for a filled well: both
    // primers arrived, or only one did. There is no third "destination"
    // shade to legend, so the panel names exactly those two states.
    expect(screen.getByText(/Both F\+R arrived/i)).toBeInTheDocument();
    expect(screen.getByText(/Only F or R arrived/i)).toBeInTheDocument();
    expect(container.querySelectorAll(".rounded-sm")).toHaveLength(4);
  });

  it("matches DestPlateView's actual colors: emerald for complete, amber for partial", () => {
    const { container } = render(<PlateLegendsPanel />);
    const swatches = Array.from(container.querySelectorAll(".rounded-sm"));
    expect(swatches.some((el) => el.className.includes("bg-emerald-400"))).toBe(true);
    expect(swatches.some((el) => el.className.includes("bg-amber-400"))).toBe(true);
  });
});
