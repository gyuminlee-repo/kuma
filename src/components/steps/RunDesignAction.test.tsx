/**
 * RunDesignAction.test.tsx — missing fields display + disabled state
 *
 * Tests:
 *   1. Run button disabled when missingFields present
 *   2. Missing field list rendered with aria-role="alert"
 *   3. Run button enabled when no missing fields and sidecar ready
 *   4. Cancel button appears while isDesigning
 */

import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { useAppStore } from "@/store/appStore";

vi.mock("@/lib/ipc-kuro", () => ({
  sendRequest: vi.fn(),
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
  spawnSidecar: vi.fn(() => Promise.resolve()),
  getLastProgressAt: vi.fn(() => Date.now()),
}));

vi.mock("@/hooks/useKuroAutosave", () => ({
  useFlushKuroBeforeDesign: vi.fn(() => () => Promise.resolve()),
}));

vi.mock("@/lib/preflight", () => ({
  runPreflightCheck: vi.fn(() =>
    Promise.resolve({ ok: true, warnings: [], errors: [] }),
  ),
}));

vi.mock("@/lib/inputThresholds", () => ({
  checkKuroInputSize: vi.fn(() => ({ level: "ok", message: "", estimatedSeconds: 0 })),
  KURO_INPUT_THRESHOLDS: {},
}));

// useSidecar mock — default "ready"
const mockSidecarStatus = vi.fn(() => "ready");
vi.mock("@/hooks/useSidecar", () => ({
  useSidecar: vi.fn(() => ({ status: mockSidecarStatus(), retry: vi.fn() })),
}));

import { RunDesignAction } from "./RunDesignAction";

const singleGeneSeqInfo = {
  header: "test",
  seq_length: 100,
  genes: [{ gene: "gene1", product: "", cds_start: 0, cds_end: 100, aa_length: 33 }],
};

describe("RunDesignAction — missing fields", () => {
  beforeEach(() => {
    mockSidecarStatus.mockReturnValue("ready");
    useAppStore.setState({
      seqInfo: null,
      mutationText: "",
      selectedGene: "",
      isDesigning: false,
    });
  });

  it("1. Run button is disabled when missingFields present (no seqInfo)", () => {
    useAppStore.setState({ seqInfo: null, mutationText: "M1A" });
    render(<RunDesignAction />);
    const btn = screen.getByRole("button", { name: /run design/i });
    expect(btn.hasAttribute("disabled")).toBe(true);
  });

  it("2. Missing field list is rendered with role=alert when seqInfo absent", () => {
    useAppStore.setState({ seqInfo: null, mutationText: "M1A" });
    render(<RunDesignAction />);
    expect(screen.getByRole("alert")).toBeTruthy();
  });

  it("3. Run button enabled when all inputs present and sidecar ready", () => {
    mockSidecarStatus.mockReturnValue("ready");
    useAppStore.setState({
      seqInfo: singleGeneSeqInfo,
      mutationText: "M1A",
      selectedGene: "",
      isDesigning: false,
    });
    render(<RunDesignAction />);
    const btn = screen.getByRole("button", { name: /run design/i });
    expect(btn.hasAttribute("disabled")).toBe(false);
  });

  it("4. Cancel button appears while isDesigning", () => {
    useAppStore.setState({
      seqInfo: singleGeneSeqInfo,
      mutationText: "M1A",
      selectedGene: "",
      isDesigning: true,
    });
    render(<RunDesignAction />);
    expect(screen.getByRole("button", { name: /cancel/i })).toBeTruthy();
  });
});
