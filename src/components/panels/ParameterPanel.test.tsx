/**
 * ParameterPanel, the design count is bounded to one plate at the input.
 *
 * The store clamp is covered in designSlice.maxPrimers.test.ts. What is only
 * observable here is the pair the user actually experiences: the entry is
 * refused out loud, and the field stops showing the number that was refused.
 */

import { fireEvent, render, screen, cleanup } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useAppStore } from "@/store/appStore";
import { ParameterPanel } from "./ParameterPanel";

vi.mock("@/lib/ipc-kuro", () => ({
  sendRequest: vi.fn(),
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
}));

function designCountInput(): HTMLInputElement {
  // The design count is the only spinner rendered outside Advanced options,
  // which starts collapsed.
  const input = screen
    .getByText("Design count:")
    .closest("label")
    ?.querySelector("input[type=number]");
  if (!(input instanceof HTMLInputElement)) throw new Error("design count input not found");
  return input;
}

describe("ParameterPanel design count", () => {
  beforeEach(() => {
    useAppStore.setState({
      maxPrimers: 95,
      mutationInputMode: "text",
      evolveproTotalCount: 0,
      evolveproCsvPath: "",
      mutationText: "",
    });
  });

  afterEach(() => {
    cleanup();
    useAppStore.setState({ maxPrimers: 95 });
  });

  it("accepts a count past two rounds without a dialog", () => {
    render(<ParameterPanel />);
    const input = designCountInput();

    fireEvent.change(input, { target: { value: "500" } });
    fireEvent.blur(input);

    // No design bound: 500 is exported as six rounds over several plates.
    expect(useAppStore.getState().maxPrimers).toBe(500);
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(input.value).toBe("500");
  });

  it("clears a normalized entry from the field when the store does not change", () => {
    // The store stays at 1 here (0 -> 1), so a field that only resyncs on a
    // store change would keep displaying 0.
    useAppStore.setState({ maxPrimers: 1 });
    render(<ParameterPanel />);
    const input = designCountInput();

    fireEvent.change(input, { target: { value: "0" } });
    fireEvent.blur(input);

    expect(input.value).toBe("1");
  });

  it("accepts a count past one plate without a dialog", () => {
    render(<ParameterPanel />);
    const input = designCountInput();

    fireEvent.change(input, { target: { value: "97" } });
    fireEvent.blur(input);

    expect(useAppStore.getState().maxPrimers).toBe(97);
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });

  it("puts no max attribute on the design count outside EVOLVEpro", () => {
    useAppStore.setState({ mutationInputMode: "text" });
    render(<ParameterPanel />);
    expect(designCountInput().getAttribute("max")).toBeNull();
  });
});
