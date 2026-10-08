import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { FileField } from "./FileField";

describe("FileField", () => {
  it("renders a browse-first filename field with full path only in title", () => {
    const fullPath = String.raw`D:\_workspace\cc\kuma\samples\sample_plasmid.gb`;

    render(
      <FileField
        label="CDS sequence"
        value={fullPath}
        onChange={vi.fn()}
        onBrowse={vi.fn()}
        placeholder="Select a file"
        stateLabel="Required"
        filled
        helperText="Reference CDS sequence"
        noPathLabel="No path selected"
        readyLabel="Ready"
        browseAriaLabel="Browse CDS sequence"
      />,
    );

    const input = screen.getByLabelText("CDS sequence");
    expect(input).toHaveValue("sample_plasmid.gb");
    expect(input).toHaveAttribute("title", fullPath);
    expect(input).toHaveAttribute("readonly");
    expect(screen.getByText("sample_plasmid.gb")).toHaveAttribute(
      "title",
      fullPath,
    );
    expect(screen.queryByDisplayValue(fullPath)).toBeNull();
  });

  it("keeps empty file fields browse-first without a misleading title", () => {
    render(
      <FileField
        label="Barcode seeds"
        value=""
        onChange={vi.fn()}
        onBrowse={vi.fn()}
        placeholder="Select xlsx"
        stateLabel="Required"
        filled={false}
        noPathLabel="No path selected"
        readyLabel="Ready"
      />,
    );

    const input = screen.getByRole("textbox", { name: "Barcode seeds" });
    expect(input).toHaveValue("");
    expect(input).toHaveAttribute("readonly");
    expect(input).not.toHaveAttribute("title");
    expect(screen.getByText("No path selected")).toBeTruthy();
  });
});
