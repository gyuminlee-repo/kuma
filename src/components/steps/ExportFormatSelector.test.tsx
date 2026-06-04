/**
 * ExportFormatSelector.test.tsx — Export All form 단위 테스트
 *
 * [source: plan A7 Step 2]
 *
 * vitest + @testing-library/react. worktree 환경에 node_modules 없으므로
 * 실행은 메인 repo merge 후 `pnpm vitest run` 으로 수행.
 */

import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

// Tauri shell 플러그인 mock
vi.mock("@tauri-apps/plugin-dialog", () => ({
  open: vi.fn().mockResolvedValue("/tmp/output"),
}));

vi.mock("@/lib/ipc-kuro", () => ({
  sendRequest: vi.fn().mockResolvedValue({ success: ["a.csv"], failed: [], output_dir: "/tmp/output" }),
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
}));

vi.mock("@/state/projectContext", () => ({
  useKumaProject: vi.fn().mockReturnValue({ project_id: "test-proj" }),
}));

const toastWarning = vi.fn();
vi.mock("sonner", () => ({
  toast: {
    warning: (...args: unknown[]) => toastWarning(...args),
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
  },
}));

import { ExportFormatSelector } from "./ExportFormatSelector";
import { useAppStore } from "@/store/appStore";

describe("ExportFormatSelector — Export All form", () => {
  beforeEach(() => {
    useAppStore.setState({ designResults: [] });
    toastWarning.mockClear();
  });

  it("renders Echo volume range hint 25–500 nL", () => {
    render(<ExportFormatSelector />);
    expect(screen.getByText(/25.*500.*nL/)).toBeInTheDocument();
  });

  it("renders JANUS volume range hint 0.5–10 μL", () => {
    render(<ExportFormatSelector />);
    expect(screen.getByText(/0\.5.*10.*μL/)).toBeInTheDocument();
  });

  it("renders vendor selection without standalone Macrogen order button", () => {
    render(<ExportFormatSelector />);
    expect(screen.getByLabelText(/order vendor/i)).toHaveValue("macrogen");
    expect(screen.queryByRole("button", { name: /order primers/i })).not.toBeInTheDocument();
  });

  it("blocks Export with toast.warning when no design results", async () => {
    useAppStore.setState({ designResults: [] });
    render(<ExportFormatSelector />);
    const btn = screen.getByRole("button");
    // PI 2026-05-15 (Item 2): button stays clickable so the warning toast can fire.
    expect(btn).not.toBeDisabled();
    fireEvent.click(btn);
    await Promise.resolve();
    expect(toastWarning).toHaveBeenCalled();
  });

  it("enables Export button when design results exist and plate names are valid", () => {
    useAppStore.setState({
      designResults: Array(3).fill({
        mutation: "A1V",
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
      }),
    });
    render(<ExportFormatSelector />);
    const btn = screen.getByRole("button");
    expect(btn).not.toBeDisabled();
  });

  it("flags invalid forward plate name with destructive border and blocks Export via toast.warning", async () => {
    useAppStore.setState({
      designResults: Array(1).fill({
        mutation: "A1V",
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
      }),
    });
    render(<ExportFormatSelector />);
    const fwdInput = screen.getByLabelText(/forward primer plate name/i);
    fireEvent.change(fwdInput, { target: { value: "한글이름" } });
    // PI 2026-05-15 (Item 2): visual error via border-destructive, button stays clickable.
    expect(fwdInput.className).toMatch(/border-destructive/);
    const btn = screen.getByRole("button");
    expect(btn).not.toBeDisabled();
    fireEvent.click(btn);
    await Promise.resolve();
    expect(toastWarning).toHaveBeenCalled();
  });

  it("shows well count in forward plate description area", () => {
    useAppStore.setState({
      designResults: Array(50).fill({
        mutation: "A1V",
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
      }),
    });
    render(<ExportFormatSelector />);
    expect(screen.getByText("50 wells")).toBeInTheDocument();
  });

  it("disables Export button and shows overflow error when well count > 96", () => {
    useAppStore.setState({
      designResults: Array(97).fill({
        mutation: "A1V",
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
      }),
    });
    render(<ExportFormatSelector />);
    const btn = screen.getByRole("button");
    expect(btn).toBeDisabled();
    expect(screen.getAllByRole("alert").length).toBeGreaterThan(0);
  });

  const mkResult = (mutation: string) => ({
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
    penalty: 0,
    gc_fwd: 50,
    gc_rev: 50,
    wt_codon: "ATG",
    mt_codon: "GTG",
    overlap_seq: "ATCG",
    warnings: [] as string[],
  });

  it("excluded rows do not count toward the 96-well overflow gate", () => {
    const results = Array.from({ length: 97 }, (_, i) => mkResult(`M${i}A`));
    useAppStore.setState({ designResults: results, excludedDesignMutations: ["M0A", "M1A"] });
    render(<ExportFormatSelector />);
    const btn = screen.getByRole("button");
    expect(btn).not.toBeDisabled();               // 95 included <= 96
    expect(screen.queryByText(/exceed one 96-well plate/i)).toBeNull();
    expect(screen.getByText("95 wells")).toBeInTheDocument();
  });
});
