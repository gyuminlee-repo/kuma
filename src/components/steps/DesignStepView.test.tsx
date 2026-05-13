/**
 * DesignStepView.test.tsx — 4 sub-step 마운트 어설션 (D2.1, Phase E)
 *
 * E3: SequenceViewer는 AppLayout main slot으로 호이스팅됨 — DesignStepView 내에서 미포함.
 * E2: 각 sub-step은 WizardContainer로 감싸짐.
 */

import { render } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("@/lib/ipc-kuro", () => ({
  sendRequest: vi.fn(),
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
}));

vi.mock("@/components/panels/InputPanel/SequenceInput", () => ({
  SequenceInput: () => <div data-testid="sequence-input" />,
}));
vi.mock("@/components/panels/InputPanel/UniprotSearch", () => ({
  UniprotSearch: () => <div data-testid="uniprot-search" />,
}));
vi.mock("@/components/panels/InputPanel/DiversityOptions", () => ({
  DiversityOptions: () => <div data-testid="diversity-options" />,
}));
vi.mock("@/components/panels/InputPanel/MutationInput", () => ({
  MutationInput: () => <div data-testid="mutation-input" />,
}));
vi.mock("@/components/panels/ParameterPanel", () => ({
  ParameterPanel: () => <div data-testid="parameter-panel" />,
}));
vi.mock("./RunDesignAction", () => ({
  RunDesignAction: () => <div data-testid="run-design-action" />,
}));

import { DesignStepView } from "./DesignStepView";
import { useAppStore } from "@/store/appStore";

describe("DesignStepView", () => {
  beforeEach(() => {
    useAppStore.setState({ currentSubStep: "design.load" });
  });

  it("design.load mounts WizardContainer + SequenceInput", () => {
    const { getByTestId } = render(<DesignStepView />);
    expect(getByTestId("wizard-container")).toBeTruthy();
    expect(getByTestId("sequence-input")).toBeTruthy();
  });

  it("design.load does NOT mount SequenceViewer (hoisted to AppLayout, E3)", () => {
    const { queryByTestId } = render(<DesignStepView />);
    expect(queryByTestId("sequence-viewer")).toBeNull();
  });

  it("design.variant mounts UniprotSearch and DiversityOptions", () => {
    useAppStore.setState({ currentSubStep: "design.variant" });
    const { getByTestId } = render(<DesignStepView />);
    expect(getByTestId("uniprot-search")).toBeTruthy();
    expect(getByTestId("diversity-options")).toBeTruthy();
  });

  it("design.mutation mounts MutationInput", () => {
    useAppStore.setState({ currentSubStep: "design.mutation" });
    const { getByTestId } = render(<DesignStepView />);
    expect(getByTestId("mutation-input")).toBeTruthy();
  });

  it("design.params mounts ParameterPanel and RunDesignAction", () => {
    useAppStore.setState({ currentSubStep: "design.params" });
    const { getByTestId } = render(<DesignStepView />);
    expect(getByTestId("parameter-panel")).toBeTruthy();
    expect(getByTestId("run-design-action")).toBeTruthy();
  });

  it("each sub-step renders inside WizardContainer", () => {
    const steps = [
      "design.load",
      "design.variant",
      "design.mutation",
      "design.params",
    ] as const;

    for (const step of steps) {
      useAppStore.setState({ currentSubStep: step });
      const { getByTestId, unmount } = render(<DesignStepView />);
      expect(getByTestId("wizard-container"), `WizardContainer present for ${step}`).toBeTruthy();
      unmount();
    }
  });
});
