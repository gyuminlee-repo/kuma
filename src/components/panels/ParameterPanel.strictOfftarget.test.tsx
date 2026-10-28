/**
 * The strict off-target switch: the control, the request field, and what a
 * workspace carries.
 *
 * The toggle is a design input, so flipping it has to clear results designed
 * under the previous value. The request field is what makes the switch reach
 * the engine at all.
 */

import { fireEvent, render, screen, cleanup } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useAppStore } from "@/store/appStore";
import { buildDesignRequestPayload } from "@/store/slices/designSlice.helpers";
import { buildKuroSnapshot, type KuroSnapshotState } from "@/lib/kuroSnapshot";
import { migrateWorkspace } from "@/lib/workspaceMigrate";
import { ParameterPanel } from "./ParameterPanel";

vi.mock("@/lib/ipc-kuro", () => ({
  sendRequest: vi.fn(),
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
}));

function strictCheckbox(): HTMLInputElement {
  const input = screen
    .getByText("Strict off-target check")
    .closest("label")
    ?.querySelector("input[type=checkbox]");
  if (!(input instanceof HTMLInputElement)) {
    throw new Error("strict off-target checkbox not found");
  }
  return input;
}

describe("ParameterPanel strict off-target toggle", () => {
  beforeEach(() => {
    useAppStore.setState({ strictOfftarget: false, showBenchmark: false });
  });

  afterEach(() => {
    cleanup();
    useAppStore.setState({ strictOfftarget: false });
  });

  it("starts off and writes the store when switched on", () => {
    render(<ParameterPanel />);
    // The switch lives under Advanced options, which starts collapsed.
    fireEvent.click(screen.getByText("Advanced options"));

    const box = strictCheckbox();
    expect(box.checked).toBe(false);

    fireEvent.click(box);
    expect(useAppStore.getState().strictOfftarget).toBe(true);

    fireEvent.click(strictCheckbox());
    expect(useAppStore.getState().strictOfftarget).toBe(false);
  });

  it("clears design results, since the switch changes which candidates survive", () => {
    useAppStore.setState({
      successCount: 7,
      totalCount: 7,
    });
    useAppStore.getState().setStrictOfftarget(true);
    expect(useAppStore.getState().successCount).toBe(0);
  });
});

describe("strict off-target in the design request", () => {
  const base = {
    fastaPath: "/p/in.gb",
    targetStart: 0,
    limitedText: "A1V",
    selectedPolymerase: "Q5",
    codonStrategy: "closest" as const,
    organism: "ecoli",
    tmFwdTarget: 62,
    tmRevTarget: 58,
    tmOverlapTarget: 42,
    gcMin: 40,
    gcMax: 60,
    primerLenEnabled: false,
    fwdLenMin: 18,
    fwdLenMax: 39,
    revLenMin: 19,
    revLenMax: 27,
    overlapMode: "partial" as const,
    rescuePool: [],
    tolMax: 4,
    randomSeed: null,
    fillOnFailure: true,
  };

  it("sends the switch either way rather than leaving the field out", () => {
    expect(
      buildDesignRequestPayload({ ...base, strictOfftarget: false }),
    ).toMatchObject({ strict_offtarget: false });
    expect(
      buildDesignRequestPayload({ ...base, strictOfftarget: true }),
    ).toMatchObject({ strict_offtarget: true });
  });
});

describe("strict off-target persistence", () => {
  it("is recorded in the autosave snapshot", () => {
    const state = {
      ...(useAppStore.getState() as unknown as KuroSnapshotState),
      strictOfftarget: true,
    };
    const snapshot = buildKuroSnapshot(state, null);
    expect(snapshot.parameters).toMatchObject({ strict_offtarget: true });
  });

  it("reads a workspace written before the switch existed as off", () => {
    const migrated = migrateWorkspace({
      version: 1,
      fastaPath: "",
      mutationInputMode: "text",
      mutationText: "",
      evolveproCsvPath: "",
      selectedGene: "",
      codonStrategy: "closest",
      maxPrimers: 95,
      designResults: [],
      successCount: 0,
      totalCount: 0,
      failedMutations: [],
      plateMappings: [],
      dedupInfo: {},
      tableSorting: [],
      manuallySwapped: {},
      customCandidates: {},
      tmFwdTarget: 62,
      tmRevTarget: 58,
      tmOverlapTarget: 42,
      gcMin: 40,
      gcMax: 60,
      overlapMode: "full",
    }, "1", "0.3");

    expect(migrated.settings).toMatchObject({ strictOfftarget: false });
  });
});
