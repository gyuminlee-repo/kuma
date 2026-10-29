/**
 * Every KURO numeric field that keeps a draft string and commits it on blur
 * must show, after the commit, the value the store actually holds.
 *
 * The draft used to be pushed back into the field only when the store value
 * changed. An entry the commit normalized to the value the store already held
 * (blank -> the fallback, 12 -> the 10 ceiling, 1.5 -> 1, 0 -> the floor of 1)
 * left the store unchanged, so the field kept showing the rejected text while
 * the design ran on a different number. Each case below fails against that.
 */

import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useAppStore } from "@/store/appStore";

vi.mock("@/lib/ipc-kuro", () => ({
  sendRequest: vi.fn(),
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
}));
vi.mock("@tauri-apps/plugin-dialog", () => ({ open: vi.fn() }));
vi.mock("../../lib/file-utils", () => ({ browseFile: vi.fn() }));
vi.mock("../../lib/workspace", () => ({ useArtifact: () => null, getActiveWorkspace: () => null }));
vi.mock("./InputPanel/SourceColumnPanel", () => ({
  SourceColumnPanel: () => <div data-testid="source-column-panel" />,
}));
vi.mock("../widgets/EvolveproSelectTable", () => ({
  EvolveproSelectTable: () => <div data-testid="evolvepro-select-table" />,
}));

import { ParameterPanel } from "./ParameterPanel";
import { MutationInput } from "./InputPanel/MutationInput";
import { DiversityOptions } from "./InputPanel/DiversityOptions";

afterEach(() => {
  cleanup();
  useAppStore.getState().resetAll();
});

function enter(input: HTMLInputElement, text: string) {
  fireEvent.change(input, { target: { value: text } });
  fireEvent.blur(input);
}

/** The number input in the same row as the label text. */
function fieldBeside(text: string, index = 0): HTMLInputElement {
  const row = screen.getByText(text).parentElement;
  const input = row?.querySelectorAll("input[type=number]")[index];
  if (!(input instanceof HTMLInputElement)) throw new Error(`no number input beside ${text}`);
  return input;
}

function openAdvanced() {
  fireEvent.click(screen.getByRole("button", { name: /Advanced options/ }));
}

describe("ParameterPanel numeric fields", () => {
  it("Tm forward shows the fallback a blank entry committed", () => {
    useAppStore.setState({ overlapMode: "partial", tmFwdTarget: 62 });
    render(<ParameterPanel />);
    openAdvanced();
    const input = fieldBeside("Fwd:");
    enter(input, "");
    expect(useAppStore.getState().tmFwdTarget).toBe(62);
    expect(input.value).toBe("62");
  });

  it("Tm tolerance shows the clamped value when the store already held it", () => {
    useAppStore.setState({ tmTolerance: 10 });
    render(<ParameterPanel />);
    openAdvanced();
    const input = fieldBeside("Tm tol ±");
    enter(input, "12");
    expect(useAppStore.getState().tmTolerance).toBe(10);
    expect(input.value).toBe("10");
  });

  it("Tm tolerance shows the half-degree step the store rounded to", () => {
    useAppStore.setState({ tmTolerance: 4.5 });
    render(<ParameterPanel />);
    openAdvanced();
    const input = fieldBeside("Tm tol ±");
    enter(input, "4.4");
    expect(useAppStore.getState().tmTolerance).toBe(4.5);
    expect(input.value).toBe("4.5");
  });

  it("GC minimum shows the fallback a blank entry committed", () => {
    useAppStore.setState({ gcMin: 40, gcMax: 60 });
    render(<ParameterPanel />);
    openAdvanced();
    const input = fieldBeside("Range:", 0);
    enter(input, "");
    expect(useAppStore.getState().gcMin).toBe(40);
    expect(input.value).toBe("40");
  });

  it("primer length shows the fallback a blank entry committed", () => {
    useAppStore.setState({ overlapMode: "partial", primerLenEnabled: true, fwdLenMin: 17 });
    render(<ParameterPanel />);
    openAdvanced();
    const fwdMin = (screen.getAllByRole("spinbutton") as HTMLInputElement[]).find(
      (el) => el.value === "17",
    );
    if (!fwdMin) throw new Error("forward length minimum not found");
    enter(fwdMin, "");
    expect(useAppStore.getState().fwdLenMin).toBe(17);
    expect(fwdMin.value).toBe("17");
  });

  it("random seed shows the integer it committed when the store already held it", () => {
    useAppStore.setState({ randomSeed: 1 });
    render(<ParameterPanel />);
    openAdvanced();
    const input = screen.getByLabelText("Seed (optional)") as HTMLInputElement;
    enter(input, "1.5");
    expect(useAppStore.getState().randomSeed).toBe(1);
    expect(input.value).toBe("1");
  });

  it("random seed keeps a blank entry as auto", () => {
    useAppStore.setState({ randomSeed: 7 });
    render(<ParameterPanel />);
    openAdvanced();
    const input = screen.getByLabelText("Seed (optional)") as HTMLInputElement;
    enter(input, "");
    expect(useAppStore.getState().randomSeed).toBeNull();
    expect(input.value).toBe("");
  });

  it("random seed restores the stored seed after a negative entry", () => {
    useAppStore.setState({ randomSeed: 7 });
    render(<ParameterPanel />);
    openAdvanced();
    const input = screen.getByLabelText("Seed (optional)") as HTMLInputElement;
    enter(input, "-3");
    expect(useAppStore.getState().randomSeed).toBe(7);
    expect(input.value).toBe("7");
  });

  it("design count still shows the clamped count", () => {
    useAppStore.setState({ maxPrimers: 1, mutationInputMode: "text" });
    render(<ParameterPanel />);
    const input = screen
      .getByText("Design count:")
      .closest("label")
      ?.querySelector("input[type=number]") as HTMLInputElement;
    enter(input, "0");
    expect(useAppStore.getState().maxPrimers).toBe(1);
    expect(input.value).toBe("1");
  });
});

function evolveproState(extra: Partial<ReturnType<typeof useAppStore.getState>> = {}) {
  useAppStore.setState({
    mutationInputMode: "evolvepro",
    evolveproCsvPath: "/p/evolvepro.csv",
    evolveproTotalCount: 2,
    evolveproRankedCandidates: [
      { variant: "A1V", y_pred: 0.9, aa_position: 1 },
      { variant: "C2V", y_pred: 0.8, aa_position: 2 },
    ],
    evolveproSelectedVariants: ["A1V"],
    ...extra,
  });
}

describe("MutationInput numeric fields", () => {
  it("campaign round restores the stored round after a blank entry", () => {
    evolveproState({ evolveproRound: 3 });
    render(<MutationInput />);
    const input = document.getElementById("campaign-round-input") as HTMLInputElement;
    enter(input, "");
    expect(useAppStore.getState().evolveproRound).toBe(3);
    expect(input.value).toBe("3");
  });

  it("campaign round shows the floor the store applied to 0", () => {
    evolveproState({ evolveproRound: 1 });
    render(<MutationInput />);
    const input = document.getElementById("campaign-round-input") as HTMLInputElement;
    enter(input, "0");
    expect(useAppStore.getState().evolveproRound).toBe(1);
    expect(input.value).toBe("1");
  });

  it("campaign round shows the integer a fractional entry committed", () => {
    evolveproState({ evolveproRound: 3 });
    render(<MutationInput />);
    const input = document.getElementById("campaign-round-input") as HTMLInputElement;
    enter(input, "2.7");
    expect(useAppStore.getState().evolveproRound).toBe(2);
    expect(input.value).toBe("2");
  });

  it("campaign round keeps an unset round blank", () => {
    evolveproState({ evolveproRound: 0 });
    render(<MutationInput />);
    const input = document.getElementById("campaign-round-input") as HTMLInputElement;
    expect(input.value).toBe("");
    enter(input, "");
    expect(useAppStore.getState().evolveproRound).toBe(0);
    expect(input.value).toBe("");
  });

  it("round size shows the ceiling when the store already held it", () => {
    evolveproState({ roundSize: 960 });
    render(<MutationInput />);
    const input = document.getElementById("campaign-round-size-input") as HTMLInputElement;
    enter(input, "2000");
    expect(useAppStore.getState().roundSize).toBe(960);
    expect(input.value).toBe("960");
  });

  it("round size shows the integer a fractional entry committed", () => {
    evolveproState({ roundSize: 48 });
    render(<MutationInput />);
    const input = document.getElementById("campaign-round-size-input") as HTMLInputElement;
    enter(input, "12.5");
    expect(useAppStore.getState().roundSize).toBe(12);
    expect(input.value).toBe("12");
  });

  it("exposed candidates restores the stored count after a negative entry", () => {
    evolveproState({ evolveproExtraExposed: 10 });
    render(<MutationInput />);
    const input = document.getElementById("extra-exposed-input") as HTMLInputElement;
    enter(input, "-1");
    expect(useAppStore.getState().evolveproExtraExposed).toBe(10);
    expect(input.value).toBe("10");
  });

  it("exposed candidates restores the stored count after a blank entry", () => {
    evolveproState({ evolveproExtraExposed: 10 });
    render(<MutationInput />);
    const input = document.getElementById("extra-exposed-input") as HTMLInputElement;
    enter(input, "");
    expect(useAppStore.getState().evolveproExtraExposed).toBe(10);
    expect(input.value).toBe("10");
  });

  it("exposed candidates still follows a store change under a mounted field", () => {
    evolveproState({ evolveproExtraExposed: 10 });
    render(<MutationInput />);
    act(() => {
      useAppStore.setState({ evolveproExtraExposed: 25 });
    });
    expect((document.getElementById("extra-exposed-input") as HTMLInputElement).value).toBe("25");
  });
});

describe("DiversityOptions per-position cap", () => {
  function capField(): HTMLInputElement {
    const input = (screen.getAllByRole("spinbutton") as HTMLInputElement[]).find(
      (el) => el.min === "1" && el.max === "20",
    );
    if (!input) throw new Error("per-position cap not found");
    return input;
  }

  it("restores the stored cap after an entry below 1", () => {
    useAppStore.setState({ maxPerPosition: 3 });
    render(<DiversityOptions />);
    fireEvent.click(screen.getByRole("button", { name: /Advanced options/ }));
    const input = capField();
    enter(input, "0");
    expect(useAppStore.getState().maxPerPosition).toBe(3);
    expect(input.value).toBe("3");
  });

  it("restores the stored cap after a blank entry", () => {
    useAppStore.setState({ maxPerPosition: 3 });
    render(<DiversityOptions />);
    fireEvent.click(screen.getByRole("button", { name: /Advanced options/ }));
    const input = capField();
    enter(input, "");
    expect(input.value).toBe("3");
  });

  it("shows the integer a fractional entry committed", () => {
    useAppStore.setState({ maxPerPosition: 3 });
    render(<DiversityOptions />);
    fireEvent.click(screen.getByRole("button", { name: /Advanced options/ }));
    const input = capField();
    enter(input, "2.5");
    expect(useAppStore.getState().maxPerPosition).toBe(2);
    expect(input.value).toBe("2");
  });
});
