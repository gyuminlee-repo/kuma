/**
 * OutputStepView.splitter.test.tsx — patch-260514 #7
 *
 * [source: spec patch-260514 #7 — primer/plate 영역 drag resize + sidebar toggle]
 *
 * 시나리오:
 *  (a) 기본 render: primer + plate 두 영역 모두 표시
 *  (b) toggle click → plate 영역 aria-hidden + display:none
 *  (c) localStorage 비율 적용 후 render → splitPct 회복 (width style 단언)
 */

import { fireEvent, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/ipc-kuro", () => ({
  sendRequest: vi.fn(),
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
}));

// PlateMap pulls from store; mock to avoid heavy rendering
vi.mock("@/components/widgets/PlateMap", () => ({
  PlateMap: () => <div data-testid="plate-map-mock">plate</div>,
}));
vi.mock("@/components/widgets/ResultTable", () => ({
  ResultTable: () => <div data-testid="result-table-mock">table</div>,
}));

import { OutputStepView } from "../OutputStepView";
import { useAppStore } from "@/store/appStore";

const SPLIT_KEY = "kuro.output.split";
const COLLAPSED_KEY = "kuro.output.plateCollapsed";

const baseState = {
  designResults: [{ id: "p1" }],
  plateMappings: [],
  failedMutations: [],
  rescueStats: null,
};

describe("OutputStepView splitter + sidebar toggle (patch-260514 #7)", () => {
  beforeEach(() => {
    window.localStorage.clear();
    useAppStore.setState(baseState as never);
  });

  afterEach(() => {
    window.localStorage.clear();
  });

  it("(a) renders primer + plate panels by default", () => {
    const { getByTestId } = render(<OutputStepView />);
    const primer = getByTestId("output-primer-panel");
    const plate = getByTestId("output-plate-panel");
    expect(primer).toBeTruthy();
    expect(plate).toBeTruthy();
    expect(plate.getAttribute("aria-hidden")).toBe("false");
  });

  it("(b) toggle hides plate panel and persists collapsed=1", () => {
    const { getByTestId, getByLabelText } = render(<OutputStepView />);
    const btn = getByLabelText("Hide plate map");
    fireEvent.click(btn);
    const plate = getByTestId("output-plate-panel");
    expect(plate.getAttribute("aria-hidden")).toBe("true");
    expect((plate as HTMLElement).style.display).toBe("none");
    expect(window.localStorage.getItem(COLLAPSED_KEY)).toBe("1");
  });

  it("(c) localStorage split is restored on render", () => {
    window.localStorage.setItem(SPLIT_KEY, "70");
    const { getByTestId } = render(<OutputStepView />);
    const primer = getByTestId("output-primer-panel") as HTMLElement;
    expect(primer.style.width).toBe("70%");
  });

  it("(c) localStorage collapsed=1 keeps plate hidden on initial render", () => {
    window.localStorage.setItem(COLLAPSED_KEY, "1");
    const { getByTestId } = render(<OutputStepView />);
    const plate = getByTestId("output-plate-panel") as HTMLElement;
    expect(plate.style.display).toBe("none");
  });
});
