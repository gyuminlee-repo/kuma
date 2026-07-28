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
      inputDir: "",
      expectedPath: "",
      referencePath: "",
      outputPath: "",
      verdicts: [],
      summary: null,
    });
  });

  it("clicking a cross-phase step updates both phase and sub-step", async () => {
    render(<MameWorkflowRail />);

    const steps = screen.getAllByRole("button");
    await userEvent.setup().click(steps[1]); // analyze.inputs (setup is a single sub-step)

    expect(useMameAppStore.getState().mamePhase).toBe("analyze");
    expect(useMameAppStore.getState().currentMameSubStep).toBe("analyze.inputs");
  });

  it("marks setup done from completion state instead of active index alone", () => {
    useMameAppStore.setState({
      currentMameSubStep: "analyze.inputs",
      inputDir: "/runs/minion",
      expectedPath: "/runs/expected.xlsx",
      referencePath: "/runs/reference.fasta",
      outputPath: "/runs/out",
    });

    render(<MameWorkflowRail />);

    expect(
      screen.getByRole("button", { name: "Barcode Package done" }),
    ).toBeInTheDocument();
  });

  it("does not mark setup done just because the user navigated forward", () => {
    useMameAppStore.setState({
      currentMameSubStep: "analyze.inputs",
    });

    render(<MameWorkflowRail />);

    expect(
      screen.queryByRole("button", { name: "Barcode Package done" }),
    ).not.toBeInTheDocument();
  });
});
