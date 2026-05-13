/**
 * SetupStepView.test.tsx — 3 sub-step 마운트 어설션 (D2.4)
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

  it("setup.files mounts BarcodeSetupPanel with group=files", () => {
    const { getByTestId } = render(<SetupStepView />);
    expect(getByTestId("barcode-setup-panel-files")).toBeTruthy();
  });

  it("setup.design mounts BarcodeSetupPanel with group=design", () => {
    useMameAppStore.setState({ currentMameSubStep: "setup.design" });
    const { getByTestId } = render(<SetupStepView />);
    expect(getByTestId("barcode-setup-panel-design")).toBeTruthy();
  });

  it("setup.design includes output sections (group=design absorbs output)", () => {
    useMameAppStore.setState({ currentMameSubStep: "setup.design" });
    const { getByTestId } = render(<SetupStepView />);
    expect(getByTestId("barcode-setup-panel-design")).toBeTruthy();
  });
});
