import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const { classifyRound, roundState } = vi.hoisted(() => ({
  classifyRound: vi.fn(),
  roundState: { rounds: [], active_round_id: null as string | null },
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock("@/lib/ipc-mame", () => ({ classifyRound }));
vi.mock("@/lib/workspace", () => ({ listArtifacts: vi.fn().mockResolvedValue([]) }));
vi.mock("@/lib/round/roundArtifacts", () => ({
  normalizePath: (path: string) => path,
  roundEvolveproFiles: () => [{ n: 1, path: "/project/round-1.xlsx" }],
  roundFilesPathSignature: () => "",
  roundFilesSignature: () => "",
  roundOutputStamps: () => new Map(),
  unstampedFiles: () => [],
}));
vi.mock("@/store/round/roundSlice", () => ({
  useRoundStore: (selector: (state: { rounds: unknown[]; active_round_id: string | null }) => unknown) =>
    selector(roundState),
}));

import { getColumnRequirement } from "@/data/formatColumnRequirements";
import {
  openPreview,
  previewTriggerIds,
  renderedColumns,
} from "@/components/ui/formatPreviewTestUtils";
import { AdvisoryDecisionCard } from "./AdvisoryDecisionCard";

describe("AdvisoryDecisionCard", () => {
  it("forwards the disclosed next-round capacity instead of omitting it for the handler default", async () => {
    classifyRound.mockResolvedValue({ advisory: "decision", label: "continue_walking", reason: "calibration_period", confidence: null, missing_inputs: [] });
    render(<AdvisoryDecisionCard />);

    await waitFor(() => expect(screen.getByRole("button", { name: "advisoryDecision.classifyAriaLabel" })).not.toBeDisabled());
    fireEvent.change(screen.getByLabelText("advisoryDecision.nextRoundCapacity"), { target: { value: "384" } });
    fireEvent.click(screen.getByRole("button", { name: "advisoryDecision.classifyAriaLabel" }));

    await waitFor(() => expect(classifyRound).toHaveBeenCalledWith(
      [{ n: 1, path: "/project/round-1.xlsx" }],
      384,
    ));
  });
});

/**
 * The handler rejects a workbook missing either column by name, and until now
 * the only place that said so was the button's accessible name, which a
 * sighted reader never sees. No sample of this workbook ships, so the help
 * lists the two columns and shows no values.
 */
describe("AdvisoryDecisionCard round workbook shape", () => {
  it("lists the columns the handler requires, taken from the data file", () => {
    render(<AdvisoryDecisionCard />);

    openPreview("format-preview-round-xlsx");
    expect(renderedColumns("advisoryRoundXlsx")).toEqual(
      getColumnRequirement("advisoryRoundXlsx").columns,
    );
  });

  it("puts one '?' on the card and none on the capacity field", () => {
    render(<AdvisoryDecisionCard />);

    // Negative control: the next-round capacity is a number typed in place,
    // with no file behind it.
    expect(previewTriggerIds()).toEqual(["format-preview-round-xlsx-trigger"]);
  });
});
