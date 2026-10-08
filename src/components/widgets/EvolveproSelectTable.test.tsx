import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { EvolveproSelectRow } from "./EvolveproSelectTable";
import { EvolveproSelectTable } from "./EvolveproSelectTable";

// i18n mock: mirrors ParameterPanel.test.tsx pattern
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      // Return meaningful values for keys used by the component
      if (key === "resultTable.includeAriaLabel" && opts) {
        return `Include ${opts["mutation"]} in downstream outputs`;
      }
      if (key === "resultTable.excludedRowAriaLabel" && opts) {
        return `${opts["mutation"]} is excluded from downstream outputs`;
      }
      if (key === "resultTable.includeHeader") return "Include";
      if (key === "resultTable.includeTitle") return "Include this row in plate map and exports";
      if (key === "resultTable.excludeTitle") return "Exclude this row from plate map and exports";
      const label = key.split(".").pop() ?? key;
      return opts ? `${label}(${Object.values(opts).join(",")})` : label;
    },
  }),
}));

function row(
  variant: string,
  yPred: number,
  aaPosition: number | null,
  selected = true,
): EvolveproSelectRow {
  return { variant, yPred, aaPosition, selected };
}

describe("EvolveproSelectTable", () => {
  describe("sort order", () => {
    it("renders rows sorted by y_pred descending", () => {
      const rows = [
        row("A1G", 0.5, 1),
        row("B2C", 0.9, 2),
        row("C3D", 0.7, 3),
      ];
      render(<EvolveproSelectTable rows={rows} onToggle={vi.fn()} />);

      const cells = screen.getAllByRole("cell").filter((c) => /^[A-Z]\d[A-Z]/.test(c.textContent ?? ""));
      // First rendered mutation should be B2C (highest y_pred)
      expect(cells[0].textContent).toContain("B2C");
      expect(cells[1].textContent).toContain("C3D");
      expect(cells[2].textContent).toContain("A1G");
    });

    it("maintains stable order for rows with equal y_pred", () => {
      const rows = [
        row("X1A", 0.8, 10),
        row("Y2B", 0.8, 20),
        row("Z3C", 0.8, 30),
      ];
      render(<EvolveproSelectTable rows={rows} onToggle={vi.fn()} />);

      const mutationCells = screen
        .getAllByRole("cell")
        .filter((c) => /^[XYZ]\d[A-Z]/.test(c.textContent ?? ""));
      // Stable sort preserves input order on ties
      expect(mutationCells[0].textContent).toContain("X1A");
      expect(mutationCells[1].textContent).toContain("Y2B");
      expect(mutationCells[2].textContent).toContain("Z3C");
    });

    it("shows rank as 1-based index of sorted array", () => {
      const rows = [row("Low", 0.1, 1), row("High", 0.9, 2)];
      render(<EvolveproSelectTable rows={rows} onToggle={vi.fn()} />);

      const rankCells = screen.getAllByRole("cell").filter((c) => /^\d+$/.test(c.textContent?.trim() ?? ""));
      expect(rankCells[0].textContent?.trim()).toBe("1");
      expect(rankCells[1].textContent?.trim()).toBe("2");
    });
  });

  describe("position color badge", () => {
    it("shows Pos{n} badge for variants sharing an aa position", () => {
      const rows = [
        row("F89W", 0.9, 89),
        row("F89Y", 0.8, 89),  // duplicate position → badge
        row("A10G", 0.7, 10),  // unique position → no badge
      ];
      render(<EvolveproSelectTable rows={rows} onToggle={vi.fn()} />);

      // Both position-89 variants should show Pos89 badge
      const badges = screen.getAllByText("Pos89");
      expect(badges).toHaveLength(2);

      // Position-10 variant should not show any badge
      expect(screen.queryByText("Pos10")).toBeNull();
    });

    it("does not show badge for null aa position", () => {
      const rows = [
        row("NoPos", 0.9, null),
        row("AlsoNoPos", 0.8, null),
      ];
      render(<EvolveproSelectTable rows={rows} onToggle={vi.fn()} />);

      // No Pos badge should appear
      expect(screen.queryByText(/^Pos/)).toBeNull();
    });
  });

  describe("checkbox toggle", () => {
    it("calls onToggle with variant and new checked value when clicked", () => {
      const onToggle = vi.fn();
      const rows = [row("M1A", 0.7, 1, true)];
      render(<EvolveproSelectTable rows={rows} onToggle={onToggle} />);

      const checkbox = screen.getByRole("checkbox", {
        name: /include M1A in downstream outputs/i,
      });
      expect(checkbox).toBeChecked();

      fireEvent.click(checkbox);

      // fireEvent.click triggers onChange with checked=false
      expect(onToggle).toHaveBeenCalledWith("M1A", false);
    });

    it("reflects selected=false as unchecked checkbox", () => {
      const rows = [row("M2B", 0.5, 2, false)];
      render(<EvolveproSelectTable rows={rows} onToggle={vi.fn()} />);

      const checkbox = screen.getByRole("checkbox", {
        name: /include M2B in downstream outputs/i,
      });
      expect(checkbox).not.toBeChecked();
    });
  });

  describe("initial selected state", () => {
    it("renders checked checkboxes for selected rows", () => {
      const rows = [
        row("S1A", 0.9, 1, true),
        row("S2B", 0.8, 2, false),
        row("S3C", 0.7, 3, true),
      ];
      render(<EvolveproSelectTable rows={rows} onToggle={vi.fn()} />);

      const checked = screen
        .getAllByRole("checkbox")
        .filter((cb) => (cb as HTMLInputElement).checked);
      const unchecked = screen
        .getAllByRole("checkbox")
        .filter((cb) => !(cb as HTMLInputElement).checked);

      expect(checked).toHaveLength(2);
      expect(unchecked).toHaveLength(1);
    });
  });

  describe("empty state", () => {
    it("renders empty state message when rows is empty", () => {
      render(<EvolveproSelectTable rows={[]} onToggle={vi.fn()} />);
      expect(screen.getByText(/no candidates to display/i)).toBeInTheDocument();
    });
  });
});
