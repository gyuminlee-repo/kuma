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
import { ExportAction } from "./ExportAction";
import { useAppStore } from "@/store/appStore";
import { sendRequest } from "@/lib/ipc-kuro";

function ExportFormWithAction() {
  return <><ExportFormatSelector /><ExportAction /></>;
}

describe("ExportFormatSelector — Export All form", () => {
  beforeEach(() => {
    useAppStore.setState({
      designResults: [],
      echoRoundPicks: [],
      echoUsedQuadrants: [],
      // The form fields live in the store now; start each test from an empty form.
      exportName: "",
      exportPlateNames: {},
      exportAmount: "0.05",
      exportVectormaps: false,
    });
    toastWarning.mockClear();
  });

  it("keeps export actions outside the options form", () => {
    render(<ExportFormatSelector />);
    expect(screen.queryByRole("button", { name: /export/i })).toBeNull();
  });

  it("renders Echo volume range hint 25–500 nL", () => {
    render(<ExportFormWithAction />);
    expect(screen.getByText(/25.*500.*nL/)).toBeInTheDocument();
  });

  it("explains that both plate names are required", () => {
    render(<ExportFormWithAction />);
    expect(screen.getByText(/forward and reverse plate names are required/i)).toBeInTheDocument();
  });

  it("renders JANUS volume range hint 0.5–10 μL", () => {
    render(<ExportFormWithAction />);
    expect(screen.getByText(/0\.5.*10.*μL/)).toBeInTheDocument();
  });

  it("renders fixed Macrogen vendor without standalone order button", () => {
    render(<ExportFormWithAction />);
    // Vendor is fixed to Macrogen, shown as static text in the "Order Vendor"
    // group (not a selectable control); the standalone order button is gone.
    expect(screen.getByText(/Macrogen Plate Oligo/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /order primers/i })).not.toBeInTheDocument();
  });

  it("blocks Export with toast.warning when no design results", async () => {
    useAppStore.setState({ designResults: [] });
    render(<ExportFormWithAction />);
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
    render(<ExportFormWithAction />);
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
    render(<ExportFormWithAction />);
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
    render(<ExportFormWithAction />);
    expect(screen.getByText("50 wells")).toBeInTheDocument();
  });

  it("splits 193 results into three rounds instead of refusing them", () => {
    seedRounds(193);
    render(<ExportFormWithAction />);
    expect(screen.getByRole("button", { name: "Export round 3" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Export all" })).toBeNull();
    expect(screen.queryAllByRole("alert")).toHaveLength(0);
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

  it("shows each order plate's well count when 97 results require two rounds", () => {
    seedRounds(97);
    render(<ExportFormWithAction />);
    expect(screen.getByText("96 wells")).toBeInTheDocument();
    expect(screen.getByText("1 wells")).toBeInTheDocument();
  });

  // Past 96 the design is exported as rounds of one plate each, and the
  // operator picks each round's source plate and column parity; nothing is
  // assigned by round number.
  function seedRounds(n: number) {
    const results = Array.from({ length: n }, (_, i) => ({
      ...mkResult(`M${i + 1}A`),
      forward_seq: `F${i}`,
      reverse_seq: `R${i}`,
    }));
    const plateMappings = results.flatMap((r) => [
      { well: "", primer_name: `${r.mutation}_F`, sequence: r.forward_seq, primer_type: "forward" as const, mutation: r.mutation },
      { well: "", primer_name: `${r.mutation}_R`, sequence: r.reverse_seq, primer_type: "reverse" as const, mutation: r.mutation },
    ]);
    const dedupInfo = Object.fromEntries(results.map((r) => [r.reverse_seq, [r.mutation]]));
    useAppStore.setState({ designResults: results, plateMappings, dedupInfo, tableSorting: [] });
  }

  function pickRound(round: number, plate: number | null, parity: string | null) {
    if (plate !== null) {
      fireEvent.change(screen.getByLabelText(`Round ${round} source plate`), { target: { value: String(plate) } });
    }
    if (parity !== null) {
      fireEvent.change(screen.getByLabelText(`Round ${round} columns`), { target: { value: parity } });
    }
  }

  it("offers one export per round with no plate or parity chosen for either", () => {
    seedRounds(192);
    render(<ExportFormWithAction />);
    expect(screen.getByRole("button", { name: "Export round 1" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Export round 2" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Export all" })).toBeNull();
    expect(screen.queryAllByRole("alert")).toHaveLength(0);
    expect(screen.getByText("Round 2: wells 97-192")).toBeInTheDocument();
    expect((screen.getByLabelText("Round 2 source plate") as HTMLSelectElement).value).toBe("");
    expect((screen.getByLabelText("Round 2 columns") as HTMLSelectElement).value).toBe("");
    // A parity alone does not make a round ready: the plate has no default.
    pickRound(1, null, "A1");
    expect(screen.getByRole("button", { name: "Export round 1" })).toBeDisabled();
    pickRound(1, 1, null);
    expect(screen.getByRole("button", { name: "Export round 1" })).toBeEnabled();
  });

  it("exports a third round on a second source plate", async () => {
    seedRounds(193);
    const send = vi.mocked(sendRequest);
    send.mockClear();
    render(<ExportFormWithAction />);
    expect(screen.getByRole("button", { name: "Export round 3" })).toBeDisabled();
    const plateOptions = Array.from(
      (screen.getByLabelText("Round 3 source plate") as HTMLSelectElement).options,
    ).map((o) => o.value);
    expect(plateOptions).toEqual(["", "1", "2", "3"]);
    pickRound(1, 1, "A1");
    pickRound(3, 2, "A1");
    fireEvent.change(screen.getByLabelText("Forward primer plate name (R3)"), { target: { value: "F3" } });
    fireEvent.change(screen.getByLabelText("Reverse primer plate name (R3)"), { target: { value: "R3" } });
    fireEvent.click(screen.getByRole("button", { name: "Export round 3" }));
    await vi.waitFor(() => expect(send).toHaveBeenCalledWith("export_all", expect.anything()));
    const params = send.mock.calls.find((c) => c[0] === "export_all")![1] as {
      round_label: string;
      source_plate: number;
      quadrant: string;
      used_quadrants: string[];
      mappings: { well: string; primer_type: string }[];
    };
    expect(params.round_label).toBe("R3");
    expect(params.source_plate).toBe(2);
    expect(params.quadrant).toBe("A1");
    // Plate 2 is a new plate: round 1's A1 on plate 1 is not spent there.
    expect(params.used_quadrants).toEqual([]);
    expect(params.mappings.filter((m) => m.primer_type === "forward")).toEqual([
      expect.objectContaining({ well: "A1" }),
    ]);
  });

  it("refuses the same plate and parity on two rounds whichever is picked first", () => {
    seedRounds(192);
    render(<ExportFormWithAction />);
    pickRound(2, 1, "A1");
    pickRound(1, 1, null);
    const r1 = screen.getByLabelText("Round 1 columns") as HTMLSelectElement;
    expect(Array.from(r1.options).find((o) => o.value === "A1")!.disabled).toBe(true);
    // Moving round 1 to plate 2 frees A1 for it.
    pickRound(1, 2, null);
    expect(Array.from(r1.options).find((o) => o.value === "A1")!.disabled).toBe(false);
    pickRound(1, null, "A1");
    expect(screen.getByRole("button", { name: "Export round 1" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Export round 2" })).toBeEnabled();
  });

  it("does not send a saved plate past the plates offered for this many rounds", () => {
    // Saved when the design had five rounds; it now has three, so plate 5 is
    // not an option and the select shows nothing. The value must not survive
    // unseen into the export.
    seedRounds(193);
    useAppStore.setState({ echoRoundPicks: [{ plate: 5, quadrant: "A1" }] });
    render(<ExportFormWithAction />);
    expect((screen.getByLabelText("Round 1 source plate") as HTMLSelectElement).value).toBe("");
    expect(screen.getByRole("button", { name: "Export round 1" })).toBeDisabled();
    expect(useAppStore.getState().echoRoundPicks[0]).toEqual({ plate: null, quadrant: null });
  });

  it("applies the parities marked as spent to plate 1 only", () => {
    seedRounds(193);
    render(<ExportFormWithAction />);
    fireEvent.click(screen.getByRole("checkbox", { name: "A1" }));
    pickRound(1, 1, null);
    pickRound(3, 2, null);
    const r1 = screen.getByLabelText("Round 1 columns") as HTMLSelectElement;
    const r3 = screen.getByLabelText("Round 3 columns") as HTMLSelectElement;
    expect(Array.from(r1.options).find((o) => o.value === "A1")!.disabled).toBe(true);
    expect(Array.from(r3.options).find((o) => o.value === "A1")!.disabled).toBe(false);
  });

  it("sends round 2 on the other parity with round 1's pick as spent", async () => {
    seedRounds(192);
    const send = vi.mocked(sendRequest);
    send.mockClear();
    render(<ExportFormWithAction />);
    pickRound(1, 1, "A2");
    pickRound(2, 1, null);
    const r2 = screen.getByLabelText("Round 2 columns") as HTMLSelectElement;
    const a2Option = Array.from(r2.options).find((o) => o.value === "A2")!;
    expect(a2Option.disabled).toBe(true);
    fireEvent.change(r2, { target: { value: "A1" } });
    fireEvent.change(screen.getByLabelText("Forward primer plate name (R2)"), { target: { value: "F2" } });
    fireEvent.change(screen.getByLabelText("Reverse primer plate name (R2)"), { target: { value: "R2" } });
    fireEvent.click(screen.getByRole("button", { name: "Export round 2" }));
    await vi.waitFor(() => expect(send).toHaveBeenCalledWith("export_all", expect.anything()));
    const params = send.mock.calls.find((c) => c[0] === "export_all")![1] as {
      round_label: string;
      quadrant: string;
      used_quadrants: string[];
      mappings: { well: string; primer_type: string }[];
    };
    expect(params.round_label).toBe("R2");
    expect((params as unknown as { source_plate: number }).source_plate).toBe(1);
    expect(params.quadrant).toBe("A1");
    expect(params.used_quadrants).toEqual(["A2"]);
    const fwd = params.mappings.filter((m) => m.primer_type === "forward");
    expect(fwd).toHaveLength(96);
    expect(params.mappings.some((m) => m.well.startsWith("P2-"))).toBe(false);
  });

  it("keeps each round's order names independent and requires names for the exported round", async () => {
    seedRounds(192);
    const send = vi.mocked(sendRequest);
    send.mockClear();
    render(<ExportFormWithAction />);
    pickRound(1, 1, "A1");
    pickRound(2, 1, "A2");
    fireEvent.change(screen.getByLabelText("Forward primer plate name (R1)"), { target: { value: "Batch1_F" } });
    fireEvent.change(screen.getByLabelText("Reverse primer plate name (R1)"), { target: { value: "Batch1_R" } });
    fireEvent.click(screen.getByRole("button", { name: "Export round 2" }));
    expect(toastWarning).toHaveBeenCalled();
    expect(send).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("Forward primer plate name (R2)"), { target: { value: "Batch2_F" } });
    fireEvent.change(screen.getByLabelText("Reverse primer plate name (R2)"), { target: { value: "Batch2_R" } });
    fireEvent.click(screen.getByRole("button", { name: "Export round 1" }));
    await vi.waitFor(() => expect(send).toHaveBeenCalledWith("export_all", expect.objectContaining({
      round_label: "R1", fwd_plate_name: "Batch1_F", rev_plate_name: "Batch1_R",
    })));
    await vi.waitFor(() => expect(screen.getByRole("button", { name: "Export round 2" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "Export round 2" }));
    await vi.waitFor(() => expect(send).toHaveBeenCalledWith("export_all", expect.objectContaining({
      round_label: "R2", fwd_plate_name: "Batch2_F", rev_plate_name: "Batch2_R",
    })));
    expect(screen.getByLabelText("Forward primer plate name (R1)")).toHaveValue("Batch1_F");
  });
});
