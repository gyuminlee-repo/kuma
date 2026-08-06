/**
 * RestoredResultNotice — the statement that replaces another build's result.
 *
 * The contract this pins: silent for a run this build produced, explicit about
 * the version when it did not, offering only a re-run, and never suggesting the
 * saved result can go on being read. It also promises out loud that nothing was
 * deleted, because an operator who sees their verdicts vanish will assume the
 * opposite.
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/ipc-mame", () => ({
  sendRequest: vi.fn(),
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
}));
vi.mock("@/state/projectContext", () => ({
  useKumaProject: () => ({ path: "/projects/qa", name: "qa", scratch: false }),
}));

import { useMameAppStore } from "@/store/mame/mameAppStore";
import { RESULT_CONTRACT_REVISIONS } from "@/lib/mame/resultContract";
import { RestoredResultNotice } from "./RestoredResultNotice";

describe("RestoredResultNotice", () => {
  beforeEach(() => {
    useMameAppStore.setState({
      restoredResultProvenance: null,
      isAnalyzing: false,
      verdicts: [],
    });
  });

  it("renders nothing for a result this build produced", () => {
    const { container } = render(<RestoredResultNotice />);
    expect(container).toBeEmptyDOMElement();
  });

  it("names the version that produced an older result", () => {
    useMameAppStore.setState({
      restoredResultProvenance: {
        version: "0.15.9",
        contract: 0,
        relation: "older",
        changes: [...RESULT_CONTRACT_REVISIONS],
      },
    });

    render(<RestoredResultNotice />);

    const notice = screen.getByTestId("restored-result-notice");
    expect(notice).toHaveAttribute("data-relation", "older");
    expect(notice.textContent).toContain("0.15.9");
  });

  it("offers no way to keep reading the saved result", () => {
    // v0.15.20 had a "keep these results" button. Offering it told the operator
    // to run the lab on an obsolete engine, so it is gone for good.
    useMameAppStore.setState({
      restoredResultProvenance: {
        version: "0.15.9",
        contract: 0,
        relation: "older",
        changes: [...RESULT_CONTRACT_REVISIONS],
      },
    });

    render(<RestoredResultNotice onRunRequest={vi.fn()} />);

    expect(screen.queryByRole("button", { name: /keep/i })).toBeNull();
    expect(screen.getAllByRole("button")).toHaveLength(1);
  });

  it("says the saved run was not deleted", () => {
    useMameAppStore.setState({
      restoredResultProvenance: {
        version: "0.15.9",
        contract: 0,
        relation: "older",
        changes: [...RESULT_CONTRACT_REVISIONS],
      },
    });

    render(<RestoredResultNotice />);

    expect(screen.getByTestId("restored-result-notice").textContent).toMatch(
      /nothing was deleted/i,
    );
  });

  it("says so when the snapshot recorded no version", () => {
    useMameAppStore.setState({
      restoredResultProvenance: {
        version: null,
        contract: null,
        relation: "unknown",
        changes: [],
      },
    });

    render(<RestoredResultNotice />);

    const notice = screen.getByTestId("restored-result-notice");
    expect(notice).toHaveAttribute("data-relation", "unknown");
    expect(notice.textContent).toMatch(/no kuma version/i);
  });

  it("points a newer snapshot at the version that wrote it", () => {
    useMameAppStore.setState({
      restoredResultProvenance: {
        version: "9.9.9",
        contract: 99,
        relation: "newer",
        changes: [],
      },
    });

    render(<RestoredResultNotice />);

    expect(screen.getByTestId("restored-result-notice").textContent).toMatch(
      /newer than this build/i,
    );
  });

  it("starts a re-run from the screen that can start one", () => {
    useMameAppStore.setState({
      restoredResultProvenance: {
        version: "0.15.9",
        contract: 0,
        relation: "older",
        changes: [...RESULT_CONTRACT_REVISIONS],
      },
    });

    const { rerender } = render(<RestoredResultNotice />);
    expect(screen.queryByRole("button", { name: /Re-run analysis/i })).toBeNull();

    const onRunRequest = vi.fn();
    rerender(<RestoredResultNotice onRunRequest={onRunRequest} />);
    fireEvent.click(screen.getByRole("button", { name: /Re-run analysis/i }));

    expect(onRunRequest).toHaveBeenCalledTimes(1);
  });

  it("does not offer a re-run while one is already going", () => {
    useMameAppStore.setState({
      restoredResultProvenance: {
        version: "0.15.9",
        contract: 0,
        relation: "older",
        changes: [...RESULT_CONTRACT_REVISIONS],
      },
      isAnalyzing: true,
    });

    render(<RestoredResultNotice onRunRequest={vi.fn()} />);

    expect(screen.getByRole("button", { name: /Re-run analysis/i })).toBeDisabled();
  });

  it("stops offering a re-run once this build has produced verdicts", () => {
    // A finished run clears the provenance, but a race that left both set must
    // not show a re-run button over a result that is already current.
    useMameAppStore.setState({
      restoredResultProvenance: {
        version: "0.15.9",
        contract: 0,
        relation: "older",
        changes: [...RESULT_CONTRACT_REVISIONS],
      },
      verdicts: [{ barcode: "NB01", verdict: "PASS" } as never],
    });

    render(<RestoredResultNotice onRunRequest={vi.fn()} />);

    expect(screen.queryByRole("button", { name: /Re-run analysis/i })).toBeNull();
  });
});
