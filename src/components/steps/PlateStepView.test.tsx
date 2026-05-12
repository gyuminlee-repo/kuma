/**
 * PlateStepView.test.tsx — PlateMap 마운트 어설션 (D2.2)
 */

import { render } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";

vi.mock("@/lib/ipc-kuro", () => ({
  sendRequest: vi.fn(),
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
}));

vi.mock("@/components/widgets/PlateMap", () => ({
  PlateMap: () => <div data-testid="plate-map" />,
}));

import { PlateStepView } from "./PlateStepView";

describe("PlateStepView", () => {
  it("mounts PlateMap", () => {
    const { getByTestId } = render(<PlateStepView />);
    expect(getByTestId("plate-map")).toBeTruthy();
  });
});
