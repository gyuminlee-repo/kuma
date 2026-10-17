/**
 * A preview requested for a file that is no longer selected must not land.
 * Clearing the source (Clear All, project switch) leaves no path, and the reply
 * to the earlier request used to repopulate the cleared table.
 */
import { act, cleanup, render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ sendRequest: vi.fn() }));
vi.mock("@/lib/ipc-kuro", () => ({
  sendRequest: mocks.sendRequest,
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
}));

import { SourceColumnPanel } from "./SourceColumnPanel";
import { useAppStore } from "@/store/appStore";

const OLD = { headers: ["Variant", "old"], rows: [["A1V", "1"]], sheets: [] };
const NEW = { headers: ["Variant", "fitness"], rows: [["G2S", "2"]], sheets: [] };

function select(path: string) {
  useAppStore.setState({
    evolveproCsvPath: path,
    evolveproPreview: null,
    evolveproSheetName: null,
    evolveproVariantColumn: null,
    evolveproScoreColumn: null,
  });
}

describe("SourceColumnPanel late preview replies", () => {
  beforeEach(() => { mocks.sendRequest.mockReset(); });
  afterEach(cleanup);

  it("drops the reply for a source that was cleared while it was pending", async () => {
    let release!: (value: unknown) => void;
    mocks.sendRequest.mockReturnValue(new Promise((resolve) => { release = resolve; }));
    select("/a/items.csv");
    render(<SourceColumnPanel />);
    await waitFor(() => expect(mocks.sendRequest).toHaveBeenCalledTimes(1));

    act(() => select(""));
    await act(async () => release(OLD));

    expect(useAppStore.getState().evolveproPreview).toBeNull();
  });

  it("still applies the reply for the source that is selected", async () => {
    const releases: Array<(value: unknown) => void> = [];
    mocks.sendRequest.mockImplementation(() => new Promise((resolve) => { releases.push(resolve); }));
    select("/a/items.csv");
    render(<SourceColumnPanel />);
    await waitFor(() => expect(releases).toHaveLength(1));

    act(() => select("/b/items.csv"));
    await waitFor(() => expect(releases).toHaveLength(2));
    await act(async () => releases[1](NEW));
    await act(async () => releases[0](OLD));

    expect(useAppStore.getState().evolveproPreview).toEqual(NEW);
  });
});
