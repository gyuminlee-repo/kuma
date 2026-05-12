/**
 * VariantStepView.test.tsx — sub-step 마운트 어설션
 */

import { render } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";

vi.mock("@/lib/ipc-kuro", () => ({
  sendRequest: vi.fn(),
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
}));

// Mock heavy sub-components
vi.mock("@/components/panels/InputPanel/SequenceInput", () => ({
  SequenceInput: () => <div data-testid="sequence-input" />,
}));
vi.mock("@/components/panels/InputPanel/UniprotSearch", () => ({
  UniprotSearch: () => <div data-testid="uniprot-search" />,
}));
vi.mock("@/components/panels/InputPanel/DiversityOptions", () => ({
  DiversityOptions: () => <div data-testid="diversity-options" />,
}));
vi.mock("@/components/widgets/SequenceViewer", () => ({
  SequenceViewer: () => <div data-testid="sequence-viewer" />,
}));

import { VariantStepView } from "./VariantStepView";

describe("VariantStepView", () => {
  it("variant.load mounts SequenceInput", () => {
    const { getByTestId } = render(<VariantStepView subStep="variant.load" />);
    expect(getByTestId("sequence-input")).toBeTruthy();
  });

  it("variant.load mounts SequenceViewer", () => {
    const { getByTestId } = render(<VariantStepView subStep="variant.load" />);
    expect(getByTestId("sequence-viewer")).toBeTruthy();
  });

  it("variant.select mounts UniprotSearch", () => {
    const { getByTestId } = render(<VariantStepView subStep="variant.select" />);
    expect(getByTestId("uniprot-search")).toBeTruthy();
  });

  it("variant.adaptive mounts DiversityOptions", () => {
    const { getByTestId } = render(<VariantStepView subStep="variant.adaptive" />);
    expect(getByTestId("diversity-options")).toBeTruthy();
  });

  it("variant.domain mounts DiversityOptions (Stage 2 full mount)", () => {
    const { getByTestId } = render(<VariantStepView subStep="variant.domain" />);
    expect(getByTestId("diversity-options")).toBeTruthy();
  });

  it("variant.pareto mounts DiversityOptions (Stage 2 full mount)", () => {
    const { getByTestId } = render(<VariantStepView subStep="variant.pareto" />);
    expect(getByTestId("diversity-options")).toBeTruthy();
  });

  it("unknown sub-step returns null", () => {
    const { container } = render(<VariantStepView subStep="unknown.step" />);
    expect(container.firstChild).toBeNull();
  });
});
