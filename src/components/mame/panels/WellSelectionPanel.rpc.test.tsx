/**
 * The name the well grid asks the sidecar for.
 *
 * The panel draws the plate from the same RPC the run drafts its layout with,
 * and that method is registered as ``mame.build_well_layout`` in
 * python-core/sidecar_mame/dispatcher.py. Sending the bare ``build_well_layout``
 * reaches no handler, so the panel showed only "[-32601] Method not found" where
 * the plate should be, and the operator could not see or change the placement.
 * Nothing else caught it: the dispatcher name is checked against the dispatcher
 * file alone, and no test rendered this panel.
 */
import { fireEvent, render, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ sendRequest: vi.fn(), save: vi.fn() }));

vi.mock("@/lib/ipc-mame", () => ({
  sendRequest: mocks.sendRequest,
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
}));

// The save dialog and the toaster are host surfaces; the panel is under test,
// not Tauri. Both are stubbed so a click resolves to a path or to nothing.
vi.mock("@tauri-apps/plugin-dialog", () => ({ save: mocks.save }));
vi.mock("sonner", () => ({
  toast: { success: vi.fn(), warning: vi.fn(), error: vi.fn() },
}));

import { useMameAppStore } from "@/store/mame/mameAppStore";
import { WellSelectionPanel } from "./WellSelectionPanel";

describe("WellSelectionPanel RPC", () => {
  beforeEach(() => {
    mocks.sendRequest.mockReset();
    mocks.sendRequest.mockResolvedValue({
      draft: [{ seq: 1, well: "A1", mutant_id: "WT" }],
    });
    useMameAppStore.setState({
      expectedPath: "/tmp/expected.xlsx",
      variantSheet: null,
      variantColumn: null,
      selectedWells: null,
    });
  });

  it("calls the dispatcher-registered method name", async () => {
    render(<WellSelectionPanel />);

    await waitFor(() => expect(mocks.sendRequest).toHaveBeenCalled());
    expect(mocks.sendRequest).toHaveBeenCalledWith(
      "mame.build_well_layout",
      expect.objectContaining({ expected_mutations_xlsx: "/tmp/expected.xlsx" }),
    );
  });

  /**
   * Clicking describes the plate, it does not rearrange it.
   *
   * The grid used to seat occupant *i* on the *i*th selected well, so
   * deselecting B1 pulled WT out of C1 and into it while the operator was
   * looking at the cell they had just clicked.
   */
  it("leaves every variant in its own well when one is deselected", async () => {
    mocks.sendRequest.mockResolvedValue({
      draft: [
        { well: "A1", sample: "M1" },
        { well: "B1", sample: "M2" },
        { well: "C1", sample: "WT" },
      ],
      count: 3,
      dropped_mutant_ids: [],
    });

    const view = render(<WellSelectionPanel />);

    const cellFor = async (well: string) =>
      await view.findByRole("gridcell", { name: new RegExp(`^Well ${well},`) });

    await waitFor(async () => expect(await cellFor("C1")).toHaveTextContent("WT"));

    fireEvent.pointerDown(await cellFor("B1"));

    expect(await cellFor("A1")).toHaveTextContent("M1");
    expect(await cellFor("B1")).toHaveTextContent("M2");
    expect(await cellFor("C1")).toHaveTextContent("WT");
    expect((await cellFor("B1")).getAttribute("aria-selected")).toBe("false");
    // The declaration drops B1 and keeps the wells the campaign filled, in
    // plate order, rather than renumbering around the gap.
    expect(useMameAppStore.getState().selectedWells).toEqual(["A1", "C1"]);
  });

  /**
   * The worklist is asked for by the declared selection, not by the grid.
   *
   * Which wells a campaign fills decides which `{R}_{F}` barcodes it uses, and
   * the sidecar computes that from the same two calls the run makes. So what
   * this pins is the request: the selection reaches it verbatim (null included,
   * which means the whole draft there exactly as it does on a run) along with
   * the workbook that carries the seed names.
   */
  it("asks for the worklist with the declared selection and the barcode workbook", async () => {
    mocks.save.mockResolvedValue("/proj/out/barcode_worklist.csv");
    mocks.sendRequest.mockImplementation(async (method: string) =>
      method === "mame.export_barcode_worklist"
        ? {
            output_path: "/proj/out/barcode_worklist.csv",
            rows: 2,
            reverse_indices: [1, 3],
            forward_indices: [1],
            missing_seeds: [],
            excluded_occupants: {},
          }
        : { draft: [{ well: "A1", sample: "M1" }], count: 1, dropped_mutant_ids: [] },
    );
    useMameAppStore.setState({
      selectedWells: ["A1", "C1"],
      rawRunParams: {
        ...useMameAppStore.getState().rawRunParams,
        customBarcodesPath: "/proj/design/barcodes_sequence.xlsx",
      },
    });

    const view = render(<WellSelectionPanel />);
    const button = await view.findByRole("button", { name: /worklist/i });
    fireEvent.click(button);

    await waitFor(() =>
      expect(mocks.sendRequest).toHaveBeenCalledWith(
        "mame.export_barcode_worklist",
        expect.objectContaining({
          expected_mutations_xlsx: "/tmp/expected.xlsx",
          custom_barcodes_xlsx: "/proj/design/barcodes_sequence.xlsx",
          selected_wells: ["A1", "C1"],
          output_path: "/proj/out/barcode_worklist.csv",
        }),
      ),
    );
  });

  it("writes nothing when the save dialog is dismissed", async () => {
    mocks.save.mockResolvedValue(null);
    useMameAppStore.setState({ selectedWells: ["A1"] });

    const view = render(<WellSelectionPanel />);
    const button = await view.findByRole("button", { name: /worklist/i });
    fireEvent.click(button);

    await waitFor(() => expect(mocks.save).toHaveBeenCalled());
    expect(mocks.sendRequest).not.toHaveBeenCalledWith(
      "mame.export_barcode_worklist",
      expect.anything(),
    );
  });
});
