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
import { getMameRpcResultValidator } from "@/types/mame/validators";
import type { Round } from "@/types/round";
import {
  PositiveJanusPanel,
  positiveJanusCandidatesDigest,
  positiveJanusSignature,
} from "./PositiveJanusPanel";

const SOURCES = { round1_report_xlsx: "/p/round1.xlsx", layout_xlsx: "/p/layout.xlsx" };

const CANDIDATES: PositiveJanusCandidatesResult = {
  candidates: [
    { well: "F1", name: "K10R", relative: 1.05, n_replicates: 1, above_wt: true },
    { well: "D2", name: "K12R", relative: 1.14, n_replicates: 1, above_wt: true },
    { well: "E3", name: "K14R", relative: 0.98, n_replicates: 1, above_wt: false },
  ],
  n_above_wt: 2,
  warnings: [],
  excluded_rows: [],
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
  it("names the rows the screen set aside under the build's warnings heading", async () => {
    const blank = "round1_report_xlsx excluded 1 row(s) (non_well_sample): 'BLANK' (block 1, row 3)";
    vi.mocked(positiveJanusCandidates).mockResolvedValue({
      ...CANDIDATES,
      warnings: [blank],
      excluded_rows: [{
        source: "round1_report_xlsx", sample_name: "BLANK", reason: "non_well_sample",
        row_index: 3, block_index: 1, area: 0.33, kept: false,
      }],
    });
    renderPanel();
    fireEvent.click(screen.getByRole("button", { name: "Find positive clones" }));
    await waitFor(() => expect(screen.getByText(blank)).toBeTruthy());
    expect(screen.getByText("Warnings")).toBeTruthy();
  });

  it("validates the excluded rows of the candidates response", () => {
    const validate = getMameRpcResultValidator("mame.activity.positive_janus_candidates");
    expect(validate).toBeTruthy();
    const row = {
      source: "round1_report_xlsx", sample_name: "BLANK", reason: "non_well_sample",
      row_index: 3, block_index: 1, area: null, kept: false,
    };
    expect(validate?.({ ...CANDIDATES, excluded_rows: [row] })).toBe(true);
    const { excluded_rows: _dropped, ...withoutRows } = CANDIDATES;
    expect(validate?.(withoutRows)).toBe(false);
    expect(validate?.({ ...CANDIDATES, excluded_rows: [{ ...row, reason: 1 }] })).toBe(false);
  });

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
      candidates_digest: positiveJanusCandidatesDigest(CANDIDATES),
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
        candidates_digest: positiveJanusCandidatesDigest(CANDIDATES),
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

  it("retires a stored selection when the same path now reads differently", async () => {
    seedRound({
      positive_janus: {
        input_signature: positiveJanusSignature(SOURCES),
        // Made when E3 was the only clone above WT, before the file was overwritten.
        candidates_digest: "F1:0,D2:0,E3:1",
        selected_wells: ["E3"],
        volume: 60,
        source_rack: "stock",
        dest_rack: "dw",
      },
    });
    renderPanel();
    fireEvent.click(screen.getByRole("button", { name: "Find positive clones" }));
    await waitFor(() => expect(screen.getByLabelText(/F1/)).toBeTruthy());
    expect((screen.getByLabelText(/F1/) as HTMLInputElement).checked).toBe(true);
    expect((screen.getByLabelText(/E3/) as HTMLInputElement).checked).toBe(false);
    expect((screen.getByLabelText("Volume (µL)") as HTMLInputElement).value).toBe("70");
    expect(record()).toBeNull();
    expect(screen.getByRole("alert").textContent).toMatch(/reads differently/);
  });

  it("reads the screen again before exporting and stops when it changed", async () => {
    vi.mocked(save).mockResolvedValue("/p/activity/positive.csv");
    renderPanel();
    fireEvent.click(screen.getByRole("button", { name: "Find positive clones" }));
    await waitFor(() => expect(screen.getByLabelText(/E3/)).toBeTruthy());
    fireEvent.click(screen.getByLabelText(/E3/));
    expect(record()?.selected_wells).toEqual(["F1", "D2", "E3"]);

    // Overwritten in place: D2 is no longer above WT.
    const changed: PositiveJanusCandidatesResult = {
      ...CANDIDATES,
      candidates: CANDIDATES.candidates.map((c) =>
        c.well === "D2" ? { ...c, relative: 0.9, above_wt: false } : c,
      ),
      n_above_wt: 1,
    };
    vi.mocked(positiveJanusCandidates).mockResolvedValue(changed);
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Export JANUS mapping" }));
    });
    await waitFor(() => expect(screen.getByRole("alert")).toBeTruthy());
    expect(exportPositiveJanus).not.toHaveBeenCalled();
    expect(record()).toBeNull();
    expect((screen.getByLabelText(/D2/) as HTMLInputElement).checked).toBe(false);
    expect((screen.getByLabelText(/E3/) as HTMLInputElement).checked).toBe(false);
    expect((screen.getByLabelText(/F1/) as HTMLInputElement).checked).toBe(true);
  });

  it("clears the written notice when the inputs change", async () => {
    vi.mocked(save).mockResolvedValue("/p/activity/positive.csv");
    vi.mocked(exportPositiveJanus).mockResolvedValue({
      output_path: "/p/activity/positive.csv",
      row_count: 2,
      rows: [{}, {}],
    });
    const { rerender } = renderPanel();
    fireEvent.click(screen.getByRole("button", { name: "Find positive clones" }));
    await waitFor(() => expect(screen.getByLabelText(/F1/)).toBeTruthy());
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Export JANUS mapping" }));
    });
    await waitFor(() => expect(screen.getByText(/Wrote 2 transfers/)).toBeTruthy());

    rerender(
      <PositiveJanusPanel
        sources={{ ...SOURCES, layout_xlsx: "/p/layout2.xlsx" }}
        roundId="r1"
        roundNumber={1}
        defaultFolder="/p/activity"
      />,
    );
    expect(screen.queryByText(/Wrote 2 transfers/)).toBeNull();
  });

  it.each(["0", "", "-5", "abc"])(
    "disables export and says why when the volume reads %j, even after blur",
    async (typed) => {
      renderPanel();
      fireEvent.click(screen.getByRole("button", { name: "Find positive clones" }));
      await waitFor(() => expect(screen.getByLabelText(/F1/)).toBeTruthy());
      const field = screen.getByLabelText("Volume (µL)") as HTMLInputElement;
      fireEvent.change(field, { target: { value: "55" } });
      fireEvent.change(field, { target: { value: typed } });
      fireEvent.blur(field);
      // What the field shows is what an export would send, so it is not reverted.
      expect(field.value).toBe(typed === "abc" ? "" : typed);
      expect(
        (screen.getByRole("button", { name: "Export JANUS mapping" }) as HTMLButtonElement).disabled,
      ).toBe(true);
      expect(screen.getByRole("alert").textContent).toMatch(/positive number/);
      expect(field.getAttribute("aria-invalid")).toBe("true");
    },
  );

  it("sends the volume the field shows", async () => {
    vi.mocked(save).mockResolvedValue("/p/activity/positive.csv");
    vi.mocked(exportPositiveJanus).mockResolvedValue({
      output_path: "/p/activity/positive.csv", row_count: 2, rows: [{}, {}],
    });
    renderPanel();
    fireEvent.click(screen.getByRole("button", { name: "Find positive clones" }));
    await waitFor(() => expect(screen.getByLabelText(/F1/)).toBeTruthy());
    const field = screen.getByLabelText("Volume (µL)") as HTMLInputElement;
    fireEvent.change(field, { target: { value: "0" } });
    fireEvent.change(field, { target: { value: "42.5" } });
    fireEvent.blur(field);
    expect(field.value).toBe("42.5");
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Export JANUS mapping" }));
    });
    await waitFor(() => expect(exportPositiveJanus).toHaveBeenCalled());
    expect(vi.mocked(exportPositiveJanus).mock.calls[0]?.[0].volume).toBe(42.5);
  });
});
