import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { invoke } from "@tauri-apps/api/core";
import { ExportPlatePreview } from "./ExportPlatePreview";
import { useAppStore } from "@/store/appStore";

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
