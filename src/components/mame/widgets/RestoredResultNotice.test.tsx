/**
 * RestoredResultNotice — the provenance warning on a restored run.
 *
 * The contract this pins: silent for a run this build produced, explicit about
 * the version when it did not, never destructive, and never nagging once the
 * operator has answered for that snapshot.
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/ipc-mame", () => ({
  sendRequest: vi.fn(),
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
}));
// Reassigned by the project-switch test: the MAME layout stays mounted while
// the operator opens another project, so the notice has to re-read the stored
// answer instead of latching it at mount.
let currentProject = { path: "/projects/qa", name: "qa", scratch: false };
vi.mock("@/state/projectContext", () => ({
  useKumaProject: () => currentProject,
}));

import { useMameAppStore } from "@/store/mame/mameAppStore";
import { hasAcknowledgedResultVersion } from "@/lib/mame/resultProvenance";
import { RestoredResultNotice } from "./RestoredResultNotice";

describe("RestoredResultNotice", () => {
  beforeEach(() => {
    localStorage.clear();
    currentProject = { path: "/projects/qa", name: "qa", scratch: false };
    useMameAppStore.setState({ restoredResultProvenance: null, isAnalyzing: false });
  });

  it("renders nothing for a result this build produced", () => {
    const { container } = render(<RestoredResultNotice />);
    expect(container).toBeEmptyDOMElement();
  });

  it("names the version that produced an older result", () => {
    useMameAppStore.setState({
      restoredResultProvenance: { version: "0.15.9", relation: "older" },
    });

    render(<RestoredResultNotice />);

    const notice = screen.getByTestId("restored-result-notice");
    expect(notice).toHaveAttribute("data-relation", "older");
    expect(notice.textContent).toContain("0.15.9");
  });

  it("says so when the snapshot recorded no version", () => {
    useMameAppStore.setState({
      restoredResultProvenance: { version: null, relation: "unknown" },
    });

    render(<RestoredResultNotice />);

    const notice = screen.getByTestId("restored-result-notice");
    expect(notice).toHaveAttribute("data-relation", "unknown");
    expect(notice.textContent).toMatch(/no kuma version/i);
  });

  it("offers a re-run only when a run can be started from the screen", () => {
    useMameAppStore.setState({
      restoredResultProvenance: { version: "0.15.9", relation: "older" },
    });

    const { rerender } = render(<RestoredResultNotice />);
    expect(screen.queryByRole("button", { name: /Re-run analysis/i })).toBeNull();

    const onRunRequest = vi.fn();
    rerender(<RestoredResultNotice onRunRequest={onRunRequest} />);
    fireEvent.click(screen.getByRole("button", { name: /Re-run analysis/i }));

    expect(onRunRequest).toHaveBeenCalledTimes(1);
    // The flag goes with the results the run is about to replace.
    expect(useMameAppStore.getState().restoredResultProvenance).toBeNull();
  });

  it("does not start a run while one is already going", () => {
    useMameAppStore.setState({
      restoredResultProvenance: { version: "0.15.9", relation: "older" },
      isAnalyzing: true,
    });

    render(<RestoredResultNotice onRunRequest={vi.fn()} />);

    expect(screen.getByRole("button", { name: /Re-run analysis/i })).toBeDisabled();
  });

  it("keeps the results, records the choice, and stops nagging", () => {
    useMameAppStore.setState({
      restoredResultProvenance: { version: "0.15.9", relation: "older" },
    });

    render(<RestoredResultNotice />);
    fireEvent.click(screen.getByRole("button", { name: /Keep these results/i }));

    expect(screen.queryByTestId("restored-result-notice")).toBeNull();
    expect(hasAcknowledgedResultVersion("/projects/qa", "0.15.9")).toBe(true);
    // Keeping is not discarding: the results themselves are untouched.
    expect(useMameAppStore.getState().restoredResultProvenance).not.toBeNull();
  });

  it("stays quiet on a later restore of the same snapshot", () => {
    useMameAppStore.setState({
      restoredResultProvenance: { version: "0.15.9", relation: "older" },
    });
    const first = render(<RestoredResultNotice />);
    fireEvent.click(screen.getByRole("button", { name: /Keep these results/i }));
    first.unmount();

    render(<RestoredResultNotice />);

    expect(screen.queryByTestId("restored-result-notice")).toBeNull();
  });

  it("speaks up again for a snapshot from a different version", () => {
    useMameAppStore.setState({
      restoredResultProvenance: { version: "0.15.9", relation: "older" },
    });
    const first = render(<RestoredResultNotice />);
    fireEvent.click(screen.getByRole("button", { name: /Keep these results/i }));
    first.unmount();

    useMameAppStore.setState({
      restoredResultProvenance: { version: "0.15.14", relation: "older" },
    });
    render(<RestoredResultNotice />);

    expect(screen.getByTestId("restored-result-notice").textContent).toContain("0.15.14");
  });
  it("keeps speaking up after an in-session switch to another project", () => {
    // The MAME layout does not unmount between projects, so a dismissal latched
    // at mount would silence a second project's stale snapshot.
    useMameAppStore.setState({
      restoredResultProvenance: { version: "0.15.9", relation: "older" },
    });
    const { rerender } = render(<RestoredResultNotice />);
    fireEvent.click(screen.getByRole("button", { name: /Keep these results/i }));
    expect(screen.queryByTestId("restored-result-notice")).toBeNull();

    currentProject = { path: "/projects/other", name: "other", scratch: false };
    useMameAppStore.setState({
      restoredResultProvenance: { version: "0.15.9", relation: "older" },
    });
    rerender(<RestoredResultNotice />);

    expect(screen.getByTestId("restored-result-notice")).toBeTruthy();
    expect(hasAcknowledgedResultVersion("/projects/other", "0.15.9")).toBe(false);
  });
});
