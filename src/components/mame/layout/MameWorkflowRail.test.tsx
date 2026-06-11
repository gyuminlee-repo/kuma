import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { MameWorkflowRail } from "./MameWorkflowRail";
import { useMameAppStore } from "@/store/mame/mameAppStore";

describe("MameWorkflowRail", () => {
  beforeEach(() => {
    useMameAppStore.setState({
      mamePhase: "setup",
      currentMameSubStep: "setup.files",
    });
  });

  it("clicking a cross-phase step updates both phase and sub-step", async () => {
    render(<MameWorkflowRail />);

    const steps = screen.getAllByRole("button");
    await userEvent.setup().click(steps[1]); // analyze.inputs (setup is a single sub-step)

    expect(useMameAppStore.getState().mamePhase).toBe("analyze");
    expect(useMameAppStore.getState().currentMameSubStep).toBe("analyze.inputs");
  });
});
