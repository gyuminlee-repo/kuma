/**
 * ExportStepView.test.tsx — export.all 단일 sub-step 마운트 어설션 (D1.1)
 */

import { render } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";

vi.mock("@/lib/ipc-kuro", () => ({
  sendRequest: vi.fn(),
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
}));

vi.mock("./ExportFormatSelector", () => ({
  ExportFormatSelector: () => <div data-testid="export-format-selector" />,
}));
vi.mock("./OrderSummary", () => ({
  OrderSummary: () => <div data-testid="order-summary" />,
}));

import { ExportStepView } from "./ExportStepView";

describe("ExportStepView", () => {
  it("export.all renders export sections", () => {
    const { getByTestId } = render(<ExportStepView />);
    expect(getByTestId("export-format-selector")).toBeTruthy();
    expect(getByTestId("order-summary")).toBeTruthy();
  });
});
