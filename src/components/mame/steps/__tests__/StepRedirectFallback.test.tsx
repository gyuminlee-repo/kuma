/**
 * StepRedirectFallback.test.tsx — sub-step 불일치 시 fallback 동작 검증.
 *
 * [source: spec #12 — sidebar sub-step mismatch 빈 창 방지]
 */

import { render, waitFor } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

import { StepRedirectFallback } from "../StepRedirectFallback";

describe("StepRedirectFallback", () => {
  it("renders role=status with redirecting message", () => {
    const setSubStep = vi.fn();
    const { getByRole } = render(
      <StepRedirectFallback
        currentSub="setup.files"
        expectedFor="analyze"
        setSubStep={setSubStep}
      />,
    );
    expect(getByRole("status")).toBeTruthy();
  });

  it("calls setSubStep with analyze.inputs when expectedFor=analyze", async () => {
    const setSubStep = vi.fn();
    render(
      <StepRedirectFallback
        currentSub="setup.files"
        expectedFor="analyze"
        setSubStep={setSubStep}
      />,
    );
    await waitFor(() => {
      expect(setSubStep).toHaveBeenCalledWith("analyze.inputs");
    });
  });

  it("calls setSubStep with setup.files when expectedFor=setup", async () => {
    const setSubStep = vi.fn();
    render(
      <StepRedirectFallback
        currentSub="analyze.plate"
        expectedFor="setup"
        setSubStep={setSubStep}
      />,
    );
    await waitFor(() => {
      expect(setSubStep).toHaveBeenCalledWith("setup.files");
    });
  });

  it("calls setSubStep with activity.ingest when expectedFor=activity", async () => {
    const setSubStep = vi.fn();
    render(
      <StepRedirectFallback
        currentSub="setup.files"
        expectedFor="activity"
        setSubStep={setSubStep}
      />,
    );
    await waitFor(() => {
      expect(setSubStep).toHaveBeenCalledWith("activity.ingest");
    });
  });
});
