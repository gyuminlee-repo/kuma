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
vi.mock("./WorkspaceSaveLoad", () => ({
  WorkspaceSaveLoad: () => <div data-testid="workspace-save-load" />,
}));

import { ExportStepView } from "./ExportStepView";

describe("ExportStepView", () => {
  it("export.all renders all export sections", () => {
    const { getByTestId } = render(<ExportStepView subStep="export.all" />);
    expect(getByTestId("export-format-selector")).toBeTruthy();
    expect(getByTestId("order-summary")).toBeTruthy();
    expect(getByTestId("workspace-save-load")).toBeTruthy();
  });
});
