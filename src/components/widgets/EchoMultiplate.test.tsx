import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { adaptEchoRows, adaptDestCellsEcho, type EchoDryRunRow } from "@/lib/echoJanusAdapter";
import { EchoPlateView } from "./EchoPlateView";
import { DestPlateView } from "./DestPlateView";

const rows: EchoDryRunRow[] = [1, 2].map((plate) => ({
  source_plate: `Source [${plate}]`, source_well: "A1",
  source_well_name: `primer-${plate}`, dest_plate: `Destination [${plate}]`,
  dest_well: "A1", dest_well_name: "M1A", mutation: "M1A", transfer_vol: plate * 25,
}));

describe("Echo physical plate identity", () => {
  it("retains source identity and separates identical mutation/well destinations", () => {
    expect(adaptEchoRows(rows)).toMatchObject([
      { sourcePlate: "Source [1]", well: "A01" },
      { sourcePlate: "Source [2]", well: "A01" },
    ]);
    expect(adaptDestCellsEcho(rows)).toMatchObject([
      { destPlate: "Destination [1]", fwdVol: 25 },
      { destPlate: "Destination [2]", fwdVol: 50 },
    ]);
  });

  it("selects source plates by name, preserves selection on reorder and clears stale popovers", () => {
    const { rerender } = render(<EchoPlateView cells={adaptEchoRows(rows)} title="Source" />);
    expect(screen.getByTitle(/primer-1/)).toBeInTheDocument();
    fireEvent.click(screen.getByTitle(/primer-1/));
    expect(screen.getByTestId("plate-popover-body")).toHaveTextContent("Source [1] A01");
    fireEvent.change(screen.getByRole("combobox", { name: "Source" }), { target: { value: "Source [2]" } });
    expect(screen.queryByTestId("plate-popover-body")).toBeNull();
    expect(screen.queryByTitle(/primer-1/)).toBeNull();
    expect(screen.getByTitle(/primer-2/)).toHaveAttribute("data-state", "closed");
    rerender(<EchoPlateView cells={adaptEchoRows([...rows].reverse())} title="Source" />);
    expect(screen.getByRole("combobox")).toHaveValue("Source [2]");
    rerender(<EchoPlateView cells={adaptEchoRows(rows.slice(0, 1))} title="Source" />);
    expect(screen.queryByRole("combobox")).toBeNull();
    expect(screen.getByTitle(/primer-1/)).toBeInTheDocument();
    rerender(<EchoPlateView cells={adaptEchoRows(rows)} title="Source" />);
    expect(screen.getByRole("combobox")).toHaveValue("Source [1]");
  });

  it("selects destination plates without combining completeness, volumes or focus", () => {
    const mixed = [rows[0], { ...rows[1], source_well: "B1" }];
    render(<DestPlateView cells={adaptDestCellsEcho(mixed)} sourceMethod="echo" title="Destination" />);
    const first = screen.getByTitle(/M1A.*F=✓ R=✗/);
    fireEvent.click(first);
    expect(screen.getByTestId("plate-popover-body")).toHaveTextContent("Destination [1] A1");
    fireEvent.change(screen.getByRole("combobox", { name: "Destination" }), { target: { value: "Destination [2]" } });
    expect(screen.queryByTestId("plate-popover-body")).toBeNull();
    const second = screen.getByTitle(/M1A.*F=✗ R=✓/);
    expect(second).toHaveAttribute("data-state", "partial");
    fireEvent.click(second);
    expect(screen.getByTestId("plate-popover-body")).toHaveTextContent("50 nL");
    expect(screen.getByTestId("plate-popover-body")).toHaveTextContent("Destination [2] A1");
  });

  it("keeps repeated mutations at distinct wells and merges padded coordinates only within a plate", () => {
    const cells = adaptDestCellsEcho([
      rows[0],
      { ...rows[0], source_well: "B1", dest_well: "A01" },
      { ...rows[0], dest_well: "A2" },
      rows[1],
    ]);
    expect(cells).toMatchObject([
      { destPlate: "Destination [1]", well: "A1", hasF: true, hasR: true },
      { destPlate: "Destination [1]", well: "A2", hasF: true, hasR: false },
      { destPlate: "Destination [2]", well: "A1", hasF: true, hasR: false },
    ]);
  });
});
