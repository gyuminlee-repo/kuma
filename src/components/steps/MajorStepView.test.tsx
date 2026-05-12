/**
 * MajorStepView.test.tsx — 각 major 선택 시 올바른 *StepView 마운트 (D1.1: 3-major)
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
vi.mock("./PlateStepView", () => ({
  PlateStepView: () => <div data-testid="plate-step-view" />,
}));
vi.mock("./ExportStepView", () => ({
  ExportStepView: () => <div data-testid="export-step-view" />,
}));

import { MajorStepView } from "./MajorStepView";
import { useAppStore } from "@/store/appStore";

describe("MajorStepView dispatcher (3-major)", () => {
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

  it("mounts PlateStepView when currentMajor=plate", () => {
    useAppStore.setState({ currentMajor: "plate", currentSubStep: "plate.layout" });
    const { getByTestId } = render(<MajorStepView />);
    expect(getByTestId("plate-step-view")).toBeTruthy();
  });

  it("mounts ExportStepView when currentMajor=export", () => {
    useAppStore.setState({ currentMajor: "export", currentSubStep: "export.all" });
    const { getByTestId } = render(<MajorStepView />);
    expect(getByTestId("export-step-view")).toBeTruthy();
  });

  it("does not mount multiple step views simultaneously", () => {
    useAppStore.setState({ currentMajor: "plate", currentSubStep: "plate.layout" });
    const { queryByTestId } = render(<MajorStepView />);
    expect(queryByTestId("design-step-view")).toBeNull();
    expect(queryByTestId("plate-step-view")).toBeTruthy();
    expect(queryByTestId("export-step-view")).toBeNull();
  });
});
