/**
 * ExcludedOccupantsNotice, what a finished run left off the plate.
 *
 * The three silent states are silent for different reasons and are kept apart
 * on purpose: no provenance at all (nothing has run), provenance without the
 * field (a result written before it existed, or a run that declared nothing),
 * and an empty map (a declaration that covered every occupant). All three mean
 * "nothing was left out", and drawing a notice for any of them would put a
 * warning on the ordinary run.
 *
 * On wording vs content. The prose lives in the locale files and is edited
 * independently, so nothing here pins a sentence. What is pinned is that every
 * excluded sample reaches the screen with its well, because that is the whole
 * content of the notice: `i18n-lint` proves a key exists and `i18n-parity`
 * compares key SETS, so a placeholder renamed on one side of `t(...)` ships a
 * literal `{{list}}` with every gate green. The two copy-edit-proof guards
 * below cover that class.
 */
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/ipc-mame", () => ({
  sendRequest: vi.fn(),
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
}));

import type { LayoutProvenance } from "@/types/mame/models";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import { ExcludedOccupantsNotice } from "./ExcludedOccupantsNotice";

function provenance(patch: Partial<LayoutProvenance> = {}): LayoutProvenance {
  return {
    source: "inferred_draft_layout",
    expected_path: "/proj/expected.xlsx",
    selected_wells: ["A1", "C1"],
    unused_wells: [],
    ...patch,
  };
}

describe("ExcludedOccupantsNotice", () => {
  beforeEach(() => {
    useMameAppStore.setState({ layoutProvenance: null });
  });

  it("names every excluded sample with the well it was drafted into", () => {
    useMameAppStore.setState({
      layoutProvenance: provenance({
        excluded_occupants: { B1: "M2", D1: "M4" },
      }),
    });

    render(<ExcludedOccupantsNotice />);

    const notice = screen.getByTestId("excluded-occupants-notice");
    expect(notice).toHaveTextContent("M2 (B1)");
    expect(notice).toHaveTextContent("M4 (D1)");
    // The count is the other half of the content, and 2 must come from the map
    // rather than from the two declared wells, which also number 2.
    expect(notice).toHaveTextContent("2");
    // Copy-edit-proof: no unresolved placeholder and no raw key echoed back.
    expect(notice.textContent).not.toContain("{{");
    expect(notice.textContent).not.toContain("mame.qc.");
  });

  it("says nothing when no run has reported a layout", () => {
    render(<ExcludedOccupantsNotice />);

    expect(screen.queryByTestId("excluded-occupants-notice")).toBeNull();
  });

  it("says nothing for a result written before the field existed", () => {
    useMameAppStore.setState({ layoutProvenance: provenance() });

    render(<ExcludedOccupantsNotice />);

    expect(screen.queryByTestId("excluded-occupants-notice")).toBeNull();
  });

  it("says nothing when the declaration covered every occupant", () => {
    useMameAppStore.setState({
      layoutProvenance: provenance({ excluded_occupants: {} }),
    });

    render(<ExcludedOccupantsNotice />);

    expect(screen.queryByTestId("excluded-occupants-notice")).toBeNull();
  });
});
