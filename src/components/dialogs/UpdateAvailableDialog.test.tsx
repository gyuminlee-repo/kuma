import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { UpdateAvailableDialog } from "./UpdateAvailableDialog";

const openUrlMock = vi.hoisted(() => vi.fn<() => Promise<void>>());

vi.mock("@tauri-apps/plugin-opener", () => ({
  openUrl: openUrlMock,
}));

describe("UpdateAvailableDialog", () => {
  beforeEach(() => {
    openUrlMock.mockReset();
    openUrlMock.mockResolvedValue();
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("recommends a newer GitHub release and opens its release page", async () => {
    const fetchMock = vi.fn<typeof fetch>();
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ tag_name: "v0.13.12" }), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<UpdateAvailableDialog />);

    expect(
      await screen.findByText("Update available: v0.0.0-test to v0.13.12"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/A newer Kuma release is available on GitHub/),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "View release" }));
    await waitFor(() => {
      expect(openUrlMock).toHaveBeenCalledWith(
        "https://github.com/gyuminlee-repo/kuma/releases/tag/v0.13.12",
      );
    });
  });

  it("stays closed when the installed version is current", async () => {
    const fetchMock = vi.fn<typeof fetch>();
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ tag_name: "v0.0.0-test" }), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<UpdateAvailableDialog />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledOnce());
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
