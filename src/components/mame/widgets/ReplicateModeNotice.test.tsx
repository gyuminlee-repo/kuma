/**
 * The trigger is the comparison, not the mode. These three cases are the ones
 * that separate it from "fire when pooled": a subset selection must be called
 * out even though it is not pooled, and a pooled run of a folder that holds one
 * native barcode must not be, because nothing was left out of it.
 */
import { render, screen, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/ipc-mame", () => ({
  sendRequest: vi.fn(),
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
}));

import { useMameAppStore } from "@/store/mame/mameAppStore";
import { ReplicateModeNotice } from "./ReplicateModeNotice";

afterEach(cleanup);

function setAxis(detectedBarcodeCount: number | null, selectedNativeBarcodes: string[] | null) {
  useMameAppStore.setState({ detectedBarcodeCount, selectedNativeBarcodes });
}

describe("ReplicateModeNotice", () => {
  it("states the shortfall when one of three detected barcodes was scored", () => {
    setAxis(3, ["sort_barcode07"]);

    render(<ReplicateModeNotice />);

    const notices = screen.getAllByTestId("replicate-mode-notice");
    expect(notices).toHaveLength(1);
    expect(notices[0]).toHaveAttribute("data-mode", "subset");
    expect(notices[0]).toHaveAttribute("data-detected", "3");
    expect(notices[0]).toHaveAttribute("data-replicates", "1");
    expect(notices[0].textContent).toContain("3");
  });

  it("states the shortfall when three detected barcodes were pooled into one plate", () => {
    setAxis(3, []);

    render(<ReplicateModeNotice />);

    const notices = screen.getAllByTestId("replicate-mode-notice");
    expect(notices).toHaveLength(1);
    expect(notices[0]).toHaveAttribute("data-mode", "pooled");
    expect(notices[0]).toHaveAttribute("data-replicates", "1");
    // The count of what was folded together is the whole point of the line.
    expect(notices[0].textContent).toContain("3");
  });

  it("says nothing when the folder held one native barcode", () => {
    setAxis(1, []);

    render(<ReplicateModeNotice />);

    expect(screen.queryAllByTestId("replicate-mode-notice")).toHaveLength(0);
  });

  it("says nothing when every detected barcode became a replicate", () => {
    setAxis(2, ["sort_barcode07", "sort_barcode08"]);

    render(<ReplicateModeNotice />);

    expect(screen.queryAllByTestId("replicate-mode-notice")).toHaveLength(0);
  });

  it("says nothing when no run has stated an axis", () => {
    setAxis(null, null);

    render(<ReplicateModeNotice />);

    expect(screen.queryAllByTestId("replicate-mode-notice")).toHaveLength(0);
  });
});
