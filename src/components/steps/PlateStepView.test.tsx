/**
 * PlateStepView.test.tsx — WizardContainer + Export All footer 어설션 (Phase F, F2)
 */

import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";

vi.mock("@/lib/ipc-kuro", () => ({
  sendRequest: vi.fn(),
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
}));

vi.mock("@/components/widgets/PlateMap", () => ({
  PlateMap: () => <div data-testid="plate-map" />,
}));

vi.mock("@/components/dialogs/MappingExportDialog", () => ({
  MappingExportDialog: ({ open }: { open: boolean }) => (
    <div data-testid="mapping-export-dialog" data-open={String(open)} />
  ),
}));

vi.mock("@/components/layout/export-handlers", () => ({
  handleExportAll: vi.fn(),
  handleExportMappingWithParams: vi.fn(),
}));

vi.mock("@/state/projectContext", () => ({
  useKumaProject: () => ({ path: "/some/path", scratch: false }),
}));

let mockPlateMappings: unknown[] = [{ id: "mock" }];

vi.mock("@/store/appStore", () => ({
  useAppStore: (sel: (s: Record<string, unknown>) => unknown) =>
    sel({ goToPrevStep: vi.fn(), goToNextStep: vi.fn(), plateMappings: mockPlateMappings }),
}));

import { PlateStepView } from "./PlateStepView";

describe("PlateStepView", () => {
  it("mounts PlateMap inside WizardContainer", () => {
    render(<PlateStepView />);
    expect(screen.getByTestId("plate-map")).toBeTruthy();
    expect(screen.getByTestId("wizard-container")).toBeTruthy();
  });

  it("Export All Next button opens MappingExportDialog when project is valid", () => {
    mockPlateMappings = [{ id: "mock" }];
    render(<PlateStepView />);
    const dialog = screen.getByTestId("mapping-export-dialog");
    expect(dialog.getAttribute("data-open")).toBe("false");

    // WizardContainer의 Next 버튼 클릭
    const nextBtn = screen.getByRole("button", { name: /export all/i });
    fireEvent.click(nextBtn);

    expect(screen.getByTestId("mapping-export-dialog").getAttribute("data-open")).toBe("true");
  });

  it("Next button is hidden when plateMappings is empty (empty state guard)", () => {
    mockPlateMappings = [];
    render(<PlateStepView />);
    // onNext=undefined → WizardContainer hides Next button
    expect(screen.queryByRole("button", { name: /export all/i })).toBeNull();
  });
});
