/**
 * JanusStepView — step 3.1, the Janus instrument settings step.
 *
 * The controls tested here used to live on 2.1 (inputs). They are their own
 * major step now so a sequencing-only operator never has to walk past them, and
 * the step must stay optional: nothing on it gates a run and its Next simply
 * carries on to step 4.
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("@/lib/ipc-mame", () => ({
  sendRequest: vi.fn(),
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
}));
// Stubbed to its open/closed state: what matters here is that the step reaches
// the dialog, not what the dialog draws (that is its own test file).
vi.mock("@/components/mame/dialogs/JanusMappingDialog", () => ({
  JanusMappingDialog: ({ open }: { open: boolean }) =>
    open ? <div data-testid="janus-mapping-dialog" /> : null,
}));

import { JanusStepView } from "./JanusStepView";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import { DEFAULT_JANUS_SETTINGS } from "@/lib/mame/janusSettings";

describe("JanusStepView", () => {
  beforeEach(() => {
    useMameAppStore.setState({
      mamePhase: "janus",
      currentMameSubStep: "janus.settings",
      janusSettings: DEFAULT_JANUS_SETTINGS,
      janusAutosave: null,
      janusMappingAutosave: null,
      verdicts: [],
      summary: null,
    });
  });

  it("carries the transfer volume and writes edits to the store", () => {
    render(<JanusStepView />);

    const field = screen.getByLabelText(/Transfer volume/i) as HTMLInputElement;
    expect(field.value).toBe(String(DEFAULT_JANUS_SETTINGS.volume));

    fireEvent.change(field, { target: { value: "45" } });

    expect(useMameAppStore.getState().janusSettings.volume).toBe(45);
  });

  it("opens the instrument settings dialog", () => {
    render(<JanusStepView />);
    expect(screen.queryByTestId("janus-mapping-dialog")).toBeNull();

    fireEvent.click(
      screen.getByRole("button", { name: "Open Janus instrument settings" }),
    );

    expect(screen.getByTestId("janus-mapping-dialog")).toBeTruthy();
  });

  it("reaches the settings before a run, when there is nothing to export yet", () => {
    render(<JanusStepView />);

    expect(
      screen.getByRole("button", { name: "Open Janus instrument settings" }),
    ).toBeEnabled();
  });

  it("says the step can be skipped", () => {
    render(<JanusStepView />);

    expect(screen.getByTestId("janus-optional-note").textContent).toMatch(
      /optional/i,
    );
  });

  it("redirects a foreign sub-step to 3.1 instead of rendering blank", () => {
    useMameAppStore.setState({ currentMameSubStep: "activity.ingest" });
    render(<JanusStepView />);

    expect(screen.getByRole("status").textContent).toBeTruthy();
    expect(screen.queryByLabelText(/Transfer volume/i)).toBeNull();
  });
});
