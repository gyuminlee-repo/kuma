import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/ipc-mame", () => ({
  sendRequest: vi.fn(),
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
}));

import { sendRequest } from "@/lib/ipc-mame";
import { createMameStore, useMameAppStore } from "@/store/mame/mameAppStore";
import { fetchMameJanusPreview, handleExportMameJanusMapping } from "./janus";
import { DEFAULT_JANUS_SETTINGS } from "./janusSettings";

describe("independent cell-stock mapping", () => {
  beforeEach(() => {
    vi.mocked(sendRequest).mockReset();
    useMameAppStore.setState({ isExporting: false, analyzeResult: null });
  });

  it("routes a resequencing preview to its cache", async () => {
    const repeat = createMameStore("resequence");
    vi.mocked(sendRequest).mockResolvedValue({ row_count: 1 });

    await fetchMameJanusPreview(DEFAULT_JANUS_SETTINGS, repeat);

    expect(sendRequest).toHaveBeenCalledWith(
      "export_janus_mapping_dry_run",
      expect.objectContaining({ run_scope: "resequence" }),
    );
  });

  it("keeps export state scoped even when the resequencing export fails", async () => {
    const repeat = createMameStore("resequence");
    let rejectExport: (reason: Error) => void = () => {
      throw new Error("Export signal not initialized");
    };
    vi.mocked(sendRequest).mockImplementation(() => new Promise((_resolve, reject) => {
      rejectExport = reject;
    }));

    const pending = handleExportMameJanusMapping(
      "/resequence/stock.csv", "csv", DEFAULT_JANUS_SETTINGS, repeat,
    );
    const failure = expect(pending).rejects.toThrow("export failed");
    expect(repeat.getState().isExporting).toBe(true);
    expect(useMameAppStore.getState().isExporting).toBe(false);
    rejectExport(new Error("export failed"));
    await failure;

    expect(repeat.getState().isExporting).toBe(false);
    expect(sendRequest).toHaveBeenCalledWith(
      "export_janus_mapping",
      expect.objectContaining({ run_scope: "resequence", output: "/resequence/stock.csv" }),
    );
  });
});
