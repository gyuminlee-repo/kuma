/**
 * A dry-run requested under earlier settings must not overwrite the preview
 * computed for the current settings, whichever of the two replies lands last.
 */
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { invoke } from "@tauri-apps/api/core";
import { ExportPlatePreview } from "./ExportPlatePreview";
import { useAppStore } from "@/store/appStore";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));

type Pending = { method: string; vol: number; resolve: (v: unknown) => void; reject: (e: Error) => void };
const pending: Pending[] = [];

beforeEach(() => {
  (globalThis as { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__ = {};
  pending.length = 0;
  vi.mocked(invoke).mockReset();
  vi.mocked(invoke).mockImplementation((_cmd, args) => {
    const a = args as { method: string; params: { transfer_vol: number } };
    return new Promise((resolve, reject) => {
      pending.push({ method: a.method, vol: a.params.transfer_vol, resolve, reject });
    });
  });
  useAppStore.setState({ echoTransferVol: 100, janusTransferVol: 2, echoQuadrant: null, echoUsedQuadrants: [] });
});
afterEach(cleanup);

const empty = { rows: [], total: 0, transfer_vol: 0 };

describe("ExportPlatePreview out-of-order replies", () => {
  it("keeps the current preview when the superseded request fails late", async () => {
    render(<ExportPlatePreview />);
    await waitFor(() => expect(pending).toHaveLength(2));
    act(() => useAppStore.setState({ echoTransferVol: 250 }));
    await waitFor(() => expect(pending).toHaveLength(4));

    await act(async () => { pending[2].resolve(empty); pending[3].resolve(empty); });
    expect(await screen.findByText(/no mapping/i)).toBeInTheDocument();

    await act(async () => { pending[0].reject(new Error("stale dry-run failure")); pending[1].resolve(empty); });
    expect(screen.queryByText(/stale dry-run failure/)).toBeNull();
    expect(screen.getByText(/no mapping/i)).toBeInTheDocument();
  });
});
