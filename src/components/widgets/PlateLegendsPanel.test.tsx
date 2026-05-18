import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { PlateLegendsPanel } from "./PlateLegendsPanel";

describe("PlateLegendsPanel", () => {
  it("renders 3 legend chips and a heading", () => {
    render(<PlateLegendsPanel />);
    expect(screen.getByText("Color legend")).toBeInTheDocument();
    expect(screen.getByText(/Forward primer/i)).toBeInTheDocument();
    expect(screen.getByText(/Reverse primer/i)).toBeInTheDocument();
    expect(screen.getByText(/Destination/i)).toBeInTheDocument();
  });
});
