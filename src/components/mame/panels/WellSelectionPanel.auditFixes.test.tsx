import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { WellSelectionPanel } from "@/components/mame/panels/WellSelectionPanel";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import type { BuildWellLayoutResult } from "@/types/mame/well_layout";

const sendRequest = vi.hoisted(() => vi.fn());
vi.mock("@/lib/ipc-mame", () => ({ sendRequest }));
vi.mock("@tauri-apps/plugin-dialog", () => ({ save: vi.fn() }));

const draft: BuildWellLayoutResult = {
  draft: [{ well: "A1", sample: "M1" }, { well: "H12", sample: "WT" }],
  count: 2,
  dropped_mutant_ids: [],
  wt_well: "H12",
};

beforeEach(() => {
  sendRequest.mockResolvedValue(draft);
  useMameAppStore.setState({
    expectedPath: "/project/variants.xlsx",
    variantSheet: null,
    variantColumn: null,
    selectedWells: null,
    wtPlacement: "last_well",
    wtWell: "H12",
  });
});

describe("well selection default matches draft", () => {
  it("keeps the last-well control selected in the untouched grid", async () => {
    render(<WellSelectionPanel />);
    expect(await screen.findByRole("gridcell", { name: /^Well H12,/ })).toHaveAttribute("aria-selected", "true");
  });

  it("does not select an unoccupied leading well by default", async () => {
    render(<WellSelectionPanel />);
    expect(await screen.findByRole("gridcell", { name: /^Well B1,/ })).toHaveAttribute("aria-selected", "false");
  });

  it("preserves the untouched control when deselecting the mutant", async () => {
    render(<WellSelectionPanel />);
    fireEvent.pointerDown(await screen.findByRole("gridcell", { name: /^Well A1,/ }));
    expect(useMameAppStore.getState().selectedWells).toEqual(["H12"]);
  });

  it("honors an explicit selection of the actual occupied wells", async () => {
    useMameAppStore.setState({ selectedWells: ["A1", "H12"] });
    render(<WellSelectionPanel />);
    expect(await screen.findByRole("gridcell", { name: /^Well H12,/ })).toHaveAttribute("aria-selected", "true");
  });

  it("returns to null when the actual draft selection is restored", async () => {
    useMameAppStore.setState({ selectedWells: ["H12"] });
    render(<WellSelectionPanel />);
    fireEvent.pointerDown(await screen.findByRole("gridcell", { name: /^Well A1,/ }));
    expect(useMameAppStore.getState().selectedWells).toBeNull();
  });
});
