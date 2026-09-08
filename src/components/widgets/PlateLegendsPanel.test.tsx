import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { PlateLegendsPanel } from "./PlateLegendsPanel";
import {
  PLATE_FILL_DEST_COMPLETE,
  PLATE_FILL_DEST_PARTIAL,
  PLATE_FILL_FORWARD,
  PLATE_FILL_REVERSE,
} from "@/lib/platePreviewStyles";

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

  it("takes every swatch colour from the constants the cells use", () => {
    // Asserted against the shared constants, not literal class names: the
    // defect this replaces was swatch and cell holding separate literals that
    // drifted (cells gained dark: variants, swatches did not). A literal
    // assertion stayed green right through that.
    const { container } = render(<PlateLegendsPanel />);
    const swatches = Array.from(container.querySelectorAll(".rounded-sm"));
    for (const cls of [
      PLATE_FILL_FORWARD,
      PLATE_FILL_REVERSE,
      PLATE_FILL_DEST_COMPLETE,
      PLATE_FILL_DEST_PARTIAL,
    ]) {
      expect(swatches.some((el) => el.className.includes(cls))).toBe(true);
    }
  });
});
