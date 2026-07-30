import { act, cleanup, render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ProjectProvider } from "@/state/projectContext";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import type { VerdictRecord } from "@/types/mame/models";
import { useMameAutosave } from "./useMameAutosave";

const autosaveMocks = vi.hoisted(() => ({
  scheduleAutosave: vi.fn(),
  flushAutosave: vi.fn(() => Promise.resolve()),
}));

vi.mock("@/lib/autosave", () => ({
  scheduleAutosave: autosaveMocks.scheduleAutosave,
  flushAutosave: autosaveMocks.flushAutosave,
}));

let latestFlush: (() => Promise<void>) | null = null;

const verdict: VerdictRecord = {
  native_barcode: "barcode1",
  custom_barcode: "1_1",
  file_size_kb: 120,
  read_count: 160,
  n_mixed_positions: 0,
  max_minor_allele_fraction: 0,
  n_low_depth_positions: 0,
  consensus_n_fraction: 0,
  n_low_quality_bases: 0,
  n_input_reads: 160,
  n_aligned_reads: 155,
  n_mapq_failed: 0,
  n_span_failed: 0,
  source_path: "/mock/NB01/1_1.fasta",
  aa_sequence: "MSTTS",
  observed_nt_changes: [],
  n_no_call_aa: 0,
  observed_aa_changes: ["V5F"],
  expected_mutations: ["V5F"],
  mutant_id: "V5F",
  verdict: "PASS",
  verdict_notes: "",
};

function Harness() {
  const { flushMameAutosave } = useMameAutosave();
  latestFlush = flushMameAutosave;
  return null;
}

describe("useMameAutosave", () => {
  beforeEach(() => {
    latestFlush = null;
    autosaveMocks.scheduleAutosave.mockClear();
    autosaveMocks.flushAutosave.mockClear();
    useMameAppStore.getState().resetInput();
  });

  afterEach(() => {
    cleanup();
  });

  it("schedules mame autosave when persisted input fields change", async () => {
    render(
      <ProjectProvider value={{ path: "/tmp/kuma-project", name: "Demo", scratch: false }}>
        <Harness />
      </ProjectProvider>,
    );

    act(() => {
      useMameAppStore.getState().setInputDir("/runs/2026-05-26");
    });

    await waitFor(() => {
      expect(autosaveMocks.scheduleAutosave).toHaveBeenCalledTimes(1);
    });
    expect(autosaveMocks.scheduleAutosave).toHaveBeenCalledWith(
      expect.objectContaining({ projectPath: "/tmp/kuma-project", scratch: false }),
      "mame",
      expect.any(Function),
    );
  });

  it("schedules mame autosave when persisted result fields change", async () => {
    render(
      <ProjectProvider value={{ path: "/tmp/kuma-project", name: "Demo", scratch: false }}>
        <Harness />
      </ProjectProvider>,
    );

    act(() => {
      useMameAppStore.getState().setVerdicts([verdict]);
    });

    await waitFor(() => {
      expect(autosaveMocks.scheduleAutosave).toHaveBeenCalledTimes(1);
    });
    expect(autosaveMocks.scheduleAutosave).toHaveBeenCalledWith(
      expect.objectContaining({ projectPath: "/tmp/kuma-project", scratch: false }),
      "mame",
      expect.any(Function),
    );
  });

  it("skips scheduling for scratch projects", async () => {
    render(
      <ProjectProvider value={{ path: "/tmp/kuma-scratch", name: "Scratch", scratch: true }}>
        <Harness />
      </ProjectProvider>,
    );

    act(() => {
      useMameAppStore.getState().setInputDir("/runs/scratch");
    });

    await Promise.resolve();
    expect(autosaveMocks.scheduleAutosave).not.toHaveBeenCalled();
  });

  it("flushes the current mame autosave target", async () => {
    render(
      <ProjectProvider value={{ path: "/tmp/kuma-project", name: "Demo", scratch: false }}>
        <Harness />
      </ProjectProvider>,
    );

    if (latestFlush === null) {
      throw new Error("flush callback was not registered");
    }

    await act(async () => {
      await latestFlush?.();
    });

    expect(autosaveMocks.flushAutosave).toHaveBeenCalledWith(
      expect.objectContaining({ projectPath: "/tmp/kuma-project", scratch: false }),
      "mame",
    );
  });
});
