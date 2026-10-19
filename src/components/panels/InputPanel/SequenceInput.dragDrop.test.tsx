/**
 * The drag-and-drop registration resolves asynchronously. When the panel
 * unmounts first, the listener it eventually returns must be released and a
 * later drop must not load a sequence into whatever is on screen now.
 */
import { act, cleanup, render, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

type DropHandler = (event: { payload: { type: string; paths?: string[] } }) => void;
const registration = vi.hoisted(() => vi.fn());
vi.mock("@tauri-apps/api/webview", () => ({
  getCurrentWebview: () => ({ onDragDropEvent: registration }),
}));
vi.mock("@/lib/ipc-kuro", () => ({
  sendRequest: vi.fn(async () => ({ organisms: [] })),
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
}));

import { SequenceInput } from "./SequenceInput";
import { useAppStore } from "@/store/appStore";

describe("SequenceInput drag-and-drop subscription", () => {
  afterEach(cleanup);

  it("releases a registration that resolves after unmount and ignores its drops", async () => {
    const loadSequence = vi.fn(async () => undefined);
    useAppStore.setState({ loadSequence });
    let resolveRegistration!: (unlisten: () => void) => void;
    registration.mockReturnValue(new Promise((resolve) => { resolveRegistration = resolve; }));
    const unlisten = vi.fn();

    const view = render(<SequenceInput />);
    await waitFor(() => expect(registration).toHaveBeenCalledTimes(1));
    view.unmount();
    await act(async () => resolveRegistration(unlisten));

    expect(unlisten).toHaveBeenCalledTimes(1);
    const handler = registration.mock.calls[0][0] as DropHandler;
    await act(async () => handler({ payload: { type: "drop", paths: ["/x/seq.gb"] } }));
    expect(loadSequence).not.toHaveBeenCalled();
  });

  it("loads a dropped sequence while mounted", async () => {
    const loadSequence = vi.fn(async () => undefined);
    useAppStore.setState({ loadSequence });
    registration.mockResolvedValue(vi.fn());

    render(<SequenceInput />);
    await waitFor(() => expect(registration).toHaveBeenCalled());
    const handler = registration.mock.calls.at(-1)?.[0] as DropHandler;
    await act(async () => handler({ payload: { type: "drop", paths: ["/x/seq.gb"] } }));
    expect(loadSequence).toHaveBeenCalledWith("/x/seq.gb");
  });
});
