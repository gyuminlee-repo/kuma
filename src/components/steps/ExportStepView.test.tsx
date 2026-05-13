/**
 * ExportStepView.test.tsx — WizardContainer wrap 어설션 (Back/Next UX 일관성)
 *
 * [source: spec Phase E — E2 WizardContainer]
 * [source: spec Phase G — #4 maxWidth export.all → "4xl"]
 */

import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import userEvent from "@testing-library/user-event";

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
import { useAppStore } from "@/store/appStore";

describe("ExportStepView", () => {
  beforeEach(() => {
    useAppStore.setState({ currentSubStep: "export.all" as never });
  });

  it("WizardContainer가 마운트된다 (data-testid=wizard-container)", () => {
    render(<ExportStepView />);
    expect(screen.getByTestId("wizard-container")).toBeTruthy();
  });

  it("export 섹션 컴포넌트가 렌더된다", () => {
    render(<ExportStepView />);
    expect(screen.getByTestId("export-format-selector")).toBeTruthy();
    expect(screen.getByTestId("order-summary")).toBeTruthy();
  });

  it("Back 버튼 클릭 시 goToPrevStep이 호출된다", async () => {
    const goToPrevStep = vi.fn();
    useAppStore.setState({ goToPrevStep } as never);

    const user = userEvent.setup();
    render(<ExportStepView />);

    const backBtn = screen.getByRole("button", { name: /back/i });
    await user.click(backBtn);

    expect(goToPrevStep).toHaveBeenCalledOnce();
  });

  it("Next 버튼이 렌더되지 않는다 (마지막 major step)", () => {
    render(<ExportStepView />);
    const nextBtn = screen.queryByRole("button", { name: /next/i });
    expect(nextBtn).toBeNull();
  });
});
