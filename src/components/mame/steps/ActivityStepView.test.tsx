import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ProjectProvider } from "@/state/projectContext";

vi.mock("@/lib/ipc", () => ({ rpc: vi.fn() }));
vi.mock("@/lib/ipc-mame", () => ({
  sendRequest: vi.fn(),
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
}));
vi.mock("@/store/round/roundSlice", () => ({
  useRoundStore: vi.fn((selector) => selector({ active_round_id: "r1", rounds: [], addRound: vi.fn() })),
}));
vi.mock("@/components/mame/panels/BuildEvolveproInputPanel", () => ({
  BuildEvolveproInputPanel: () => <div data-testid="unified-builder" />,
}));

import { ActivityStepView } from "./ActivityStepView";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import {
  BUILD_EVOLVEPRO_DEFAULT_STATE,
  createBuildEvolveproCompletion,
  saveBuildEvolveproToStorage,
  type BuildEvolveproFormState,
} from "@/lib/mame/buildEvolveproFormStorage";

const PROJECT = "/project";
const completedForm: BuildEvolveproFormState = {
  ...BUILD_EVOLVEPRO_DEFAULT_STATE,
  activityPath: "/project/activity/activity.csv",
  activityScale: "raw",
  verdictXlsx: "/project/ngs/verdict.xlsx",
  outputXlsx: "/project/activity/evolvepro_input.xlsx",
};

function renderStep() {
  return render(
    <ProjectProvider value={{ path: PROJECT, name: "Demo", scratch: false }}>
      <ActivityStepView />
    </ProjectProvider>,
  );
}

describe("ActivityStepView unified Step 3", () => {
  beforeEach(() => {
    localStorage.clear();
    useMameAppStore.setState({
      currentMameSubStep: "activity.ingest",
      buildEvolveproCompletion: null,
    });
  });

  it("renders one unified builder without a route selector or legacy activity sections", () => {
    renderStep();

    expect(screen.getAllByTestId("unified-builder")).toHaveLength(1);
    expect(screen.queryByRole("radiogroup", { name: /activity route/i })).not.toBeInTheDocument();
    expect(screen.queryByTestId("ingest-section")).not.toBeInTheDocument();
    expect(screen.queryByTestId("merge-section")).not.toBeInTheDocument();
    expect(screen.queryByTestId("export-section")).not.toBeInTheDocument();
  });

  it("blocks Next until the unified form has a successful matching completion", async () => {
    saveBuildEvolveproToStorage(completedForm, PROJECT);
    renderStep();

    fireEvent.click(screen.getByRole("button", { name: "Next" }));

    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(useMameAppStore.getState().currentMameSubStep).toBe("activity.ingest");
  });

  it("allows Next only when completion matches the persisted inputs and evidence", () => {
    saveBuildEvolveproToStorage(completedForm, PROJECT);
    useMameAppStore.setState({
      buildEvolveproCompletion: createBuildEvolveproCompletion(
        completedForm,
        completedForm.outputXlsx,
      ),
    });
    renderStep();

    fireEvent.click(screen.getByRole("button", { name: "Next" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(useMameAppStore.getState().currentMameSubStep).toBe("activity.signals");
  });

  it("rejects a completion when its verdict evidence has changed", async () => {
    saveBuildEvolveproToStorage({ ...completedForm, verdictXlsx: "/project/ngs/new-verdict.xlsx" }, PROJECT);
    useMameAppStore.setState({
      buildEvolveproCompletion: createBuildEvolveproCompletion(
        completedForm,
        completedForm.outputXlsx,
      ),
    });
    renderStep();

    fireEvent.click(screen.getByRole("button", { name: "Next" }));

    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(useMameAppStore.getState().currentMameSubStep).toBe("activity.ingest");
  });
});
