/**
 * PlateStepView.test.tsx — plate.layout 단일 sub-step 마운트 어설션 (D1.1)
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

import { PlateStepView } from "./PlateStepView";

describe("PlateStepView", () => {
  it("plate.layout mounts KuroPlateView", () => {
    const { getByTestId } = render(<PlateStepView subStep="plate.layout" />);
    expect(getByTestId("kuro-plate-view")).toBeTruthy();
  });
});
