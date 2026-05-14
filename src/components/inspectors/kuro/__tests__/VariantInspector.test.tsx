import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { VariantInspector } from "../VariantInspector";

describe("VariantInspector", () => {
  it("renders empty state when no row is selected", () => {
    render(<VariantInspector selected={null} />);
    expect(screen.getByText(/Select a row to view details/i)).toBeTruthy();
  });

  it("renders mutation details when a row is selected", () => {
    render(
      <VariantInspector
        selected={{
          mutation: "M42A",
          activity: 1.23,
          activityStd: 0.45,
          reads: 1024,
          domain: "kinase",
          mameLink: "round3/well_B07",
        }}
      />,
    );
    expect(screen.getByText("M42A")).toBeTruthy();
    expect(screen.getByText("1.23 ± 0.45")).toBeTruthy();
    expect(screen.getByText("1,024")).toBeTruthy();
    expect(screen.getByText("kinase")).toBeTruthy();
    expect(screen.getByText("round3/well_B07")).toBeTruthy();
  });
});
