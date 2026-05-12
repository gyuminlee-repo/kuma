/**
 * ActivityStepView.test.tsx — 3 sub-step 마운트 어설션 (D2.4)
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
  ActivityPanel: () => <div data-testid="activity-panel" />,
}));

import { ActivityStepView } from "./ActivityStepView";
import { useMameAppStore } from "@/store/mame/mameAppStore";

describe("ActivityStepView", () => {
  beforeEach(() => {
    useMameAppStore.setState({ currentMameSubStep: "activity.ingest" });
  });

  it("activity.ingest mounts IngestSection", () => {
    const { getByTestId } = render(<ActivityStepView />);
    expect(getByTestId("ingest-section")).toBeTruthy();
  });

  it("activity.merge mounts MergeSection", () => {
    useMameAppStore.setState({ currentMameSubStep: "activity.merge" });
    const { getByTestId } = render(<ActivityStepView />);
    expect(getByTestId("merge-section")).toBeTruthy();
  });

  it("activity.export mounts ExportSection", () => {
    useMameAppStore.setState({ currentMameSubStep: "activity.export" });
    const { getByTestId } = render(<ActivityStepView />);
    expect(getByTestId("export-section")).toBeTruthy();
  });
});
