import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { MameWorkflowRail } from "./MameWorkflowRail";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import { useRoundStore } from "@/store/round/roundSlice";

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
      buildEvolveproCompletion: null,
      janusSettings: { ...useMameAppStore.getState().janusSettings, liquidClass: "" },
      janusMappingAutosave: null,
    });
    useRoundStore.setState({ rounds: [], active_round_id: null });
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

  it("numbers Janus as 3.1 and pushes Activity to 4.1 / 4.2", () => {
    render(<MameWorkflowRail />);

    expect(screen.getByText("3.1")).toBeInTheDocument();
    expect(screen.getByText("4.1")).toBeInTheDocument();
    expect(screen.getByText("4.2")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Janus Instrument Settings/i }),
    ).toBeInTheDocument();
  });

  it("clicking the Janus step switches to the janus phase", async () => {
    render(<MameWorkflowRail />);

    await userEvent
      .setup()
      .click(screen.getByRole("button", { name: /Janus Instrument Settings/i }));

    expect(useMameAppStore.getState().mamePhase).toBe("janus");
    expect(useMameAppStore.getState().currentMameSubStep).toBe("janus.settings");
  });

  it("leaves the Janus step not-done for a sequencing-only run", () => {
    useMameAppStore.setState({
      currentMameSubStep: "analyze.review",
      verdicts: [],
      summary: null,
    });

    render(<MameWorkflowRail />);

    expect(
      screen.queryByRole("button", { name: /Janus Instrument Settings done/i }),
    ).not.toBeInTheDocument();
  });

  it("marks the Janus step done once the liquid class is supplied", () => {
    useMameAppStore.setState({
      janusSettings: {
        ...useMameAppStore.getState().janusSettings,
        liquidClass: "Tip_50_Water",
      },
    });

    render(<MameWorkflowRail />);

    expect(
      screen.getByRole("button", { name: /Janus Instrument Settings done/i }),
    ).toBeInTheDocument();
  });

  it("marks the Janus step done when a run already wrote the mapping, with no liquid class", () => {
    // The second half of the done rule: a written `..._janus.csv` is proof the
    // instrument sheet exists even though the liquid class was never typed.
    useMameAppStore.setState({
      janusMappingAutosave: {
        status: "saved",
        output_path: "/project/260804_MAME_96_janus.csv",
        format: "csv",
        row_count: 42,
        excluded: [],
        excluded_count: 0,
        warnings: [],
        errors: [],
      },
    });

    render(<MameWorkflowRail />);

    expect(
      screen.getByRole("button", { name: /Janus Instrument Settings done/i }),
    ).toBeInTheDocument();
  });

  it("marks Activity Data done when the active round has activity evidence", () => {
    useMameAppStore.setState({
      currentMameSubStep: "activity.signals",
    });
    const roundId = useRoundStore.getState().addRound({ plate_meta: { plates: [] } });
    useRoundStore.getState().updateRoundField(roundId, "activity", {
      records: [],
      plate_meta: { plates: [] },
    });

    render(<MameWorkflowRail />);

    expect(
      screen.getByRole("button", { name: "Activity Data done" }),
    ).toBeInTheDocument();
  });
});
