/**
 * DesignStepView.test.tsx — 4 sub-step 마운트 어설션 (D2.1)
 */

import { render } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("@/lib/ipc-kuro", () => ({
  sendRequest: vi.fn(),
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
}));

vi.mock("@/components/widgets/SequenceViewer", () => ({
  SequenceViewer: () => <div data-testid="sequence-viewer" />,
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

  it("design.load mounts SequenceViewer + SequenceInput", () => {
    const { getByTestId } = render(<DesignStepView />);
    expect(getByTestId("sequence-viewer")).toBeTruthy();
    expect(getByTestId("sequence-input")).toBeTruthy();
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

  it("SequenceViewer mounts in all sub-steps (design.load baseline)", () => {
    // SequenceViewer는 sub-step 무관하게 항상 상단에 마운트된다
    const { getByTestId } = render(<DesignStepView />);
    expect(getByTestId("sequence-viewer")).toBeTruthy();
  });
});
