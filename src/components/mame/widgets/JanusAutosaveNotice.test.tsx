/**
 * The two automatic files, as reported after a run.
 *
 * A run that says "Analysis complete" while a file failed sends somebody to a
 * folder with no file in it, so all three outcomes have to be legible for each:
 * written, nothing to write, and could not write (with the reason).
 *
 * The instrument mapping is written without a confirmed deck, so what it left
 * blank or derived has to be readable here, and none of it may look like a
 * failure.
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
  warnings: [],
};

describe("JanusAutosaveNotice", () => {
  beforeEach(() => {
    useMameAppStore.setState({ janusAutosave: null, janusMappingAutosave: null });
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

  it("names the instrument mapping as its own file", () => {
    useMameAppStore.setState({
      janusMappingAutosave: {
        ...BASE,
        status: "saved",
        output_path: "D:/project/260804_MAME_96_janus.csv",
        row_count: 42,
      },
    });

    render(<JanusAutosaveNotice />);

    const notice = screen.getByTestId("janus-mapping-autosave-notice");
    expect(notice).toHaveAttribute("data-status", "saved");
    expect(notice).toHaveTextContent("260804_MAME_96_janus.csv");
    expect(notice).toHaveTextContent(/instrument mapping/i);
    // The File menu item is gone; no copy may still send anyone there.
    expect(notice).not.toHaveTextContent(/File > Export Janus Mapping/i);
  });

  it("reports a generated deck without calling the run a failure", () => {
    // The v0.15.8 change: what the export worked out for itself is reported
    // rather than refused. The blank liquid class that used to be reported
    // beside this went with its column, so the generated plate names are the
    // warning the export still raises.
    useMameAppStore.setState({
      janusMappingAutosave: {
        ...BASE,
        status: "saved",
        output_path: "D:/project/260804_MAME_96_janus.csv",
        row_count: 3,
        warnings: [
          {
            code: "derived_source_rack",
            severity: "warning",
            message:
              "plate names generated from the plates of this run " +
              "(NB01 -> Stock plate1, destination -> final culture plate)",
            mutant_ids: [],
          },
        ],
      },
    });

    render(<JanusAutosaveNotice />);

    const notice = screen.getByTestId("janus-mapping-autosave-notice");
    // Saved, not failed: the warning describes the file, it does not withhold it.
    expect(notice).toHaveAttribute("data-status", "saved");
    expect(notice).toHaveAttribute("role", "status");
    expect(notice).toHaveTextContent(/generated from the plates of this run/i);
    expect(notice).toHaveTextContent(/Stock plate1/);
  });

  it("shows both files at once, each with its own outcome", () => {
    useMameAppStore.setState({
      janusAutosave: {
        ...BASE,
        status: "saved",
        output_path: "D:/project/run_picks.csv",
        row_count: 2,
      },
      janusMappingAutosave: {
        ...BASE,
        status: "saved",
        output_path: "D:/project/run_janus.csv",
        row_count: 2,
      },
    });

    render(<JanusAutosaveNotice />);

    expect(screen.getByTestId("janus-autosave-notice")).toHaveTextContent(
      "run_picks.csv",
    );
    expect(screen.getByTestId("janus-mapping-autosave-notice")).toHaveTextContent(
      "run_janus.csv",
    );
  });

  it("says plainly that nothing was written when nothing was selected", () => {
    useMameAppStore.setState({ janusAutosave: { ...BASE, status: "skipped" } });

    render(<JanusAutosaveNotice />);

    const notice = screen.getByTestId("janus-autosave-notice");
    expect(notice).toHaveAttribute("data-status", "skipped");
    expect(notice).toHaveTextContent(/no selection list was written/i);
  });

  it("surfaces the reason a file could not be written", () => {
    useMameAppStore.setState({
      janusAutosave: {
        ...BASE,
        status: "failed",
        errors: [
          {
            code: "autosave_failed",
            severity: "error",
            message: "disk went away",
            mutant_ids: [],
          },
        ],
      },
    });

    render(<JanusAutosaveNotice />);

    const notice = screen.getByTestId("janus-autosave-notice");
    expect(notice).toHaveAttribute("data-status", "failed");
    expect(notice).toHaveAttribute("role", "alert");
    expect(notice).toHaveTextContent(/disk went away/i);
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
