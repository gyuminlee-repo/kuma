import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useRoundStore } from "@/store/round/roundSlice";

const mockMkdir = vi.hoisted(() => vi.fn());
vi.mock("@tauri-apps/plugin-dialog", () => ({ open: vi.fn(), save: vi.fn() }));
vi.mock("@tauri-apps/plugin-fs", () => ({ mkdir: mockMkdir }));
vi.mock("@/lib/ipc-mame", () => ({
  positiveJanusCandidates: vi.fn(),
  exportPositiveJanus: vi.fn(),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { save } from "@tauri-apps/plugin-dialog";
import { exportPositiveJanus, positiveJanusCandidates } from "@/lib/ipc-mame";
import type { PositiveJanusCandidatesResult } from "@/types/mame/positive_janus";
import type { Round } from "@/types/round";
import { PositiveJanusPanel, positiveJanusSignature } from "./PositiveJanusPanel";

const SOURCES = { round1_report_xlsx: "/p/round1.xlsx", layout_xlsx: "/p/layout.xlsx" };

const CANDIDATES: PositiveJanusCandidatesResult = {
  candidates: [
    { well: "F1", name: "K10R", relative: 1.05, n_replicates: 1, above_wt: true },
    { well: "D2", name: "K12R", relative: 1.14, n_replicates: 1, above_wt: true },
    { well: "E3", name: "K14R", relative: 0.98, n_replicates: 1, above_wt: false },
  ],
  n_above_wt: 2,
  warnings: [],
  defaults: {
    volume: 70,
    source_rack: "final cell stock",
    dest_rack: "deep well plate",
    sample_type: "cell stock",
  },
};

function seedRound(extra: Partial<Round> = {}) {
  useRoundStore.setState({
    rounds: [
      {
        id: "r1",
        n: 1,
        created_at: "2026-10-29T00:00:00Z",
        status: "design",
        error_info: null,
        plate_meta: { plates: [] },
        design: {},
        genotype: {},
        activity: null,
        merged_table: [],
        ...extra,
      } as Round,
    ],
    active_round_id: "r1",
  });
}

function renderPanel(sources: typeof SOURCES | null = SOURCES) {
  return render(
    <PositiveJanusPanel sources={sources} roundId="r1" roundNumber={1} defaultFolder="/p/activity" />,
  );
}

function record() {
  return useRoundStore.getState().rounds[0]?.positive_janus ?? null;
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  seedRound();
  vi.mocked(positiveJanusCandidates).mockResolvedValue(CANDIDATES);
});

describe("PositiveJanusPanel", () => {
  it("asks for a plate-addressed screen when the form holds none", () => {
    renderPanel(null);
    expect(screen.queryByRole("button", { name: "Find positive clones" })).toBeNull();
    expect(positiveJanusCandidates).not.toHaveBeenCalled();
  });

  it("checks the above-WT clones first and shows the backend defaults", async () => {
    renderPanel();
    fireEvent.click(screen.getByRole("button", { name: "Find positive clones" }));
    await waitFor(() => expect(screen.getByLabelText(/F1/)).toBeTruthy());
    expect(positiveJanusCandidates).toHaveBeenCalledWith(SOURCES);
    expect((screen.getByLabelText(/F1/) as HTMLInputElement).checked).toBe(true);
    expect((screen.getByLabelText(/D2/) as HTMLInputElement).checked).toBe(true);
    expect((screen.getByLabelText(/E3/) as HTMLInputElement).checked).toBe(false);
    expect((screen.getByLabelText("Volume (µL)") as HTMLInputElement).value).toBe("70");
    expect((screen.getByLabelText("Source plate name") as HTMLInputElement).value).toBe("final cell stock");
    expect((screen.getByLabelText("Destination plate name") as HTMLInputElement).value).toBe("deep well plate");
    // Nothing is stored until the operator changes something.
    expect(record()).toBeNull();
  });

  it("keeps an adjusted selection on the round and exports it", async () => {
    vi.mocked(save).mockResolvedValue("/p/activity/positive.csv");
    vi.mocked(exportPositiveJanus).mockResolvedValue({
      output_path: "/p/activity/positive.csv",
      row_count: 2,
      rows: [{}, {}],
    });
    renderPanel();
    fireEvent.click(screen.getByRole("button", { name: "Find positive clones" }));
    await waitFor(() => expect(screen.getByLabelText(/E3/)).toBeTruthy());

    fireEvent.click(screen.getByLabelText(/D2/));
    fireEvent.click(screen.getByLabelText(/E3/));
    fireEvent.change(screen.getByLabelText("Volume (µL)"), { target: { value: "50" } });

    expect(record()).toEqual({
      input_signature: positiveJanusSignature(SOURCES),
      selected_wells: ["F1", "E3"],
      volume: 50,
      source_rack: "final cell stock",
      dest_rack: "deep well plate",
    });

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Export JANUS mapping" }));
    });
    await waitFor(() => expect(exportPositiveJanus).toHaveBeenCalled());
    expect(vi.mocked(exportPositiveJanus).mock.calls[0]?.[0]).toEqual({
      ...SOURCES,
      selected_wells: ["F1", "E3"],
      volume: 50,
      source_rack: "final cell stock",
      dest_rack: "deep well plate",
      output_csv: "/p/activity/positive.csv",
    });
    expect(mockMkdir).toHaveBeenCalledWith("/p/activity", { recursive: true });
  });

  it("restores a stored selection for the same files and ignores one for other files", async () => {
    seedRound({
      positive_janus: {
        input_signature: positiveJanusSignature(SOURCES),
        selected_wells: ["E3"],
        volume: 60,
        source_rack: "stock",
        dest_rack: "dw",
      },
    });
    const { unmount } = renderPanel();
    fireEvent.click(screen.getByRole("button", { name: "Find positive clones" }));
    await waitFor(() => expect(screen.getByLabelText(/E3/)).toBeTruthy());
    expect((screen.getByLabelText(/E3/) as HTMLInputElement).checked).toBe(true);
    expect((screen.getByLabelText(/F1/) as HTMLInputElement).checked).toBe(false);
    expect((screen.getByLabelText("Volume (µL)") as HTMLInputElement).value).toBe("60");
    unmount();

    const other = { ...SOURCES, round1_report_xlsx: "/p/other.xlsx" };
    render(<PositiveJanusPanel sources={other} roundId="r1" roundNumber={1} defaultFolder={null} />);
    fireEvent.click(screen.getByRole("button", { name: "Find positive clones" }));
    await waitFor(() => expect(screen.getByLabelText(/F1/)).toBeTruthy());
    expect((screen.getByLabelText(/F1/) as HTMLInputElement).checked).toBe(true);
    expect((screen.getByLabelText(/E3/) as HTMLInputElement).checked).toBe(false);
  });

  it("does not export with nothing selected", async () => {
    renderPanel();
    fireEvent.click(screen.getByRole("button", { name: "Find positive clones" }));
    await waitFor(() => expect(screen.getByLabelText(/F1/)).toBeTruthy());
    fireEvent.click(screen.getByLabelText(/F1/));
    fireEvent.click(screen.getByLabelText(/D2/));
    expect(
      (screen.getByRole("button", { name: "Export JANUS mapping" }) as HTMLButtonElement).disabled,
    ).toBe(true);
  });
});
