/**
 * ClonePlateCrosscheckNotice: the wells it names, and the states it stays quiet in.
 *
 * The silent states carry the weight. A notice that renders on every workbook
 * becomes furniture, and one that renders on a status it does not understand
 * tells an operator a plate disagrees when nothing was compared.
 *
 * Nothing here pins a sentence. The prose lives in the locale files and is
 * edited independently; `i18n-lint` proves the keys exist and `i18n-parity`
 * compares key sets, so what is worth asserting in the DOM is the numbers, the
 * well names and the role.
 */
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/ipc-mame", () => ({
  sendRequest: vi.fn(),
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
}));

import type { ClonePlateCrosscheck } from "@/types/mame/models";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import { ClonePlateCrosscheckNotice } from "./ClonePlateCrosscheckNotice";

function finding(patch: Partial<ClonePlateCrosscheck> = {}): ClonePlateCrosscheck {
  return {
    status: "mismatch",
    plate_sheet: "Fwd List",
    wells_compared: 95,
    mismatch_count: 87,
    examples: [
      { well: "A1", primer_plate: "S22T", clone_plate: "S11I" },
      { well: "B1", primer_plate: "S11I", clone_plate: "S22T" },
    ],
    ...patch,
  };
}

describe("ClonePlateCrosscheckNotice", () => {
  beforeEach(() => {
    useMameAppStore.setState({ clonePlateCrosscheck: null });
  });

  it("says nothing before a validation has run", () => {
    render(<ClonePlateCrosscheckNotice />);

    expect(screen.queryByTestId("clone-plate-crosscheck-notice")).toBeNull();
  });

  it("says nothing for a status that is not a mismatch", () => {
    // The sidecar sends only "mismatch", and an older or newer one that sends
    // something else must not have it read as a disagreement.
    useMameAppStore.setState({
      clonePlateCrosscheck: finding({ status: "stated_wells", mismatch_count: 0 }),
    });

    render(<ClonePlateCrosscheckNotice />);

    expect(screen.queryByTestId("clone-plate-crosscheck-notice")).toBeNull();
  });

  it("names how many wells differ, of how many, and the first few", () => {
    useMameAppStore.setState({ clonePlateCrosscheck: finding() });

    render(<ClonePlateCrosscheckNotice />);

    const notice = screen.getByTestId("clone-plate-crosscheck-notice");
    expect(notice).toHaveAttribute("role", "status");
    expect(notice.textContent).toContain("87");
    expect(notice.textContent).toContain("95");
    expect(notice.textContent).toContain("Fwd List");
    expect(notice.textContent).toContain("A1");
    expect(notice.textContent).toContain("S22T");
    expect(notice.textContent).toContain("B1");
  });

  it("is not an alert, because it refuses nothing", () => {
    // `PlateOrderNotice` is role="alert" beside a Run button that will not
    // press. This one sits beside a Run button that works.
    useMameAppStore.setState({ clonePlateCrosscheck: finding() });

    render(<ClonePlateCrosscheckNotice />);

    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("names a well where one side places nothing", () => {
    useMameAppStore.setState({
      clonePlateCrosscheck: finding({
        mismatch_count: 1,
        examples: [{ well: "C1", primer_plate: "N28S", clone_plate: "" }],
      }),
    });

    render(<ClonePlateCrosscheckNotice />);

    expect(screen.getByTestId("clone-plate-crosscheck-notice").textContent).toContain(
      "C1",
    );
  });
});
