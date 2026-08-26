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
