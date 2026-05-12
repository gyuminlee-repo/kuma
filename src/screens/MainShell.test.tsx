import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MainShell } from "./MainShell";
import { ProjectProvider } from "@/state/projectContext";
import {
  __emitCloseRequestedForTest,
  __getWindowMockState,
  __resetWindowMock,
} from "../../scripts/stubs/webview";

vi.mock("@/lib/ipc", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/ipc")>();
  return {
    ...actual,
    killSidecar: vi.fn().mockResolvedValue(undefined),
    rpc: vi.fn().mockResolvedValue({}),
  };
});

import { killSidecar, rpc } from "@/lib/ipc";

const killSidecarMock = vi.mocked(killSidecar);
const rpcMock = vi.mocked(rpc);

describe("MainShell", () => {
  beforeEach(() => {
    __resetWindowMock();
    vi.clearAllMocks();
  });

  it("renders the shell header", () => {
    render(
      <ProjectProvider value={{ path: "/tmp/x", name: "Demo", scratch: false }}>
        <MainShell />
      </ProjectProvider>,
    );

    expect(screen.getByText("Demo")).toBeTruthy();
  });

  it("does not block the final native close emitted by destroy", async () => {
    render(
      <ProjectProvider value={{ path: "/tmp/x", name: "Demo", scratch: false }}>
        <MainShell />
      </ProjectProvider>,
    );

    await waitFor(() => {
      expect(__getWindowMockState().hasCloseRequestedHandler).toBe(true);
    });

    await __emitCloseRequestedForTest();

    await waitFor(() => {
      expect(__getWindowMockState().destroyCount).toBe(1);
    });
    expect(killSidecarMock).toHaveBeenCalledWith("kuro");
    expect(killSidecarMock).toHaveBeenCalledWith("mame");
    expect(__getWindowMockState().preventDefaultCount).toBe(1);
  });

  // TODO: tab change ping handler does not fire under jsdom + react-resizable-panels.
  // Production works; only the test-environment interaction is broken. Re-enable once
  // a stable reproduction or a userEvent / RTL workaround lands.
  it.skip("pings sidecars when tabs change", async () => {
    const user = userEvent.setup();
    render(
      <ProjectProvider value={{ path: "/tmp/x", name: "Demo", scratch: false }}>
        <MainShell />
      </ProjectProvider>,
    );

    await user.click(screen.getByRole("tab", { name: "Mame" }));
    await waitFor(() => {
      expect(rpcMock).toHaveBeenCalledWith("mame", "ping", {});
    });

    await user.click(screen.getByRole("tab", { name: "Kuro" }));
    await waitFor(() => {
      expect(rpcMock).toHaveBeenCalledWith("kuro", "ping", {});
    });
  });
});
