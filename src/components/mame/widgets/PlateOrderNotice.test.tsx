/**
 * What the operator actually sees when the expected workbook contradicts itself.
 *
 * The incident this guards against is silent, so the assertions are about the
 * facts being on screen (which sheet, which well, what is missing, what makes
 * the sheet order irrelevant), not about a banner merely existing.
 *
 * Since v0.15.6 the notice never stops a run, and it says nothing once the
 * operator has named the sheet and column the variant list is read from.
 */
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/ipc-mame", () => ({
  sendRequest: vi.fn(),
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
}));

import { useMameAppStore } from "@/store/mame/mameAppStore";
import { PlateOrderNotice } from "./PlateOrderNotice";

const REPORT = {
  comparable: true,
  mismatched: true,
  plate_sheet: "Fwd List",
  examples: [{ well: "A2", plate: "K53I", expected: "I92D" }],
  missing_from_expected: ["Q17R"],
  absent_from_plate: [],
};

describe("PlateOrderNotice", () => {
  beforeEach(() => {
    useMameAppStore.setState({
      plateOrderFinding: null,
      expectedPath: "D:/project/KURO_expected.xlsx",
      sampleMapPath: "",
      wellLayout: null,
      variantSelectionExplicit: false,
    });
  });

  it("renders nothing when there is no finding", () => {
    const { container } = render(<PlateOrderNotice />);
    expect(container).toBeEmptyDOMElement();
  });

  it("states the disagreement without stopping anything", () => {
    useMameAppStore.setState({
      plateOrderFinding: { ...REPORT, severity: "info" },
    });

    render(<PlateOrderNotice />);

    const notice = screen.getByTestId("plate-order-notice");
    expect(notice).toHaveAttribute("data-severity", "info");
    // Information, not an error: the run is allowed either way.
    expect(notice).toHaveAttribute("role", "status");
    // Which file, which sheet, which well, and what the plate carries that the
    // expected sheet does not.
    expect(notice).toHaveTextContent("KURO_expected.xlsx");
    expect(notice).toHaveTextContent("Fwd List");
    expect(notice).toHaveTextContent("A2");
    expect(notice).toHaveTextContent("K53I");
    expect(notice).toHaveTextContent("I92D");
    expect(notice).toHaveTextContent("Q17R");
    // The way to take the sheet order out of the run, without mentioning a
    // Build well layout button that no longer exists.
    expect(notice).toHaveTextContent(/sample map/i);
    expect(notice).not.toHaveTextContent(/build well layout/i);
  });

  it("keeps a finding the sidecar graded blocking to an informational tone", () => {
    useMameAppStore.setState({
      plateOrderFinding: { ...REPORT, severity: "blocking" },
    });

    render(<PlateOrderNotice />);

    expect(screen.getByTestId("plate-order-notice")).toHaveAttribute(
      "data-severity",
      "info",
    );
  });

  it("says nothing once the operator picked the sheet and column themselves", () => {
    useMameAppStore.setState({
      plateOrderFinding: { ...REPORT, severity: "blocking" },
      variantSelectionExplicit: true,
    });

    const { container } = render(<PlateOrderNotice />);

    expect(container).toBeEmptyDOMElement();
  });
});
