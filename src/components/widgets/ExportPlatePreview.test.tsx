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
  // Quadrant state is reset here too: it is store state a test can set, and a
  // leftover selection would silently change what the Echo grid and its
  // caption claim in every later test.
  useAppStore.setState({
    echoTransferVol: 100,
    janusTransferVol: 2.0,
    echoQuadrant: null,
    echoUsedQuadrants: [],
  });
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
    const empty = await screen.findByText(/no mapping/i);
    expect(empty).toBeInTheDocument();
    // StateView's title <p>, not the plain muted div this replaced.
    expect(empty.className).toContain("text-title");
  });

  it("shows error with retry on failure", async () => {
    (invoke as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("boom"));
    render(<ExportPlatePreview />);
    expect(await screen.findByText(/boom/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /retry|재시도/i })).toBeInTheDocument();
  });

  it("announces the error through StateView's alert role", async () => {
    (invoke as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("boom"));
    render(<ExportPlatePreview />);
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/boom/);
  });

  it("marks the loading state as a live region", () => {
    (invoke as ReturnType<typeof vi.fn>).mockImplementation(() => new Promise(() => {}));
    const { container } = render(<ExportPlatePreview />);
    expect(container.querySelector("[aria-live='polite']")).not.toBeNull();
  });

  it("labels the two Echo-tab grids differently", async () => {
    (invoke as ReturnType<typeof vi.fn>).mockImplementation((...a: unknown[]) => {
      const arg = a[1] as { method?: string };
      if (arg?.method === "export_echo_mapping_dry_run") {
        return Promise.resolve({
          rows: [
            {
              // Full eight-key shape validators.ts:870 requires; a short
              // fixture is rejected before the view ever renders.
              source_plate: "P1",
              source_well_name: "P1-fw",
              source_well: "A01",
              dest_plate: "D1",
              dest_well_name: "D1-A1",
              dest_well: "A1",
              transfer_vol: 25,
              mutation: "P1",
            },
          ],
          total: 1,
          transfer_vol: 25,
        });
      }
      return Promise.resolve(emptyJanus);
    });
    render(<ExportPlatePreview />);
    const source = await screen.findByText(/Echo source plate \(384/i);
    const dest = await screen.findByText(/Destination plate \(96/i);
    expect(source.textContent).not.toBe(dest.textContent);
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
          // build_echo_rows always emits `mutation`
          // (kuma_core/kuro/plate_mapper.py:904 and :932), so the fixture does too.
          mutation: "P1",
        },
      ],
      total: 1,
      transfer_vol: 25,
    };
    const janusRows = {
      rows: [
        {
          name: "P1-fw",
          type: "primer",
          no: 1,
          asp_rack: "fw plate",
          asp_posi: "A1",
          dsp_rack: "PCR mixture plate",
          dsp_posi: "B2",
          volume: 2.5,
          mutation: "P1",
          role: "fwd",
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

  it("offers no row-band control and sends no mapping_range", async () => {
    // Placement is the quadrant selector's job (ExportFormatSelector, rendered
    // beneath this preview). The row band that used to sit here wrapped modulo
    // its own width in the mapper, so every band it could express other than the
    // full plate stacked different mutants onto one source well.
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
          // build_echo_rows always emits `mutation`
          // (kuma_core/kuro/plate_mapper.py:904 and :932), so the fixture does too.
          mutation: "P1",
        },
      ],
      total: 1,
      transfer_vol: 25,
    };
    (invoke as ReturnType<typeof vi.fn>).mockImplementation((_cmd, args) => {
      const a = args as { method: string };
      if (a.method === "export_echo_mapping_dry_run") return Promise.resolve(echoRows);
      if (a.method === "export_janus_mapping_dry_run") return Promise.resolve(emptyJanus);
      return Promise.resolve({});
    });

    const { container } = render(<ExportPlatePreview />);
    await waitFor(() => {
      expect(container.querySelectorAll("[data-testid='echo-cell']").length).toBeGreaterThan(0);
    });

    // The plate is on screen, so the whole control area rendered; no dropdown there.
    expect(screen.queryByRole("combobox")).toBeNull();
    expect(document.getElementById("mapping-range-row-start")).toBeNull();
    expect(document.getElementById("mapping-range-row-end")).toBeNull();

    const calls = (invoke as ReturnType<typeof vi.fn>).mock.calls;
    expect(calls.length).toBeGreaterThan(0);
    for (const c of calls) {
      const params = (c[1] as { params?: Record<string, unknown> }).params ?? {};
      expect(params).not.toHaveProperty("mapping_range");
    }
  });

  // The grid draws one quadrant pair of an interleaved layout, which reads as
  // "primers placed one well apart" unless the view says what it is showing.
  describe("Echo quadrant caption", () => {
    function mockEchoRow() {
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
            mutation: "P1",
          },
        ],
        total: 1,
        transfer_vol: 25,
      };
      (invoke as ReturnType<typeof vi.fn>).mockImplementation((_cmd, args) => {
        const a = args as { method: string };
        if (a.method === "export_echo_mapping_dry_run") return Promise.resolve(echoRows);
        if (a.method === "export_janus_mapping_dry_run") return Promise.resolve(emptyJanus);
        return Promise.resolve({});
      });
    }

    it("names both quadrants of the pair the selected run fills", async () => {
      useAppStore.setState({ echoQuadrant: "A1" });
      mockEchoRow();
      render(<ExportPlatePreview />);
      const note = await screen.findByTestId("echo-quadrant-note");
      // A1 alone would leave the reverse primers in rows B, D, F looking like
      // another run's wells; the caption names the pair the mapper spends.
      expect(note.textContent).toContain("A1");
      expect(note.textContent).toContain("B1");
    });

    it("counts the quadrants this run leaves spent", async () => {
      useAppStore.setState({ echoQuadrant: "A1" });
      mockEchoRow();
      render(<ExportPlatePreview />);
      const progress = await screen.findByTestId("echo-quadrant-progress");
      expect(progress.textContent).toMatch(/2 of 4/);
    });

    it("adds the operator's spent quadrants to that count", async () => {
      useAppStore.setState({ echoQuadrant: "A1", echoUsedQuadrants: ["A2", "B2"] });
      mockEchoRow();
      render(<ExportPlatePreview />);
      const progress = await screen.findByTestId("echo-quadrant-progress");
      expect(progress.textContent).toMatch(/4 of 4/);
    });

    it("lists the spent quadrants only when the operator named some", async () => {
      useAppStore.setState({ echoQuadrant: "A1", echoUsedQuadrants: ["A2"] });
      mockEchoRow();
      render(<ExportPlatePreview />);
      const used = await screen.findByTestId("echo-quadrant-used");
      expect(used.textContent).toContain("A2");
    });

    it("shows no spent-quadrant line when none were named", async () => {
      useAppStore.setState({ echoQuadrant: "A1", echoUsedQuadrants: [] });
      mockEchoRow();
      render(<ExportPlatePreview />);
      await screen.findByTestId("echo-quadrant-note");
      expect(screen.queryByTestId("echo-quadrant-used")).toBeNull();
    });

    it("says so instead when no quadrant is selected", async () => {
      mockEchoRow();
      render(<ExportPlatePreview />);
      const note = await screen.findByTestId("echo-quadrant-note");
      expect(note.textContent).toMatch(/no quadrant selected/i);
      expect(screen.queryByTestId("echo-quadrant-progress")).toBeNull();
    });
  });
});
