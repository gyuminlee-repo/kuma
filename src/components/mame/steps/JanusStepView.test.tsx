/**
 * JanusStepView: step 3.1, the Janus instrument settings step.
 *
 * The instrument configuration used to live on 2.1 (inputs). It is its own major
 * step now so a sequencing-only operator never has to walk past it, and the step
 * must stay optional: nothing on it gates a run and its Next simply carries on
 * to step 4.
 *
 * The step asks for nothing of its own. It used to carry a transfer volume input
 * above the panel, which wrote the same stored `janusSettings.volume` the
 * panel's Volume field writes, so the operator was answering one question twice.
 * What is left is the optional note, the notice for the pick list an analyze run
 * writes on its own, and the mapping panel.
 */

import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("@/lib/ipc-mame", () => ({
  sendRequest: vi.fn(),
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
}));
// Stubbed: what matters here is that the step renders the panel, not what the
// panel draws (that is its own test file, JanusMappingPanel.test.tsx).
vi.mock("@/components/mame/widgets/JanusMappingPanel", () => ({
  JanusMappingPanel: () => <div data-testid="janus-mapping-panel" />,
}));

import { JanusStepView } from "./JanusStepView";
import { useMameAppStore } from "@/store/mame/mameAppStore";

describe("JanusStepView", () => {
  beforeEach(() => {
    useMameAppStore.setState({
      mamePhase: "janus",
      currentMameSubStep: "janus.settings",
      janusAutosave: null,
      janusMappingAutosave: null,
      verdicts: [],
      summary: null,
    });
  });

  it("asks for no volume of its own; the panel's field is the only one", () => {
    render(<JanusStepView />);

    // The panel is stubbed here, so anything volume-shaped that turns up is the
    // step asking for the number a second time, which is what was removed.
    expect(screen.queryByLabelText(/volume/i)).toBeNull();
    expect(screen.queryByRole("spinbutton")).toBeNull();
  });

  it("renders the mapping panel inline, not behind a dialog", () => {
    render(<JanusStepView />);

    expect(screen.getByTestId("janus-mapping-panel")).toBeTruthy();
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
    // The step body is suppressed, not merely blank: both things it renders on
    // the happy path are absent. Asserted against what the step still draws,
    // since a query for a control it no longer has would pass either way.
    expect(screen.queryByTestId("janus-mapping-panel")).toBeNull();
    expect(screen.queryByTestId("janus-optional-note")).toBeNull();
  });
});
