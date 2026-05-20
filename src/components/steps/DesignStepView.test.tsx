/**
 * DesignStepView.test.tsx — Phase G: 4 sub-step 마운트 어설션
 *
 * [source: spec Phase G — Design 4 sub-step 재배치 (#2)]
 * E3: SequenceViewer는 AppLayout main slot으로 호이스팅됨 — DesignStepView 내에서 미포함.
 * E2: 각 sub-step은 WizardContainer로 감싸짐.
 * G7: design.submit에서 UniprotSearch 직접 마운트 없음 (DiversitySections 경유).
 */

import { render, fireEvent, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";

const mocks = vi.hoisted(() => ({
  runDesign: vi.fn(),
}));

vi.mock("@/lib/ipc-kuro", () => ({
  sendRequest: vi.fn(),
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
}));

vi.mock("@/hooks/useRunDesign", () => ({
  useRunDesign: () => ({
    run: mocks.runDesign,
    isDesigning: false,
    missingFields: [],
    hasBlockingIssue: false,
    sizeWarning: null,
    setSizeWarning: vi.fn(),
    preflightResult: null,
    setPreflightResult: vi.fn(),
  }),
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
  RunDesignActionView: () => <div data-testid="run-design-action" />,
}));

import { DesignStepView } from "./DesignStepView";
import { useAppStore } from "@/store/appStore";

describe("DesignStepView (Phase G)", () => {
  beforeEach(() => {
    useAppStore.setState({ currentSubStep: "design.load", evolveproMode: "topN" });
    mocks.runDesign.mockReset();
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

  it("design.mutation mounts MutationInput", () => {
    useAppStore.setState({ currentSubStep: "design.mutation" });
    const { getByTestId } = render(<DesignStepView />);
    expect(getByTestId("mutation-input")).toBeTruthy();
  });

  it("design.params mounts ParameterPanel (RunDesignAction removed from this step)", () => {
    useAppStore.setState({ currentSubStep: "design.params" });
    const { getByTestId, queryByTestId } = render(<DesignStepView />);
    expect(getByTestId("parameter-panel")).toBeTruthy();
    expect(queryByTestId("run-design-action")).toBeNull();
  });

  it("design.submit in top-N mode hides DiversityOptions and mounts RunDesignAction", () => {
    useAppStore.setState({ currentSubStep: "design.submit", evolveproMode: "topN" });
    const { getByTestId, queryByTestId } = render(<DesignStepView />);
    expect(queryByTestId("diversity-options")).toBeNull();
    expect(getByTestId("run-design-action")).toBeTruthy();
  });

  it("design.submit in pipeline mode mounts DiversityOptions + RunDesignAction", () => {
    useAppStore.setState({ currentSubStep: "design.submit", evolveproMode: "pipeline" });
    const { getByTestId } = render(<DesignStepView />);
    expect(getByTestId("diversity-options")).toBeTruthy();
    expect(getByTestId("run-design-action")).toBeTruthy();
  });

  it("design.submit footer Run Design button calls shared run action", async () => {
    useAppStore.setState({ currentSubStep: "design.submit" });
    render(<DesignStepView />);
    await userEvent.setup().click(screen.getByRole("button", { name: "Run Design" }));
    expect(mocks.runDesign).toHaveBeenCalledOnce();
  });

  it("design.submit does NOT mount UniprotSearch directly (Phase G #7 — via DiversitySections)", () => {
    useAppStore.setState({ currentSubStep: "design.submit" });
    // UniprotSearch is mocked — if DesignStepView directly mounted it, it would appear
    // DiversityOptions mock does NOT include UniprotSearch, so this asserts direct mount is absent
    const { queryByTestId } = render(<DesignStepView />);
    expect(queryByTestId("uniprot-search")).toBeNull();
  });

  it("design.variant sub-step no longer exists (Phase G)", () => {
    useAppStore.setState({ currentSubStep: "design.variant" as never });
    const { container } = render(<DesignStepView />);
    // Falls through to default: null
    expect(container.firstChild).toBeNull();
  });

  it("design.load shows missing-input dialog when seqInfo absent and Next clicked", () => {
    useAppStore.setState({ currentSubStep: "design.load", seqInfo: null });
    const { getByRole, queryByRole } = render(<DesignStepView />);
    expect(queryByRole("dialog")).toBeNull();
    const nextBtn = getByRole("button", { name: /next|다음/i });
    fireEvent.click(nextBtn);
    expect(getByRole("dialog")).toBeTruthy();
  });

  it("design.mutation shows missing-input dialog when mutationText empty and evolveproTotalCount 0", () => {
    useAppStore.setState({
      currentSubStep: "design.mutation",
      mutationText: "",
      evolveproTotalCount: 0,
    });
    const { getByRole, queryByRole } = render(<DesignStepView />);
    expect(queryByRole("dialog")).toBeNull();
    const nextBtn = getByRole("button", { name: /next|다음/i });
    fireEvent.click(nextBtn);
    expect(getByRole("dialog")).toBeTruthy();
  });

  it("each sub-step renders inside WizardContainer", () => {
    const steps = [
      "design.load",
      "design.mutation",
      "design.params",
      "design.submit",
    ] as const;

    for (const step of steps) {
      useAppStore.setState({ currentSubStep: step });
      const { getByTestId, unmount } = render(<DesignStepView />);
      expect(getByTestId("wizard-container"), `WizardContainer present for ${step}`).toBeTruthy();
      unmount();
    }
  });
});
