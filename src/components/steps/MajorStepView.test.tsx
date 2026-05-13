/**
 * MajorStepView.test.tsx — Phase G: 3-major (Design / Output / Export) 마운트 어설션
 * [source: spec Phase G — 3-tab (Design / Output / Export)]
 */

import { render } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("@/lib/ipc-kuro", () => ({
  sendRequest: vi.fn(),
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
}));

// Mock child step views to isolate MajorStepView dispatcher
vi.mock("./DesignStepView", () => ({
  DesignStepView: () => <div data-testid="design-step-view" />,
}));
vi.mock("./OutputStepView", () => ({
  OutputStepView: () => <div data-testid="output-step-view" />,
}));
vi.mock("./ExportStepView", () => ({
  ExportStepView: () => <div data-testid="export-step-view" />,
}));

import { MajorStepView } from "./MajorStepView";
import { useAppStore } from "@/store/appStore";

describe("MajorStepView dispatcher (3-major, Phase G)", () => {
  beforeEach(() => {
    useAppStore.setState({
      currentMajor: "design",
      currentSubStep: "design.load",
    });
  });

  it("mounts DesignStepView when currentMajor=design", () => {
    const { getByTestId } = render(<MajorStepView />);
    expect(getByTestId("design-step-view")).toBeTruthy();
  });

  it("mounts OutputStepView when currentMajor=output", () => {
    useAppStore.setState({ currentMajor: "output", currentSubStep: "output.summary" });
    const { getByTestId } = render(<MajorStepView />);
    expect(getByTestId("output-step-view")).toBeTruthy();
  });

  it("mounts ExportStepView when currentMajor=export", () => {
    useAppStore.setState({ currentMajor: "export", currentSubStep: "export.all" });
    const { getByTestId } = render(<MajorStepView />);
    expect(getByTestId("export-step-view")).toBeTruthy();
  });

  it("does not mount multiple step views simultaneously", () => {
    useAppStore.setState({ currentMajor: "output", currentSubStep: "output.summary" });
    const { queryByTestId } = render(<MajorStepView />);
    expect(queryByTestId("design-step-view")).toBeNull();
    expect(queryByTestId("output-step-view")).toBeTruthy();
    expect(queryByTestId("export-step-view")).toBeNull();
  });

  it("does not mount ReportStepView or PlateStepView (deleted in Phase G)", () => {
    const { queryByTestId } = render(<MajorStepView />);
    expect(queryByTestId("report-step-view")).toBeNull();
    expect(queryByTestId("plate-step-view")).toBeNull();
  });
});
