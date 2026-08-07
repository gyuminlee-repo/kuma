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
import { render, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ sendRequest: vi.fn() }));

vi.mock("@/lib/ipc-mame", () => ({
  sendRequest: mocks.sendRequest,
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
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
});
