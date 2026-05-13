/**
 * WizardContainer.test.tsx — E2 WizardContainer unit tests
 *
 * i18n is initialized with en.json values (test-setup.ts: initI18n("en")),
 * so t() returns actual English labels, not raw keys.
 */

import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import userEvent from "@testing-library/user-event";

vi.mock("@/lib/ipc-kuro", () => ({
  sendRequest: vi.fn(),
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
}));

import { WizardContainer } from "./WizardContainer";

describe("WizardContainer", () => {
  it("renders wizard-container testid", () => {
    render(
      <WizardContainer stepIndex={1} stepTotal={4} titleKey="phaseC.subSteps.design.load">
        <div data-testid="child" />
      </WizardContainer>,
    );
    expect(screen.getByTestId("wizard-container")).toBeTruthy();
  });

  it("renders heading with step label and translated title", () => {
    render(
      <WizardContainer stepIndex={2} stepTotal={4} titleKey="phaseC.subSteps.design.variant">
        <div />
      </WizardContainer>,
    );
    const heading = screen.getByRole("heading", { level: 2 });
    // "Step 2: Pool Filters" (en.json values)
    expect(heading.textContent).toContain("Step 2");
    expect(heading.textContent).toContain("Pool Filters");
  });

  it("renders description when descriptionKey is provided", () => {
    render(
      <WizardContainer
        stepIndex={1}
        stepTotal={4}
        titleKey="phaseC.subSteps.design.load"
        descriptionKey="phaseE.descriptions.design.load"
      >
        <div />
      </WizardContainer>,
    );
    // Actual text from en.json
    expect(
      screen.getByText("Upload an EVOLVEpro CSV or paste a protein sequence."),
    ).toBeTruthy();
  });

  it("does not render description when descriptionKey is absent", () => {
    render(
      <WizardContainer stepIndex={1} stepTotal={4} titleKey="phaseC.subSteps.design.load">
        <div />
      </WizardContainer>,
    );
    const desc = screen.queryByText(
      "Upload an EVOLVEpro CSV or paste a protein sequence.",
    );
    expect(desc).toBeNull();
  });

  it("Back button disabled when onPrev is undefined", () => {
    render(
      <WizardContainer stepIndex={1} stepTotal={4} titleKey="phaseC.subSteps.design.load" onNext={() => {}}>
        <div />
      </WizardContainer>,
    );
    const backBtn = screen.getByRole("button", { name: "Back" });
    expect((backBtn as HTMLButtonElement).disabled).toBe(true);
  });

  it("Back button enabled when onPrev is provided", () => {
    render(
      <WizardContainer
        stepIndex={2}
        stepTotal={4}
        titleKey="phaseC.subSteps.design.variant"
        onPrev={() => {}}
        onNext={() => {}}
      >
        <div />
      </WizardContainer>,
    );
    const backBtn = screen.getByRole("button", { name: "Back" });
    expect((backBtn as HTMLButtonElement).disabled).toBe(false);
  });

  it("Next button not rendered when onNext is undefined (design.params case)", () => {
    render(
      <WizardContainer stepIndex={4} stepTotal={4} titleKey="phaseC.subSteps.design.params" onPrev={() => {}}>
        <div />
      </WizardContainer>,
    );
    const nextBtn = screen.queryByRole("button", { name: "Next" });
    expect(nextBtn).toBeNull();
  });

  it("Next button calls onNext when clicked", async () => {
    const onNext = vi.fn();
    render(
      <WizardContainer stepIndex={1} stepTotal={4} titleKey="phaseC.subSteps.design.load" onNext={onNext}>
        <div />
      </WizardContainer>,
    );
    const nextBtn = screen.getByRole("button", { name: "Next" });
    await userEvent.click(nextBtn);
    expect(onNext).toHaveBeenCalledOnce();
  });

  it("renders children inside container", () => {
    render(
      <WizardContainer stepIndex={1} stepTotal={4} titleKey="phaseC.subSteps.design.load">
        <div data-testid="my-child">content</div>
      </WizardContainer>,
    );
    expect(screen.getByTestId("my-child")).toBeTruthy();
  });

  it("progress indicator shows step n / total", () => {
    render(
      <WizardContainer stepIndex={3} stepTotal={4} titleKey="phaseC.subSteps.design.mutation">
        <div />
      </WizardContainer>,
    );
    expect(screen.getByText("Step 3 / 4")).toBeTruthy();
  });
});
