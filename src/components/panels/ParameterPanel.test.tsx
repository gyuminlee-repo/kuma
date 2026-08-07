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
import { MAX_MUTATIONS_PER_RUN } from "@/lib/inputThresholds";
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

  it("refuses a count above one plate and clamps the store", () => {
    render(<ParameterPanel />);
    const input = designCountInput();

    fireEvent.change(input, { target: { value: "500" } });
    fireEvent.blur(input);

    expect(useAppStore.getState().maxPrimers).toBe(MAX_MUTATIONS_PER_RUN);
    expect(screen.getByRole("alertdialog")).toBeTruthy();
    expect(screen.getByText(/Design count limited to one plate/i)).toBeTruthy();
    // The rejected number and the bound both appear, so the message says what
    // was refused rather than only that something was.
    expect(screen.getByText(/You entered 500\./)).toBeTruthy();
    expect(screen.getByText(/at most 96 variants/)).toBeTruthy();
    // The bound counts variants, not plates. Forward and reverse primers each
    // take a plate of their own, so 96 variants occupy two plates and the
    // export screens say so. The message has to agree with them.
    expect(screen.getByText(/each fill their own plate/)).toBeTruthy();
    // No "continue anyway": this bound has nothing to continue to.
    expect(screen.queryByRole("button", { name: /continue/i })).toBeNull();
    expect(input.value).toBe(String(MAX_MUTATIONS_PER_RUN));
  });

  it("still clears the field when the store is already at the cap", () => {
    // The store does not change here (96 -> 96), so a field that only resyncs
    // on a store change would keep displaying 500.
    useAppStore.setState({ maxPrimers: MAX_MUTATIONS_PER_RUN });
    render(<ParameterPanel />);
    const input = designCountInput();

    fireEvent.change(input, { target: { value: "500" } });
    fireEvent.blur(input);

    expect(input.value).toBe(String(MAX_MUTATIONS_PER_RUN));
    expect(screen.getByRole("alertdialog")).toBeTruthy();
  });

  it("accepts a count that fits a plate without a dialog", () => {
    render(<ParameterPanel />);
    const input = designCountInput();

    fireEvent.change(input, { target: { value: "50" } });
    fireEvent.blur(input);

    expect(useAppStore.getState().maxPrimers).toBe(50);
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });

  it("caps the input max attribute at one plate", () => {
    render(<ParameterPanel />);
    expect(designCountInput().getAttribute("max")).toBe(String(MAX_MUTATIONS_PER_RUN));
  });
});
