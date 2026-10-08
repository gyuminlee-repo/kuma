/**
 * The first BLAST or InterProScan submission without a contact email opens this
 * dialog. Saving has to reach preferences.json before the caller retries,
 * because the sidecar reads the address from there; the settings store's own
 * 500 ms debounce would otherwise let the retry go out with no address.
 */
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { sendRequest } from "../../../lib/ipc-kuro";
import { useAppStore } from "../../../store/appStore";
import { ContactEmailDialog } from "../ContactEmailDialog";

vi.mock("../../../lib/ipc-kuro", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../lib/ipc-kuro")>();
  return { ...actual, sendRequest: vi.fn() };
});

const mockedSendRequest = vi.mocked(sendRequest);

describe("ContactEmailDialog", () => {
  beforeEach(() => {
    mockedSendRequest.mockReset();
    mockedSendRequest.mockResolvedValue({ ok: true, path: "preferences.json" });
    useAppStore.setState({ settings: { theme: "dark", network: { consent_blast: true } } });
  });

  afterEach(() => {
    useAppStore.setState({ contactEmailPending: false });
  });

  it("opens when an address is needed, saves it, then lets the caller resume", async () => {
    render(<ContactEmailDialog />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    let pending!: Promise<boolean>;
    act(() => {
      pending = useAppStore.getState().requireContactEmail();
    });
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText(/EBI requires/i)).toBeInTheDocument();

    const input = screen.getByLabelText(/^email address$/i);
    fireEvent.change(input, { target: { value: "someone@lab.org" } });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /save/i }));
    });

    await expect(pending).resolves.toBe(true);
    // Saved to disk, with the rest of the bundle intact, before resuming.
    expect(mockedSendRequest).toHaveBeenCalledWith("settings_save", {
      settings: {
        theme: "dark",
        network: { consent_blast: true, contact_email: "someone@lab.org" },
      },
    });
    expect(useAppStore.getState().contactEmailPending).toBe(false);
  });

  it("refuses an address without @ and a domain, and saves nothing", async () => {
    render(<ContactEmailDialog />);
    act(() => {
      void useAppStore.getState().requireContactEmail();
    });
    const input = await screen.findByLabelText(/^email address$/i);
    fireEvent.change(input, { target: { value: "not-an-address" } });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /save/i }));
    });

    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(mockedSendRequest).not.toHaveBeenCalled();
    expect(useAppStore.getState().contactEmailPending).toBe(true);
  });

  it("resolves false on cancel so the caller can skip the EBI step", async () => {
    render(<ContactEmailDialog />);
    let pending!: Promise<boolean>;
    act(() => {
      pending = useAppStore.getState().requireContactEmail();
    });
    await screen.findByRole("dialog");
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /skip/i }));
    });

    await expect(pending).resolves.toBe(false);
    expect(mockedSendRequest).not.toHaveBeenCalled();
  });

  it("shares one dialog between callers that ask at the same time", async () => {
    render(<ContactEmailDialog />);
    let first!: Promise<boolean>;
    let second!: Promise<boolean>;
    act(() => {
      first = useAppStore.getState().requireContactEmail();
      second = useAppStore.getState().requireContactEmail();
    });
    expect(await screen.findAllByRole("dialog")).toHaveLength(1);
    fireEvent.change(screen.getByLabelText(/^email address$/i), { target: { value: "someone@lab.org" } });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /save/i }));
    });

    await expect(first).resolves.toBe(true);
    await expect(second).resolves.toBe(true);
  });
});
