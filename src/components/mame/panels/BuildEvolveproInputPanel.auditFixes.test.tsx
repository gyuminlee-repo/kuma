import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { BuildEvolveproInputPanel } from "@/components/mame/panels/BuildEvolveproInputPanel";
import { ProjectProvider } from "@/state/projectContext";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import { useRoundStore } from "@/store/round/roundSlice";
import { resetMameAll } from "@/store/mame/resetAll";
import {
  BUILD_EVOLVEPRO_DEFAULT_STATE,
  loadBuildEvolveproFromStorage,
  saveBuildEvolveproToStorage,
} from "@/lib/mame/buildEvolveproFormStorage";

const mocks = vi.hoisted(() => ({ build: vi.fn(), detect: vi.fn(), open: vi.fn() }));
vi.mock("@/lib/ipc-mame", () => ({
  buildEvolveproInput: mocks.build,
  detectMeasurementSource: mocks.detect,
  sendRequest: vi.fn(),
  cancelAndRespawn: vi.fn(),
  isSidecarRunning: () => false,
}));
vi.mock("@tauri-apps/plugin-dialog", () => ({ open: mocks.open, save: vi.fn() }));
vi.mock("@tauri-apps/plugin-fs", () => ({ mkdir: vi.fn().mockResolvedValue(undefined) }));
vi.mock("@/lib/workspace", () => ({
  registerArtifacts: vi.fn().mockResolvedValue(undefined),
  clearWorkspace: vi.fn(),
  getActiveWorkspace: () => null,
}));
vi.mock("@/lib/openFolder", () => ({ revealInOSFolder: vi.fn() }));

function panel(path: string) {
  return <ProjectProvider value={{ path, name: "Audit", scratch: false }}><BuildEvolveproInputPanel /></ProjectProvider>;
}

function seed(path: string) {
  saveBuildEvolveproToStorage({
    ...BUILD_EVOLVEPRO_DEFAULT_STATE,
    activityPath: `${path}/old.csv`,
    verdictXlsx: `${path}/verdict.xlsx`,
    outputXlsx: `${path}/out.xlsx`,
  }, path);
}

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
  useMameAppStore.setState({ resetEpoch: 0, buildEvolveproSeedEpoch: 0 });
  useRoundStore.setState({ rounds: [], active_round_id: null });
  mocks.build.mockRejectedValue(new Error("Audit transport boundary: no output written"));
  mocks.detect.mockResolvedValue({
    path: "/project/new.xlsx", candidates: ["gcSheet", "longFormat"],
    ambiguous: true, evidence: {}, reason: "Two formats fit",
  });
});

describe("builder state audit", () => {
  it("allows a fully resolved stored source to reach the build boundary", async () => {
    seed("/project");
    render(panel("/project"));
    fireEvent.click(screen.getByRole("button", { name: "Convert to EVOLVEpro input format" }));
    await screen.findByRole("alert");
    expect(mocks.build).toHaveBeenCalledWith(expect.objectContaining({ activity_path: "/project/old.csv" }));
  });

  it("does not build the previous source while the displayed new file is ambiguous", async () => {
    seed("/project");
    mocks.open.mockResolvedValue("/project/new.xlsx");
    render(panel("/project"));
    fireEvent.click(screen.getByRole("button", { name: "Change: Experiment data file" }));
    fireEvent.click(screen.getByRole("button", { name: "Browse Experiment data file" }));
    await screen.findByText(/reads as two formats/i);
    expect(screen.getByLabelText("Experiment data file")).toHaveValue("new.xlsx");
    expect(screen.getByRole("button", { name: "Convert to EVOLVEpro input format" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Convert to EVOLVEpro input format" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Convert to EVOLVEpro input format" })).toBeInTheDocument());
    expect(mocks.build).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("radio", { name: "Generic long-format" }));
    expect(screen.getByRole("button", { name: "Convert to EVOLVEpro input format" })).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "Convert to EVOLVEpro input format" }));
    await screen.findByRole("alert");
    expect(mocks.build).toHaveBeenCalledWith(expect.objectContaining({ activity_path: "/project/new.xlsx" }));
  });

  it("persists a newly browsed verdict to the current project after a provider switch", async () => {
    seed("/project-a");
    seed("/project-b");
    const view = render(panel("/project-a"));
    view.rerender(panel("/project-b"));
    mocks.open.mockResolvedValue("/project-b/new-verdict.xlsx");
    fireEvent.click(screen.getByRole("button", { name: "Change: NGS verdict xlsx" }));
    fireEvent.click(screen.getByRole("button", { name: "Browse NGS verdict xlsx" }));
    await waitFor(() => expect(screen.getByLabelText("NGS verdict xlsx")).toHaveValue("new-verdict.xlsx"));
    expect({
      previous: loadBuildEvolveproFromStorage("/project-a").verdictXlsx,
      current: loadBuildEvolveproFromStorage("/project-b").verdictXlsx,
    }).toEqual({
      previous: "/project-a/verdict.xlsx",
      current: "/project-b/new-verdict.xlsx",
    });
  });
});

// Every reset used to erase the saved form, and the erasing ran again on each
// mount once any reset had happened, so reopening step 4 emptied it. Only Clear
// All erases it now; opening a project and mounting the panel reload it.
describe("saved Activity form across resets", () => {
  const shownSource = () => screen.queryByTitle("/project/old.csv");

  it("survives the panel mounting after an earlier reset", () => {
    seed("/project");
    useMameAppStore.setState({ resetEpoch: 3 });
    render(panel("/project"));
    expect(shownSource()).not.toBeNull();
    expect(loadBuildEvolveproFromStorage("/project").activityPath).toBe("/project/old.csv");
  });

  it("comes back after a project-opening reset and is emptied by Clear All", async () => {
    seed("/project");
    useMameAppStore.setState({ formStoragePath: "/project" });
    render(panel("/project"));

    await act(async () => { await resetMameAll({ preserveWorkspaceArtifacts: true }); });
    expect(shownSource()).not.toBeNull();
    expect(loadBuildEvolveproFromStorage("/project").activityPath).toBe("/project/old.csv");

    useMameAppStore.setState({ formStoragePath: "/project" });
    await act(async () => { await resetMameAll(); });
    expect(shownSource()).toBeNull();
    expect(loadBuildEvolveproFromStorage("/project").activityPath).toBe("");
  });
});
