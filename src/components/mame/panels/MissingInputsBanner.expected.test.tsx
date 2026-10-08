/**
 * Re-pointing a lost expected workbook from the banner is a choice of that
 * workbook like any other, so it goes through `chooseExpectedPath`, which also
 * checks plate order and reads the sheets for the mapping picker. The banner
 * used to call the bare setter and skip both (item 14 of the 2026-09-29 input
 * audit).
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useMissingInputs } from "@/lib/mame/missingInputs";
import { useMameAppStore } from "@/store/mame/mameAppStore";

vi.mock("@tauri-apps/plugin-dialog", () => ({
  open: vi.fn(async () => "/proj/variants.xlsx"),
}));
vi.mock("@tauri-apps/plugin-fs", () => ({ stat: vi.fn(async () => ({ size: 10 })) }));
vi.mock("sonner", () => ({ toast: { warning: vi.fn() } }));

import { MissingInputsBanner } from "./MissingInputsBanner";

describe("MissingInputsBanner: expected workbook", () => {
  const chooseExpectedPath = vi.fn();
  const setExpectedPath = vi.fn();

  beforeEach(() => {
    chooseExpectedPath.mockReset();
    setExpectedPath.mockReset();
    useMameAppStore.setState({ expectedPath: "", chooseExpectedPath, setExpectedPath });
    useMissingInputs.getState().setMissing([{ field: "expectedPath", name: "variants.xlsx" }]);
  });

  it("routes the picked workbook through chooseExpectedPath", async () => {
    render(<MissingInputsBanner />);
    fireEvent.click(screen.getByRole("button", { name: /browse/i }));
    await waitFor(() => expect(chooseExpectedPath).toHaveBeenCalledWith("/proj/variants.xlsx"));
    expect(setExpectedPath).not.toHaveBeenCalled();
  });
});
