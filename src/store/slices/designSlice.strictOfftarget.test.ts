/**
 * The strict off-target switch on the paths that are not the design search.
 *
 * evaluate_primer reports hits instead of rejecting, so the switch decides
 * what the user is told about a primer pair they typed in themselves. A reset
 * has to put the switch back to off, because that is what keeps an autosave
 * written before the switch existed from inheriting the previous project's
 * value: hydration resets the store first and then applies only the fields the
 * snapshot carries.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  sendRequest: vi.fn(),
}));

vi.mock("../../lib/ipc-kuro", () => ({
  sendRequest: mocks.sendRequest,
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
}));

import { useAppStore } from "../appStore";

describe("evaluate_primer carries the strict off-target switch", () => {
  beforeEach(() => {
    mocks.sendRequest.mockReset();
    mocks.sendRequest.mockResolvedValue(null);
    useAppStore.setState({
      fastaPath: "/project/input.gb",
      selectedGene: "0",
      strictOfftarget: false,
    });
  });

  afterEach(() => {
    useAppStore.setState({ strictOfftarget: false });
  });

  it("sends false while the switch is off", async () => {
    await useAppStore.getState().evaluateCustomPrimer("A1V", "ATGC", "GCAT");
    expect(mocks.sendRequest).toHaveBeenCalledWith(
      "evaluate_primer",
      expect.objectContaining({ strict_offtarget: false }),
    );
  });

  it("sends true once the switch is on", async () => {
    useAppStore.setState({ strictOfftarget: true });
    await useAppStore.getState().evaluateCustomPrimer("A1V", "ATGC", "GCAT");
    expect(mocks.sendRequest).toHaveBeenCalledWith(
      "evaluate_primer",
      expect.objectContaining({ strict_offtarget: true }),
    );
  });
});

describe("resetAll puts the switch back to off", () => {
  it("clears a value left on by the previous project", () => {
    useAppStore.setState({ strictOfftarget: true });
    useAppStore.getState().resetAll({ preserveWorkspaceArtifacts: true });
    expect(useAppStore.getState().strictOfftarget).toBe(false);
  });
});
