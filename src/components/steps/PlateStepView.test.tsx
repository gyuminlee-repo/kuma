/**
 * PlateStepView.test.tsx — sub-step 마운트 어설션
 */

import { render } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";

vi.mock("@/lib/ipc-kuro", () => ({
  sendRequest: vi.fn(),
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
}));

vi.mock("@/components/widgets/KuroPlateView", () => ({
  KuroPlateView: () => <div data-testid="kuro-plate-view" />,
}));
vi.mock("./PlateSizeSelector", () => ({
  PlateSizeSelector: () => <div data-testid="plate-size-selector" />,
}));
vi.mock("./WellLabelOptions", () => ({
  WellLabelOptions: () => <div data-testid="well-label-options" />,
}));

import { PlateStepView } from "./PlateStepView";

describe("PlateStepView", () => {
  it("plate.size mounts PlateSizeSelector", () => {
    const { getByTestId } = render(<PlateStepView subStep="plate.size" />);
    expect(getByTestId("plate-size-selector")).toBeTruthy();
  });

  it("plate.layout mounts KuroPlateView", () => {
    const { getByTestId } = render(<PlateStepView subStep="plate.layout" />);
    expect(getByTestId("kuro-plate-view")).toBeTruthy();
  });

  it("plate.labels mounts WellLabelOptions", () => {
    const { getByTestId } = render(<PlateStepView subStep="plate.labels" />);
    expect(getByTestId("well-label-options")).toBeTruthy();
  });

  it("unknown sub-step returns null", () => {
    const { container } = render(<PlateStepView subStep="unknown.step" />);
    expect(container.firstChild).toBeNull();
  });
});
