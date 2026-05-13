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

import { ExportFormatSelector } from "./ExportFormatSelector";
import { useAppStore } from "@/store/appStore";

describe("ExportFormatSelector — Export All form", () => {
  beforeEach(() => {
    useAppStore.setState({ designResults: [] });
  });

  it("renders Echo volume range hint 25–500 nL", () => {
    render(<ExportFormatSelector />);
    expect(screen.getByText(/25.*500.*nL/)).toBeInTheDocument();
  });

  it("renders JANUS volume range hint 0.5–10 μL", () => {
    render(<ExportFormatSelector />);
    expect(screen.getByText(/0\.5.*10.*μL/)).toBeInTheDocument();
  });

  it("disables Export button when no design results", () => {
    useAppStore.setState({ designResults: [] });
    render(<ExportFormatSelector />);
    const btn = screen.getByRole("button");
    expect(btn).toBeDisabled();
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

  it("disables Export button and shows error when forward plate name contains invalid chars", () => {
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
    const btn = screen.getByRole("button");
    expect(btn).toBeDisabled();
    // error alert should be present
    expect(screen.getAllByRole("alert").length).toBeGreaterThan(0);
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
    expect(screen.getByText(/50/)).toBeInTheDocument();
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
});
