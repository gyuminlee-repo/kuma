/**
 * MajorStepView.test.tsx — 각 major 선택 시 올바른 *StepView 마운트
 */

import { render } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("@/lib/ipc-kuro", () => ({
  sendRequest: vi.fn(),
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
}));

// Mock child step views to isolate MajorStepView dispatcher
vi.mock("./VariantStepView", () => ({
  VariantStepView: () => <div data-testid="variant-step-view" />,
}));
vi.mock("./SdmStepView", () => ({
  SdmStepView: () => <div data-testid="sdm-step-view" />,
}));
vi.mock("./PlateStepView", () => ({
  PlateStepView: () => <div data-testid="plate-step-view" />,
}));
vi.mock("./ExportStepView", () => ({
  ExportStepView: () => <div data-testid="export-step-view" />,
}));

import { MajorStepView } from "./MajorStepView";
import { useAppStore } from "@/store/appStore";

describe("MajorStepView dispatcher", () => {
  beforeEach(() => {
    useAppStore.setState({
      currentMajor: "variant",
      currentSubStep: "variant.load",
    });
  });

  it("mounts VariantStepView when currentMajor=variant", () => {
    const { getByTestId } = render(<MajorStepView />);
    expect(getByTestId("variant-step-view")).toBeTruthy();
  });

  it("mounts SdmStepView when currentMajor=sdm", () => {
    useAppStore.setState({ currentMajor: "sdm", currentSubStep: "sdm.mutations" });
    const { getByTestId } = render(<MajorStepView />);
    expect(getByTestId("sdm-step-view")).toBeTruthy();
  });

  it("mounts PlateStepView when currentMajor=plate", () => {
    useAppStore.setState({ currentMajor: "plate", currentSubStep: "plate.size" });
    const { getByTestId } = render(<MajorStepView />);
    expect(getByTestId("plate-step-view")).toBeTruthy();
  });

  it("mounts ExportStepView when currentMajor=export", () => {
    useAppStore.setState({ currentMajor: "export", currentSubStep: "export.format" });
    const { getByTestId } = render(<MajorStepView />);
    expect(getByTestId("export-step-view")).toBeTruthy();
  });

  it("does not mount multiple step views simultaneously", () => {
    useAppStore.setState({ currentMajor: "sdm", currentSubStep: "sdm.run" });
    const { queryByTestId } = render(<MajorStepView />);
    expect(queryByTestId("variant-step-view")).toBeNull();
    expect(queryByTestId("sdm-step-view")).toBeTruthy();
    expect(queryByTestId("plate-step-view")).toBeNull();
    expect(queryByTestId("export-step-view")).toBeNull();
  });
});
