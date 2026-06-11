/**
 * SetupStepView.test.tsx — single merged "Barcode Package" step (1.1).
 * setup.files and the legacy setup.design id both render the full panel.
 */

import { render } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("@/lib/ipc", () => ({
  rpc: vi.fn(),
}));
vi.mock("@/lib/ipc-mame", () => ({
  sendRequest: vi.fn(),
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
}));

vi.mock("@/components/mame/panels/BarcodeSetupPanel", () => ({
  BarcodeSetupPanel: ({ group }: { group?: string }) => (
    <div data-testid={`barcode-setup-panel-${group ?? "all"}`} />
  ),
}));

import { SetupStepView } from "./SetupStepView";
import { useMameAppStore } from "@/store/mame/mameAppStore";

describe("SetupStepView", () => {
  beforeEach(() => {
    useMameAppStore.setState({ currentMameSubStep: "setup.files" });
  });

  it("setup.files mounts the merged BarcodeSetupPanel (no group filter)", () => {
    const { getByTestId } = render(<SetupStepView />);
    expect(getByTestId("barcode-setup-panel-all")).toBeTruthy();
  });

  it("legacy setup.design id also renders the merged panel", () => {
    useMameAppStore.setState({ currentMameSubStep: "setup.design" });
    const { getByTestId } = render(<SetupStepView />);
    expect(getByTestId("barcode-setup-panel-all")).toBeTruthy();
  });
});
