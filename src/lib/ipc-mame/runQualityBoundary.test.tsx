import { fireEvent, render, screen, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AnalyzeResult } from "@/types/mame/models";
import { RunQcSection } from "@/components/mame/widgets/RunQcSection";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import en from "@/locales/en.json";
import { runQualityFixture } from "@/test-utils/runQualityFixture";

const boundary = vi.hoisted(() => ({ rpc: vi.fn(), read: vi.fn() }));
vi.mock("../ipc", () => ({ rawSidecarRpc: boundary.rpc, killSidecar: vi.fn() }));
vi.mock("@tauri-apps/plugin-fs", () => ({
  exists: async () => true, readTextFile: boundary.read, rename: vi.fn(),
}));
import { sendRequest } from "./index";
import { readMameResultSnapshot } from "@/lib/mame/resultSnapshot";

const quality = {
  severity: null, median_well_reads: 500, min_read_count: 100, depth_ok: true,
  wells_under_floor: 0, wells_total: 96, recommended_reads: 1000,
  flow_cell_id: null, pore_start: null, pore_end: null, pore_warranty_min: 800,
  reused_from: null, thresholds: {}, findings: [],
};
afterEach(() => { cleanup(); useMameAppStore.setState({ runQuality: null }); });

describe("run quality trust boundaries", () => {
  const malformed: readonly unknown[] = [
    null, [], "quality", {},
    { ...quality, findings: [null] },
    { ...quality, thresholds: [] },
    { ...quality, thresholds: { floor: { source: "ONT", kind: "vendor_default", value: "100" } } },
    { ...runQualityFixture, position_recurrence: [] },
    { ...runQualityFixture, position_recurrence: { ...runQualityFixture.position_recurrence, positions: {} } },
    { ...runQualityFixture, position_recurrence: { ...runQualityFixture.position_recurrence, positions: [null] } },
    { ...runQualityFixture, position_recurrence: { ...runQualityFixture.position_recurrence, strand_information: "invalid" } },
    { ...runQualityFixture, position_recurrence: { ...runQualityFixture.position_recurrence,
      positions: [{ ...runQualityFixture.position_recurrence.positions[0], recurrence_rate: "0.2" }] } },
    { ...runQualityFixture, indel_recurrence: { ...runQualityFixture.indel_recurrence, deletions: [null] } },
    { ...runQualityFixture, indel_recurrence: { ...runQualityFixture.indel_recurrence,
      insertions: [{ anchor: 900, wells: 2, expected_variants: 1, distinct_sequences: "1" }] } },
    { ...runQualityFixture, read_length: { ...runQualityFixture.read_length, histograms: [null] } },
    { ...runQualityFixture, read_length: { ...runQualityFixture.read_length, qscore_histograms: {} } },
    { ...runQualityFixture, read_length: { ...runQualityFixture.read_length,
      histograms: [{ ...runQualityFixture.read_length.histograms[0], plot: { bucket_starts: [0], bucket_ends: [1], bucket_values: ["bad"], total: 1 } }] } },
    { ...runQualityFixture, read_length: { ...runQualityFixture.read_length,
      qscore_histograms: [{ bucket_value_type: null, bucket_starts: [0], bucket_ends: [1], series: [null] }] } },
    { ...runQualityFixture, read_length: { ...runQualityFixture.read_length, provenance: { n50: null } } },
  ];
  it.each(malformed.map((value, index) => ({ value, index })))("rejects malformed nested shape $index at both boundaries", async ({ value }) => {
    boundary.rpc.mockResolvedValue({ run_quality: value });
    boundary.read.mockResolvedValue(JSON.stringify({ schema: 1, result: { run_quality: value } }));
    await expect(sendRequest("analyze")).rejects.toThrow(/Invalid RPC result shape/);
    expect(await readMameResultSnapshot("/project")).toEqual({ status: "missing" });
  });
  it.each([Number.NaN, Infinity, -Infinity])("rejects nonfinite measurements %s from RPC", async (value) => {
    boundary.rpc.mockResolvedValue({ run_quality: { ...runQualityFixture, read_length: {
      ...runQualityFixture.read_length, reference_length_bp: value,
    } } });
    await expect(sendRequest("analyze")).rejects.toThrow(/Invalid RPC result shape/);
  });
  it.each([
    {}, { run_quality: quality }, { run_quality: runQualityFixture },
    { run_quality: { ...runQualityFixture, thresholds: { floor: { value: null, source: "ONT", kind: "vendor_default" } },
      findings: [{ code: "mixed_depth_factor_amplicon_scale", severity: "warning", ratio: 2 }] } },
    { run_quality: { ...runQualityFixture, read_length: { ...runQualityFixture.read_length, histograms: null, qscore_histograms: null } } },
  ])("preserves valid and legacy payloads verbatim %#", async (result) => {
    boundary.rpc.mockResolvedValue(result);
    boundary.read.mockResolvedValue(JSON.stringify({ schema: 1, result }));
    expect(await sendRequest("analyze")).toBe(result);
    expect(await readMameResultSnapshot("/project")).toEqual({ status: "ok", snapshot: { schema: 1, result } });
  });
  it("refuses a malformed load acknowledgement", async () => {
    boundary.rpc.mockResolvedValue({ restored: true, verdict_count: "1", replicate_count: 0 });
    await expect(sendRequest("load_analyze_result")).rejects.toThrow(/Invalid RPC result shape/);
  });
  it("accepts the sidecar load acknowledgement", async () => {
    const ack = { restored: true, verdict_count: 1, replicate_count: 0 };
    boundary.rpc.mockResolvedValue(ack);
    expect(await sendRequest("load_analyze_result")).toBe(ack);
  });
  it.each([undefined, null, 0, 3])("preserves deletion metadata and strict subset %s in verdicts and replicates", async (subset) => {
    const verdict = {
      n_no_call_zero_depth: 0, n_no_call_deletion: 3,
      n_no_call_ambiguous: 0, n_no_call_no_majority: 0,
      ...(subset === undefined ? {} : { n_no_call_deletion_majority: subset }),
    };
    const result = { run_quality: runQualityFixture, verdicts: [verdict],
      replicates: [{ plate_verdicts: { barcode01: verdict } }],
    };
    boundary.rpc.mockResolvedValue(result);
    boundary.read.mockResolvedValue(JSON.stringify({ schema: 1, result }));
    expect(await sendRequest("analyze")).toBe(result);
    expect(await readMameResultSnapshot("/project")).toEqual({ status: "ok", snapshot: { schema: 1, result } });
  });
  it("rejects raw-run analyze before assigning run quality", async () => {
    boundary.rpc.mockResolvedValue({ run_quality: { ...quality, read_length: null } });
    await expect(useMameAppStore.getState()._demuxAndAnalyze(null)).rejects.toThrow(/Invalid RPC result shape/);
    expect(useMameAppStore.getState().runQuality).toBeNull();
  });
  it("reports non-raw analyze failure without assigning run quality", async () => {
    useMameAppStore.setState({ inputMode: "consensus" });
    boundary.rpc.mockResolvedValue({ run_quality: { ...quality, read_length: null } });
    await useMameAppStore.getState().runAnalysis();
    expect(useMameAppStore.getState().runQuality).toBeNull();
    expect(useMameAppStore.getState().validationErrors.join(" ")).toMatch(/Invalid RPC result shape/);
    expect(useMameAppStore.getState().isAnalyzing).toBe(false);
  });
  it.each(["position_recurrence", "indel_recurrence", "read_length"])(
    "refuses null %s before QC rendering", async (field) => {
      boundary.rpc.mockResolvedValue({ run_quality: { ...quality, [field]: null } });
      await expect(sendRequest("analyze")).rejects.toThrow(/Invalid RPC result shape/);
    },
  );
  it.each(["position_recurrence", "indel_recurrence", "read_length"])(
    "refuses restored null %s", async (field) => {
      boundary.read.mockResolvedValue(JSON.stringify({ schema: 1, result: {
        run_quality: { ...quality, [field]: null },
      } }));
      expect(await readMameResultSnapshot("/project")).toEqual({ status: "missing" });
    },
  );
  it("opens QC when legitimate legacy optional blocks are absent", async () => {
    boundary.rpc.mockResolvedValue({ run_quality: quality });
    const result = await sendRequest<AnalyzeResult>("analyze");
    useMameAppStore.setState({ runQuality: result.run_quality });
    render(<RunQcSection runHealth={null} />);
    fireEvent.click(screen.getByRole("button", { name: en.mame.runHealth.qcSectionAriaLabel }));
    expect(screen.getByTestId("run-qc-section")).toBeInTheDocument();
  });
});
