/**
 * ActivityStepView.test.tsx — activity sub-step 마운트 어설션 (D2.4, Phase G #19)
 *
 * Phase G #19: activity.export → activity.mergeExport (2-step). Later merged again:
 * activity.ingest is now the single Activity step; activity.mergeExport is a legacy redirect.
 */

import { render } from "@testing-library/react";
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
  MergeExportSection: () => <div data-testid="merge-export-section" />,
  ActivityPanel: () => <div data-testid="activity-panel" />,
}));

import { ActivityStepView } from "./ActivityStepView";
import { useMameAppStore } from "@/store/mame/mameAppStore";

describe("ActivityStepView", () => {
  beforeEach(() => {
    useMameAppStore.setState({ currentMameSubStep: "activity.ingest" });
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
});
