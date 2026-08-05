/**
 * The automatic pick list, as reported after a run.
 *
 * A run that says "Analysis complete" while its file failed sends somebody to a
 * folder with no file in it, so all three outcomes have to be legible: written,
 * nothing to write, and could not write (with the reason).
 *
 * The wording carries a second duty. The file is the selection, not a robot
 * worklist, and the place that builds a worklist is the Janus settings dialog,
 * not the File menu it was removed from in v0.14.7.
 */
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/ipc-mame", () => ({
  sendRequest: vi.fn(),
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
}));

import { useMameAppStore } from "@/store/mame/mameAppStore";
import { JanusAutosaveNotice } from "./JanusAutosaveNotice";

const BASE = {
  output_path: null,
  format: "csv" as const,
  row_count: 0,
  excluded: [],
  excluded_count: 0,
  errors: [],
};

describe("JanusAutosaveNotice", () => {
  beforeEach(() => {
    useMameAppStore.setState({ janusAutosave: null });
  });

  it("renders nothing before a run has reported one", () => {
    const { container } = render(<JanusAutosaveNotice />);
    expect(container).toBeEmptyDOMElement();
  });

  it("names the file and the pick count when it was written", () => {
    useMameAppStore.setState({
      janusAutosave: {
        ...BASE,
        status: "saved",
        output_path: "D:/project/260804_MAME_96_picks.csv",
        row_count: 42,
      },
    });

    render(<JanusAutosaveNotice />);

    const notice = screen.getByTestId("janus-autosave-notice");
    expect(notice).toHaveAttribute("data-status", "saved");
    expect(notice).toHaveTextContent("42");
    expect(notice).toHaveTextContent("260804_MAME_96_picks.csv");
  });

  it("calls the file a selection and points the worklist elsewhere", () => {
    // The file carries no liquid class, no volume and no rack number, so a
    // reader who takes it for a worklist takes it to the instrument.
    useMameAppStore.setState({
      janusAutosave: {
        ...BASE,
        status: "saved",
        output_path: "D:/project/260804_MAME_96_picks.csv",
        row_count: 42,
      },
    });

    render(<JanusAutosaveNotice />);

    const notice = screen.getByTestId("janus-autosave-notice");
    expect(notice).toHaveTextContent(/selection list, not a robot worklist/i);
    expect(notice).toHaveTextContent(/Janus instrument settings/i);
    // The File menu item is gone; no copy may still send anyone there.
    expect(notice).not.toHaveTextContent(/File > Export Janus Mapping/i);
  });

  it("says plainly that nothing was written when nothing was selected", () => {
    useMameAppStore.setState({ janusAutosave: { ...BASE, status: "skipped" } });

    render(<JanusAutosaveNotice />);

    const notice = screen.getByTestId("janus-autosave-notice");
    expect(notice).toHaveAttribute("data-status", "skipped");
    expect(notice).toHaveTextContent(/no selection list was written/i);
  });

  it("surfaces the reason a mapping could not be written", () => {
    // The common one: device9 has no default liquid class, because that value
    // decides how the robot handles the cells.
    useMameAppStore.setState({
      janusAutosave: {
        ...BASE,
        status: "failed",
        errors: [
          {
            code: "missing_liquid_class",
            message: "liquid_class is required for the device9 schema",
            mutant_ids: [],
          },
        ],
      },
    });

    render(<JanusAutosaveNotice />);

    const notice = screen.getByTestId("janus-autosave-notice");
    expect(notice).toHaveAttribute("data-status", "failed");
    expect(notice).toHaveAttribute("role", "alert");
    expect(notice).toHaveTextContent(/liquid_class is required/i);
  });

  it("reports clones left out of the mapping", () => {
    useMameAppStore.setState({
      janusAutosave: {
        ...BASE,
        status: "saved",
        output_path: "D:/project/run_janus.csv",
        row_count: 3,
        excluded_count: 5,
      },
    });

    render(<JanusAutosaveNotice />);

    expect(screen.getByTestId("janus-autosave-notice")).toHaveTextContent("5");
  });
});
