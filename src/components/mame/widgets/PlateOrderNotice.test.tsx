/**
 * What the operator actually sees when the expected workbook contradicts itself.
 *
 * The incident this guards against is silent, so the assertions are about the
 * facts being on screen (which sheet, which well, what is missing, how to
 * proceed), not about a banner merely existing.
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
    });
  });

  it("renders nothing when there is no finding", () => {
    const { container } = render(<PlateOrderNotice />);
    expect(container).toBeEmptyDOMElement();
  });

  it("states the disagreement and the way out when it blocks the run", () => {
    useMameAppStore.setState({
      plateOrderFinding: { ...REPORT, severity: "blocking" },
    });

    render(<PlateOrderNotice />);

    const notice = screen.getByTestId("plate-order-notice");
    expect(notice).toHaveAttribute("data-severity", "blocking");
    expect(notice).toHaveAttribute("role", "alert");
    // Which file, which sheet, which well, and what the plate carries that the
    // expected sheet does not.
    expect(notice).toHaveTextContent("KURO_expected.xlsx");
    expect(notice).toHaveTextContent("Fwd List");
    expect(notice).toHaveTextContent("A2");
    expect(notice).toHaveTextContent("K53I");
    expect(notice).toHaveTextContent("I92D");
    expect(notice).toHaveTextContent("Q17R");
    // Not a dead end: the notice names the two inputs that clear it.
    expect(notice).toHaveTextContent(/sample map/i);
    expect(notice).toHaveTextContent(/well layout/i);
  });

  it("states it without alarm when this run takes its wells from elsewhere", () => {
    useMameAppStore.setState({
      plateOrderFinding: { ...REPORT, severity: "info" },
      sampleMapPath: "D:/project/sample_map.xlsx",
    });

    render(<PlateOrderNotice />);

    const notice = screen.getByTestId("plate-order-notice");
    expect(notice).toHaveAttribute("data-severity", "info");
    expect(notice).toHaveAttribute("role", "status");
    // No instruction to fix anything before running: this run is unaffected.
    expect(notice).not.toHaveTextContent(/Settle this before running/i);
  });

  it("softens a stored blocking finding once the well layout is confirmed", () => {
    // The finding was graded when no layout existed. Confirming one makes the
    // sheet order irrelevant to the run, and the notice has to follow.
    useMameAppStore.setState({
      plateOrderFinding: { ...REPORT, severity: "blocking" },
      wellLayout: { A1: "K53I" },
    });

    render(<PlateOrderNotice />);

    expect(screen.getByTestId("plate-order-notice")).toHaveAttribute(
      "data-severity",
      "info",
    );
  });
});
