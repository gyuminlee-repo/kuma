/**
 * Two numeric fields keep a local draft string so a half-typed number is not
 * committed on every keystroke: the exposed-candidate count in MutationInput
 * and the per-position cap in DiversityOptions. The draft is seeded from the
 * store once, at mount. When the store changes while the field stays mounted
 * (project restore landing after the panel rendered, Clear All) the field must
 * follow, as the campaign round field beside it already does.
 */

import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useAppStore } from "@/store/appStore";

vi.mock("@tauri-apps/plugin-dialog", () => ({ open: vi.fn() }));
vi.mock("../../../lib/file-utils", () => ({ browseFile: vi.fn() }));
vi.mock("../../../lib/workspace", () => ({ useArtifact: () => null, getActiveWorkspace: () => null }));
vi.mock("./SourceColumnPanel", () => ({
  SourceColumnPanel: () => <div data-testid="source-column-panel" />,
}));
vi.mock("../../widgets/EvolveproSelectTable", () => ({
  EvolveproSelectTable: () => <div data-testid="evolvepro-select-table" />,
}));

import { MutationInput } from "./MutationInput";
import { DiversityOptions } from "./DiversityOptions";

afterEach(() => {
  useAppStore.getState().resetAll();
});

describe("MutationInput exposed-candidate field", () => {
  it("shows the store value after the store changes under a mounted field", () => {
    useAppStore.setState({
      mutationInputMode: "evolvepro",
      evolveproCsvPath: "/p/evolvepro.csv",
      evolveproTotalCount: 2,
      evolveproRankedCandidates: [
        { variant: "A1V", y_pred: 0.9, aa_position: 1 },
        { variant: "C2V", y_pred: 0.8, aa_position: 2 },
      ],
      evolveproSelectedVariants: ["A1V"],
      evolveproExtraExposed: 10,
    });
    render(<MutationInput />);
    const field = document.getElementById("extra-exposed-input") as HTMLInputElement;
    expect(field.value).toBe("10");

    act(() => {
      useAppStore.setState({ evolveproExtraExposed: 25 });
    });

    expect((document.getElementById("extra-exposed-input") as HTMLInputElement).value).toBe("25");
  });

  it("does not overwrite a draft the operator is still typing", () => {
    useAppStore.setState({
      mutationInputMode: "evolvepro",
      evolveproCsvPath: "/p/evolvepro.csv",
      evolveproRankedCandidates: [{ variant: "A1V", y_pred: 0.9, aa_position: 1 }],
      evolveproSelectedVariants: [],
      evolveproExtraExposed: 10,
    });
    render(<MutationInput />);
    const field = document.getElementById("extra-exposed-input") as HTMLInputElement;
    fireEvent.change(field, { target: { value: "" } });

    // An unrelated store write re-renders the panel; the blank draft stays.
    act(() => {
      useAppStore.setState({ evolveproTotalCount: 7 });
    });

    expect((document.getElementById("extra-exposed-input") as HTMLInputElement).value).toBe("");
  });
});

describe("DiversityOptions per-position cap field", () => {
  function capField(value: string): HTMLInputElement | undefined {
    return (screen.getAllByRole("spinbutton") as HTMLInputElement[]).find(
      (el) => el.min === "1" && el.max === "20" && el.value === value,
    );
  }

  it("shows the store value after the store changes under a mounted field", () => {
    useAppStore.setState({ maxPerPosition: 3 });
    render(<DiversityOptions />);
    fireEvent.click(screen.getByRole("button", { name: /Advanced options/ }));
    expect(capField("3")).toBeDefined();

    act(() => {
      useAppStore.setState({ maxPerPosition: 5 });
    });

    expect(capField("5")).toBeDefined();
    expect(capField("3")).toBeUndefined();
  });
});
