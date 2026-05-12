/**
 * ExportStepView.test.tsx — sub-step 마운트 어설션
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
  it("export.format mounts ExportFormatSelector", () => {
    const { getByTestId } = render(<ExportStepView subStep="export.format" />);
    expect(getByTestId("export-format-selector")).toBeTruthy();
  });

  it("export.summary mounts OrderSummary", () => {
    const { getByTestId } = render(<ExportStepView subStep="export.summary" />);
    expect(getByTestId("order-summary")).toBeTruthy();
  });

  it("export.workspace mounts WorkspaceSaveLoad", () => {
    const { getByTestId } = render(<ExportStepView subStep="export.workspace" />);
    expect(getByTestId("workspace-save-load")).toBeTruthy();
  });

  it("unknown sub-step returns null", () => {
    const { container } = render(<ExportStepView subStep="unknown.step" />);
    expect(container.firstChild).toBeNull();
  });
});
