/**
 * What the operator actually sees when the expected workbook contradicts itself.
 *
 * The incident this guards against is silent, so the assertions are about the
 * facts being on screen (which sheet, which well, what is missing, what ends
 * the refusal), not about a banner merely existing.
 *
 * Since 2026-08-05 the notice accompanies a refused run: it is the explanation
 * next to a Run button `selectCanRun` holds down, so it renders as an alert and
 * it renders for every finding. It went quiet between v0.15.6 and then once the
 * operator named the sheet and column, which left the validation error those
 * same inputs do not clear with nothing on screen to explain it.
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
      wellLayout: null,
      variantSelectionExplicit: false,
    });
  });

  it("renders nothing when there is no finding", () => {
    const { container } = render(<PlateOrderNotice />);
    expect(container).toBeEmptyDOMElement();
  });

  it("states the disagreement as the reason the run is refused", () => {
    useMameAppStore.setState({
      plateOrderFinding: { ...REPORT, severity: "blocking" },
    });

    render(<PlateOrderNotice />);

    const notice = screen.getByTestId("plate-order-notice");
    expect(notice).toHaveAttribute("data-severity", "blocking");
    // An alert, not a status line: it sits beside a Run button that will not go.
    expect(notice).toHaveAttribute("role", "alert");
    // Which file, which sheet, which well, and what the plate carries that the
    // expected sheet does not.
    expect(notice).toHaveTextContent("KURO_expected.xlsx");
    expect(notice).toHaveTextContent("Fwd List");
    expect(notice).toHaveTextContent("A2");
    expect(notice).toHaveTextContent("K53I");
    expect(notice).toHaveTextContent("I92D");
    expect(notice).toHaveTextContent("Q17R");
    // What ends it: another workbook. Not a sample map, which places wells
    // without saying which plate they came from, and not a Build well layout
    // button that no longer exists.
    expect(notice).toHaveTextContent(/re-export/i);
    expect(notice).not.toHaveTextContent(/build well layout/i);
  });

  it("still shows once the operator picked the sheet and column themselves", () => {
    // Naming the rows to read is not an answer to "which of these two plates
    // was pipetted", and `validate_inputs` errors either way. Hiding here would
    // leave that error unexplained.
    useMameAppStore.setState({
      plateOrderFinding: { ...REPORT, severity: "blocking" },
      variantSelectionExplicit: true,
    });

    render(<PlateOrderNotice />);

    expect(screen.getByTestId("plate-order-notice")).toHaveAttribute(
      "data-severity",
      "blocking",
    );
  });
});
