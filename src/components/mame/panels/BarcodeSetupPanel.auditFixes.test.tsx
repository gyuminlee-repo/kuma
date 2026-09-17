import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { BarcodeSetupPanel } from "@/components/mame/panels/BarcodeSetupPanel";
import { ProjectProvider } from "@/state/projectContext";
import { useMameAppStore } from "@/store/mame/mameAppStore";

const rpc = vi.hoisted(() => vi.fn());
vi.mock("@/lib/ipc", () => ({ rawSidecarRpc: rpc }));
vi.mock("@tauri-apps/plugin-dialog", () => ({ open: vi.fn() }));
vi.mock("@tauri-apps/plugin-fs", () => ({ readTextFile: vi.fn() }));
vi.mock("@/lib/workspace", () => ({ registerArtifacts: vi.fn() }));
vi.mock("@/lib/overwriteConfirm", () => ({ fileExists: vi.fn(), requestOverwriteConfirm: vi.fn() }));
vi.mock("@/lib/openFolder", () => ({ revealInOSFolder: vi.fn() }));

function mountPanel() {
  return render(
    <ProjectProvider value={{ path: "/project", name: "Demo", scratch: false }}>
      <BarcodeSetupPanel />
    </ProjectProvider>,
  );
}

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
  useMameAppStore.setState({
    resetEpoch: 0,
    sharedFastaPath: null,
    mameSamplePrefill: null,
    cdsCandidates: [],
    selectedCdsIndex: 0,
  });
});

describe("barcode setup audit", () => {
  it("clears on a new reset event and retains input entered after it on remount", () => {
    const view = mountPanel();
    fireEvent.change(screen.getByLabelText("Gene name"), { target: { value: "before_clear" } });
    act(() => useMameAppStore.setState({ resetEpoch: 1 }));
    expect(screen.getByLabelText("Gene name")).toHaveValue("");
    fireEvent.change(screen.getByLabelText("Gene name"), { target: { value: "after_clear" } });
    view.unmount();
    mountPanel();
    expect(screen.getByLabelText("Gene name")).toHaveValue("after_clear");
  });

  it.each([0, 1])("preserves stored user input when mounting at reset epoch %s", (resetEpoch) => {
    localStorage.setItem("kuma:mame:barcodeSetup", JSON.stringify({ geneName: "user_after_clear" }));
    useMameAppStore.setState({ resetEpoch });
    mountPanel();
    expect(screen.getByLabelText("Gene name")).toHaveValue("user_after_clear");
  });

  it("shows the same CDS selection as the auto-filled longest gene", async () => {
    localStorage.setItem("kuma:mame:barcodeSetup", JSON.stringify({ fastaPath: "/project/genes.gb" }));
    rpc.mockResolvedValue({
      header: "genes", seq_length: 1800,
      genes: [
        { gene: "short_gene", product: "short", cds_start: 0, cds_end: 303, aa_length: 101 },
        { gene: "long_gene", product: "long", cds_start: 600, cds_end: 1503, aa_length: 301 },
      ],
    });
    mountPanel();
    await waitFor(() => expect(screen.getByLabelText("Gene name")).toHaveValue("long_gene"));
    expect(screen.getByRole("combobox", { name: /CDS \/ ORF candidate/i })).toHaveTextContent("long_gene");
  });
});
