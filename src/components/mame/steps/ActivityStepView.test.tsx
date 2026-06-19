/**
 * ActivityStepView.test.tsx, activity 단일 Step 3 마운트 어설션 (D2.4, Phase G #19, PR2b)
 *
 * PR2b: activity.ingest/mergeExport를 단일 Step 3로 통합, 한 화면에 ingest →
 * merge → export → build를 모두 쌓는다. activity.mergeExport는 legacy redirect id로
 * 같은 화면을 렌더한다.
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

vi.mock("@/components/mame/panels/BuildEvolveproInputPanel", () => ({
  BuildEvolveproInputPanel: () => <div data-testid="build-evolvepro-panel" />,
}));

import { ActivityStepView } from "./ActivityStepView";
import { useMameAppStore } from "@/store/mame/mameAppStore";

describe("ActivityStepView", () => {
  beforeEach(() => {
    useMameAppStore.setState({ currentMameSubStep: "activity.ingest" });
  });

  it("activity.ingest mounts all activity sections on a single Step 3", () => {
    const { getByTestId } = render(<ActivityStepView />);
    expect(getByTestId("ingest-section")).toBeTruthy();
    expect(getByTestId("merge-section")).toBeTruthy();
    expect(getByTestId("export-section")).toBeTruthy();
    expect(getByTestId("build-evolvepro-panel")).toBeTruthy();
  });

  it("activity.mergeExport (legacy id) renders the same single Step 3", () => {
    useMameAppStore.setState({ currentMameSubStep: "activity.mergeExport" });
    const { getByTestId } = render(<ActivityStepView />);
    expect(getByTestId("ingest-section")).toBeTruthy();
    expect(getByTestId("merge-section")).toBeTruthy();
    expect(getByTestId("export-section")).toBeTruthy();
    expect(getByTestId("build-evolvepro-panel")).toBeTruthy();
  });
});
