import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { invoke } from "@tauri-apps/api/core";
import { ExportPlatePreview } from "./ExportPlatePreview";
import { useAppStore } from "@/store/appStore";
import type { PlateMapping, SdmPrimerResult } from "@/types/models";

vi.mock("@tauri-apps/api/core", () => ({
  invoke: vi.fn(),
}));

// rpc() in src/lib/ipc.ts checks __TAURI_INTERNALS__ before invoking; make it truthy.
beforeEach(() => {
  (globalThis as { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__ = {};
  (invoke as ReturnType<typeof vi.fn>).mockReset();
  useAppStore.setState({ echoTransferVol: 100, janusTransferVol: 2.0 });
});

const emptyEcho = { rows: [], total: 0, transfer_vol: 25 };
const emptyJanus = { rows: [], total: 0, transfer_vol: 2.5 };

function mockBothEmpty() {
  (invoke as ReturnType<typeof vi.fn>).mockImplementation((_cmd, args) => {
    const a = args as { method: string };
    if (a.method === "export_echo_mapping_dry_run") return Promise.resolve(emptyEcho);
    if (a.method === "export_janus_mapping_dry_run") return Promise.resolve(emptyJanus);
    return Promise.resolve({});
  });
}

describe("ExportPlatePreview", () => {
  it("calls echo + janus dry-run on mount", async () => {
    mockBothEmpty();
    render(<ExportPlatePreview />);
    await waitFor(() => {
      const calls = (invoke as ReturnType<typeof vi.fn>).mock.calls;
      const methods = calls.map((c) => (c[1] as { method?: string })?.method);
      expect(methods).toContain("export_echo_mapping_dry_run");
      expect(methods).toContain("export_janus_mapping_dry_run");
    });
  });

  it("passes configured transfer volumes to dry-run preview", async () => {
    useAppStore.setState({ echoTransferVol: 250, janusTransferVol: 3.5 });
    mockBothEmpty();
    render(<ExportPlatePreview />);
    await waitFor(() => {
      const calls = (invoke as ReturnType<typeof vi.fn>).mock.calls;
      const echoCall = calls.find((c) => (c[1] as { method?: string })?.method === "export_echo_mapping_dry_run");
      const janusCall = calls.find((c) => (c[1] as { method?: string })?.method === "export_janus_mapping_dry_run");
      expect((echoCall?.[1] as { params?: { transfer_vol?: number } }).params?.transfer_vol).toBe(250);
      expect((janusCall?.[1] as { params?: { transfer_vol?: number } }).params?.transfer_vol).toBe(3.5);
    });
  });

  it("shows empty state when no rows", async () => {
    mockBothEmpty();
    render(<ExportPlatePreview />);
    expect(await screen.findByText(/no mapping/i)).toBeInTheDocument();
  });

  it("shows error with retry on failure", async () => {
    (invoke as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("boom"));
    render(<ExportPlatePreview />);
    expect(await screen.findByText(/boom/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /retry|재시도/i })).toBeInTheDocument();
  });

  it("renders loading state initially", () => {
    (invoke as ReturnType<typeof vi.fn>).mockImplementation(() => new Promise(() => {}));
    render(<ExportPlatePreview />);
    expect(screen.getByText(/loading preview/i)).toBeInTheDocument();
  });

  it("sends pre-reordered mappings reflecting tableSorting to the dry-run RPC", async () => {
    // Seed store: two mutations with distinct fwd_len so sort by fwd_len reorders them.
    const baseResult: SdmPrimerResult = {
      mutation: "",
      aa_position: 0,
      codon_pos: 0,
      forward_seq: "",
      reverse_seq: "",
      fwd_len: 0,
      rev_len: 0,
      overlap_len: 18,
      tm_no_fwd: 60,
      tm_no_rev: 60,
      tm_overlap: 60,
      tm_condition_met: true,
      tolerance_used: 0,
      has_offtarget: false,
      penalty: 0,
      gc_fwd: 50,
      gc_rev: 50,
      wt_codon: "AAA",
      mt_codon: "GGG",
      overlap_seq: "",
      warnings: [],
    };
    const designResults: SdmPrimerResult[] = [
      { ...baseResult, mutation: "K1A", aa_position: 1, fwd_len: 30 },
      { ...baseResult, mutation: "L2B", aa_position: 2, fwd_len: 20 },
    ];
    const plateMappings: PlateMapping[] = [
      { well: "A1", primer_name: "K1A-fw", sequence: "AAA", primer_type: "forward", mutation: "K1A" },
      { well: "B1", primer_name: "L2B-fw", sequence: "CCC", primer_type: "forward", mutation: "L2B" },
      { well: "A1", primer_name: "K1A-rv", sequence: "TTT", primer_type: "reverse", mutation: "K1A" },
      { well: "B1", primer_name: "L2B-rv", sequence: "GGG", primer_type: "reverse", mutation: "L2B" },
    ];
    const dedupInfo = { TTT: ["K1A"], GGG: ["L2B"] };

    useAppStore.setState({
      designResults,
      plateMappings,
      dedupInfo,
      tableSorting: [{ id: "fwd_len", desc: false }], // ascending → L2B(20) first, K1A(30) second
    });

    mockBothEmpty();
    render(<ExportPlatePreview />);
    await waitFor(() => {
      const calls = (invoke as ReturnType<typeof vi.fn>).mock.calls;
      expect(calls.length).toBeGreaterThan(0);
    });

    const calls = (invoke as ReturnType<typeof vi.fn>).mock.calls;
    const echoCall = calls.find((c) => (c[1] as { method?: string })?.method === "export_echo_mapping_dry_run");
    expect(echoCall).toBeDefined();
    const payload = (echoCall![1] as { params: { mappings: PlateMapping[] } }).params;
    expect(payload.mappings).toBeDefined();
    // Forward mappings should be reordered: L2B (fwd_len=20) before K1A (fwd_len=30).
    const fwdMappings = payload.mappings.filter((m) => m.primer_type === "forward");
    expect(fwdMappings.map((m) => m.mutation)).toEqual(["L2B", "K1A"]);

    // Reset state so subsequent tests don't see this fixture.
    useAppStore.setState({ designResults: [], plateMappings: [], dedupInfo: {}, tableSorting: [] });
  });

  it("re-fires RPC when tableSorting changes after initial mount", async () => {
    const baseResult: SdmPrimerResult = {
      mutation: "",
      aa_position: 0,
      codon_pos: 0,
      forward_seq: "",
      reverse_seq: "",
      fwd_len: 0,
      rev_len: 0,
      overlap_len: 18,
      tm_no_fwd: 60,
      tm_no_rev: 60,
      tm_overlap: 60,
      tm_condition_met: true,
      tolerance_used: 0,
      has_offtarget: false,
      penalty: 0,
      gc_fwd: 50,
      gc_rev: 50,
      wt_codon: "AAA",
      mt_codon: "GGG",
      overlap_seq: "",
      warnings: [],
    };
    const designResults: SdmPrimerResult[] = [
      { ...baseResult, mutation: "K1A", aa_position: 1, fwd_len: 30 },
      { ...baseResult, mutation: "L2B", aa_position: 2, fwd_len: 20 },
    ];
    const plateMappings: PlateMapping[] = [
      { well: "A1", primer_name: "K1A-fw", sequence: "AAA", primer_type: "forward", mutation: "K1A" },
      { well: "B1", primer_name: "L2B-fw", sequence: "CCC", primer_type: "forward", mutation: "L2B" },
    ];

    useAppStore.setState({
      designResults,
      plateMappings,
      dedupInfo: {},
      tableSorting: [{ id: "fwd_len", desc: false }], // L2B first
    });

    mockBothEmpty();
    render(<ExportPlatePreview />);
    await waitFor(() => {
      const calls = (invoke as ReturnType<typeof vi.fn>).mock.calls;
      expect(calls.length).toBeGreaterThanOrEqual(2);
    });

    // Capture initial call count, then flip sort direction.
    const initialCallCount = (invoke as ReturnType<typeof vi.fn>).mock.calls.length;
    useAppStore.setState({ tableSorting: [{ id: "fwd_len", desc: true }] }); // now K1A first

    await waitFor(() => {
      const calls = (invoke as ReturnType<typeof vi.fn>).mock.calls;
      expect(calls.length).toBeGreaterThan(initialCallCount);
    });

    const latestEchoCall = [...(invoke as ReturnType<typeof vi.fn>).mock.calls]
      .reverse()
      .find((c) => (c[1] as { method?: string })?.method === "export_echo_mapping_dry_run");
    const latestPayload = (latestEchoCall![1] as { params: { mappings: PlateMapping[] } }).params;
    const fwdLatest = latestPayload.mappings.filter((m) => m.primer_type === "forward");
    expect(fwdLatest.map((m) => m.mutation)).toEqual(["K1A", "L2B"]);

    useAppStore.setState({ designResults: [], plateMappings: [], dedupInfo: {}, tableSorting: [] });
  });

  it("renders Echo view by default and switches to Janus on tab click", async () => {
    const echoRows = {
      rows: [
        {
          source_plate: "P1",
          source_well_name: "P1-fw",
          source_well: "A01",
          dest_plate: "D1",
          dest_well_name: "D1-A1",
          dest_well: "A1",
          transfer_vol: 25,
        },
      ],
      total: 1,
      transfer_vol: 25,
    };
    const janusRows = {
      rows: [
        {
          name: "P1-fw",
          type: "fw",
          dsp_rack_label: "rack2",
          no: 1,
          asp_rack: 1,
          asp_posi: "A1",
          dsp_rack: 2,
          dsp_posi: "B2",
          volume: 2.5,
        },
      ],
      total: 1,
      transfer_vol: 2.5,
    };
    (invoke as ReturnType<typeof vi.fn>).mockImplementation((_cmd, args) => {
      const a = args as { method: string };
      if (a.method === "export_echo_mapping_dry_run") return Promise.resolve(echoRows);
      if (a.method === "export_janus_mapping_dry_run") return Promise.resolve(janusRows);
      return Promise.resolve({});
    });
    const { container } = render(<ExportPlatePreview />);
    await waitFor(() => {
      expect(container.querySelectorAll("[data-testid='echo-cell']").length).toBeGreaterThan(0);
    });
    // Echo cells visible, janus cells not
    expect(container.querySelectorAll("[data-testid='janus-cell']").length).toBe(0);
    // Click Janus tab (Radix Tabs responds to pointer + mouse events)
    const janusTab = screen.getByRole("tab", { name: /janus/i });
    fireEvent.pointerDown(janusTab, { button: 0, pointerType: "mouse" });
    fireEvent.mouseDown(janusTab, { button: 0 });
    fireEvent.click(janusTab);
    await waitFor(() => {
      expect(container.querySelectorAll("[data-testid='janus-cell']").length).toBe(192);
    });
    expect(container.querySelectorAll("[data-testid='echo-cell']").length).toBe(0);
  });
});
