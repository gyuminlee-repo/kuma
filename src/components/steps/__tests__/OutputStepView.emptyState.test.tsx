/**
 * OutputStepView.emptyState.test.tsx, an empty output step has to say which
 * kind of empty it is.
 *
 * The user report was "step 5 shows nothing and I cannot tell whether primers
 * were made". Both states rendered the same "No results yet" card, so a run
 * whose results were discarded looked exactly like a workspace nobody had run.
 *
 * Mock setup mirrors OutputStepView.stats.test.tsx.
 */

import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/ipc-kuro", () => ({
  sendRequest: vi.fn(),
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
}));

vi.mock("@/components/widgets/PlateMap", () => ({
  PlateMap: () => <div data-testid="plate-map-mock">plate</div>,
}));
vi.mock("@/components/widgets/ResultTable", () => ({
  ResultTable: () => <div data-testid="result-table-mock">table</div>,
}));

import { OutputStepView } from "../OutputStepView";
import { useAppStore } from "@/store/appStore";

beforeEach(() => {
  window.localStorage.clear();
  useAppStore.setState({
    designResults: [],
    plateMappings: [],
    failedMutations: [],
    rescueStats: null,
    lastDesignRun: null,
  } as never);
});

afterEach(() => {
  window.localStorage.clear();
  useAppStore.setState({ lastDesignRun: null } as never);
});

describe("OutputStepView empty state", () => {
  it("shows the never-run card when no design has run", () => {
    render(<OutputStepView />);

    expect(screen.getByTestId("output-empty-never-run")).toBeInTheDocument();
    expect(screen.queryByTestId("output-empty-after-run")).toBeNull();
    expect(screen.getByText("No results yet")).toBeInTheDocument();
  });

  it("reports the last run when a design produced primers that are now gone", () => {
    useAppStore.setState({
      lastDesignRun: {
        outcome: "success",
        finishedAt: Date.parse("2026-09-08T08:49:00Z"),
        successCount: 95,
        totalCount: 95,
        failedCount: 0,
        detail: null,
      },
    } as never);

    render(<OutputStepView />);

    expect(screen.getByTestId("output-empty-after-run")).toBeInTheDocument();
    expect(screen.queryByTestId("output-empty-never-run")).toBeNull();
    // The counts the run actually produced, so "did it design anything?" has an
    // answer on this screen.
    expect(screen.getByText(/95 of 95 primers/)).toBeInTheDocument();
  });

  it("names a sidecar restart rather than staying silent", () => {
    useAppStore.setState({
      lastDesignRun: {
        outcome: "interrupted",
        finishedAt: Date.now(),
        successCount: 0,
        totalCount: 95,
        failedCount: 0,
        detail: "Sidecar killed",
      },
    } as never);

    render(<OutputStepView />);

    expect(screen.getByTestId("output-empty-after-run")).toBeInTheDocument();
    expect(screen.getByText(/sidecar restarted/)).toBeInTheDocument();
  });
});
