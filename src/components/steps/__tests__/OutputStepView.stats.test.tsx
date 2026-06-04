/**
 * OutputStepView.stats.test.tsx — primerCount reflects excludedDesignMutations
 *
 * Mirrors mock setup from OutputStepView.splitter.test.tsx.
 */

import { render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/ipc-kuro", () => ({
  sendRequest: vi.fn(),
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
}));

vi.mock("@/components/widgets/PlateMap", () => ({
  PlateMap: () => <div data-testid="plate-map-mock">plate</div>,
}));
vi.mock("@/components/widgets/ResultTable", () => ({
  ResultTable: () => <div data-testid="result-table-mock">table</div>,
}));

import { OutputStepView } from "../OutputStepView";
import { useAppStore } from "@/store/appStore";

function mkPrimer(mutation: string) {
  return {
    mutation,
    aa_position: 1,
    codon_pos: 1,
    forward_seq: "ATCG",
    reverse_seq: "CGAT",
    fwd_len: 4,
    rev_len: 4,
    overlap_len: 20,
    tm_no_fwd: 60,
    tm_no_rev: 60,
    tm_overlap: 60,
    tm_condition_met: true,
    tolerance_used: 0,
    has_offtarget: false,
  };
}

describe("OutputStepView primerCount reflects excluded mutations", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  afterEach(() => {
    window.localStorage.clear();
    useAppStore.setState({
      designResults: [],
      plateMappings: [],
      failedMutations: [],
      rescueStats: null,
      excludedDesignMutations: [],
    } as never);
  });

  it("primers stat shows full count when no exclusions", () => {
    const N = 5;
    useAppStore.setState({
      mutationInputMode: "evolvepro",
      designResults: Array.from({ length: N }, (_, i) => mkPrimer(`M${i}A`)),
      plateMappings: [],
      failedMutations: [],
      rescueStats: null,
      excludedDesignMutations: [],
    } as never);
    render(<OutputStepView />);
    // primerCount renders inside the first <dd> of the stats <dl>
    // The value "5" appears as the text of that element
    const dds = document.querySelectorAll("dl dd");
    expect(dds.length).toBeGreaterThan(0);
    expect(dds[0]!.textContent).toBe("5");
  });

  it("primers stat drops by 1 after one mutation is excluded", () => {
    const N = 5;
    const results = Array.from({ length: N }, (_, i) => mkPrimer(`M${i}A`));
    useAppStore.setState({
      mutationInputMode: "evolvepro",
      designResults: results,
      plateMappings: [],
      failedMutations: [],
      rescueStats: null,
      excludedDesignMutations: [],
    } as never);
    const { rerender } = render(<OutputStepView />);
    expect(document.querySelectorAll("dl dd")[0]!.textContent).toBe("5");

    useAppStore.setState({ excludedDesignMutations: ["M0A"] });
    rerender(<OutputStepView />);
    expect(document.querySelectorAll("dl dd")[0]!.textContent).toBe("4");
  });
});
