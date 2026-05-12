/**
 * SdmStepView.test.tsx — sub-step 마운트 어설션
 */

import { render } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";

vi.mock("@/lib/ipc-kuro", () => ({
  sendRequest: vi.fn(),
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
}));

vi.mock("@/components/panels/InputPanel/MutationInput", () => ({
  MutationInput: () => <div data-testid="mutation-input" />,
}));
vi.mock("@/components/panels/ParameterPanelSection", () => ({
  ParameterPanelSection: ({ section }: { section: string }) => (
    <div data-testid={`parameter-panel-section-${section}`} />
  ),
}));
vi.mock("./RunDesignAction", () => ({
  RunDesignAction: () => <div data-testid="run-design-action" />,
}));
vi.mock("@/components/widgets/ResultTable", () => ({
  ResultTable: () => <div data-testid="result-table" />,
}));

import { SdmStepView } from "./SdmStepView";

describe("SdmStepView", () => {
  it("sdm.mutations mounts MutationInput", () => {
    const { getByTestId } = render(<SdmStepView subStep="sdm.mutations" />);
    expect(getByTestId("mutation-input")).toBeTruthy();
  });

  it("sdm.codon mounts ParameterPanelSection with section=codon", () => {
    const { getByTestId } = render(<SdmStepView subStep="sdm.codon" />);
    expect(getByTestId("parameter-panel-section-codon")).toBeTruthy();
  });

  it("sdm.polymerase mounts ParameterPanelSection with section=polymerase-tm", () => {
    const { getByTestId } = render(<SdmStepView subStep="sdm.polymerase" />);
    expect(getByTestId("parameter-panel-section-polymerase-tm")).toBeTruthy();
  });

  it("sdm.gc mounts ParameterPanelSection with section=gc-length", () => {
    const { getByTestId } = render(<SdmStepView subStep="sdm.gc" />);
    expect(getByTestId("parameter-panel-section-gc-length")).toBeTruthy();
  });

  it("sdm.run mounts RunDesignAction", () => {
    const { getByTestId } = render(<SdmStepView subStep="sdm.run" />);
    expect(getByTestId("run-design-action")).toBeTruthy();
  });

  it("sdm.run mounts ResultTable", () => {
    const { getByTestId } = render(<SdmStepView subStep="sdm.run" />);
    expect(getByTestId("result-table")).toBeTruthy();
  });

  it("unknown sub-step returns null", () => {
    const { container } = render(<SdmStepView subStep="unknown.step" />);
    expect(container.firstChild).toBeNull();
  });
});
