/**
 * ActivityStepView.test.tsx — activity sub-step 마운트 어설션 (D2.4, Phase G #19)
 *
 * Phase G #19: activity.export → activity.mergeExport (2-step). Later merged again:
 * activity.ingest is now the single Activity step; activity.mergeExport is a legacy redirect.
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("@/lib/ipc", () => ({
  rpc: vi.fn(),
}));
vi.mock("@/lib/ipc-mame", () => ({
  sendRequest: vi.fn(),
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
}));
vi.mock("@tauri-apps/plugin-dialog", () => ({
  save: vi.fn(),
}));

// Mock round store to avoid side effects
vi.mock("@/store/round/roundSlice", () => ({
  useRoundStore: vi.fn((sel) => sel({ active_round_id: "r1", rounds: [], addRound: vi.fn() })),
}));

vi.mock("@/components/mame/panels/ActivityPanel", () => ({
  IngestSection: () => <div data-testid="ingest-section" />,
  MergeSection: () => <div data-testid="merge-section" />,
  ExportSection: () => <div data-testid="export-section" />,
}));
vi.mock("@/components/mame/panels/BuildEvolveproInputPanel", () => ({
  BuildEvolveproInputPanel: () => <div data-testid="build-evolvepro-panel" />,
}));

import { ActivityStepView } from "./ActivityStepView";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import { ACTIVITY_ROUTE_STORAGE_KEY } from "@/lib/mame/activityRouteStorage";
import {
  BUILD_EVOLVEPRO_STORAGE_KEY,
  BUILD_EVOLVEPRO_DEFAULT_STATE,
  createBuildEvolveproCompletion,
  type BuildEvolveproFormState,
} from "@/lib/mame/buildEvolveproFormStorage";

describe("ActivityStepView", () => {
  beforeEach(() => {
    localStorage.clear();
    useMameAppStore.setState({
      currentMameSubStep: "activity.ingest",
      buildEvolveproCompletion: null,
    });
  });

  it("activity.ingest mounts the merged Ingest + Merge + Export sections", () => {
    const { getByTestId } = render(<ActivityStepView />);
    expect(getByTestId("ingest-section")).toBeTruthy();
    expect(getByTestId("merge-section")).toBeTruthy();
    expect(getByTestId("export-section")).toBeTruthy();
  });

  it("legacy activity.mergeExport redirects to the merged activity step", () => {
    useMameAppStore.setState({ currentMameSubStep: "activity.mergeExport" });
    const { queryByTestId, getByRole } = render(<ActivityStepView />);
    expect(getByRole("status")).toBeTruthy();
    expect(queryByTestId("merge-section")).toBeNull();
  });

  it("blocks Activity next until the selected route has produced EVOLVEpro inputs", async () => {
    localStorage.setItem(ACTIVITY_ROUTE_STORAGE_KEY, JSON.stringify("plateLayout"));
    localStorage.setItem(
      BUILD_EVOLVEPRO_STORAGE_KEY,
      JSON.stringify({
        ...BUILD_EVOLVEPRO_DEFAULT_STATE,
        layoutXlsx: "/in/layout.xlsx",
        gcDataXlsx: "/in/gc.xlsx",
        outputXlsx: "/out/ep.xlsx",
      }),
    );

    render(<ActivityStepView />);

    fireEvent.click(screen.getByRole("button", { name: "Next" }));

    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("Complete the selected Activity route")).toBeInTheDocument();
    expect(useMameAppStore.getState().currentMameSubStep).toBe("activity.ingest");
  });

  it("allows Activity next after the selected plate-layout route has a completed build", () => {
    localStorage.setItem(ACTIVITY_ROUTE_STORAGE_KEY, JSON.stringify("plateLayout"));
    const completedForm: BuildEvolveproFormState = {
      ...BUILD_EVOLVEPRO_DEFAULT_STATE,
      layoutXlsx: "/in/layout.xlsx",
      gcDataXlsx: "/in/gc.xlsx",
      outputXlsx: "/out/ep.xlsx",
    };
    localStorage.setItem(
      BUILD_EVOLVEPRO_STORAGE_KEY,
      JSON.stringify(completedForm),
    );
    useMameAppStore.setState({
      buildEvolveproCompletion: createBuildEvolveproCompletion(
        completedForm,
        "/out/ep.xlsx",
      ),
    });

    render(<ActivityStepView />);

    fireEvent.click(screen.getByRole("button", { name: "Next" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(useMameAppStore.getState().currentMameSubStep).toBe("activity.signals");
  });

  it("blocks Activity next when the completed build belongs to stale restored inputs", async () => {
    localStorage.setItem(ACTIVITY_ROUTE_STORAGE_KEY, JSON.stringify("plateLayout"));
    const completedForm: BuildEvolveproFormState = {
      ...BUILD_EVOLVEPRO_DEFAULT_STATE,
      layoutXlsx: "/in/layout.xlsx",
      gcDataXlsx: "/in/gc.xlsx",
      outputXlsx: "/out/ep.xlsx",
    };
    useMameAppStore.setState({
      buildEvolveproCompletion: createBuildEvolveproCompletion(
        completedForm,
        "/out/ep.xlsx",
      ),
    });
    localStorage.setItem(
      BUILD_EVOLVEPRO_STORAGE_KEY,
      JSON.stringify({
        ...completedForm,
        gcDataXlsx: "/other/gc.xlsx",
      }),
    );

    render(<ActivityStepView />);

    fireEvent.click(screen.getByRole("button", { name: "Next" }));

    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(useMameAppStore.getState().currentMameSubStep).toBe("activity.ingest");
  });
});
