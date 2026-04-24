import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { MainShell } from "./MainShell";
import { ProjectProvider } from "@/state/projectContext";

vi.mock("@/lib/ipc", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/ipc")>();
  return {
    ...actual,
    rpc: vi.fn().mockResolvedValue({}),
  };
});

import { rpc } from "@/lib/ipc";

const rpcMock = vi.mocked(rpc);

describe("MainShell", () => {
  it("renders the shell header", () => {
    render(
      <ProjectProvider value={{ path: "/tmp/x", name: "Demo", scratch: false }}>
        <MainShell />
      </ProjectProvider>,
    );

    expect(screen.getByText("kuma")).toBeTruthy();
    expect(screen.getByText("Demo")).toBeTruthy();
  });

  it("pings sidecars when tabs change", async () => {
    const user = userEvent.setup();
    render(
      <ProjectProvider value={{ path: "/tmp/x", name: "Demo", scratch: false }}>
        <MainShell />
      </ProjectProvider>,
    );

    await user.click(screen.getByRole("tab", { name: "Mame" }));
    expect(rpcMock).toHaveBeenCalledWith("mame", "ping", {});

    await user.click(screen.getByRole("tab", { name: "Kuro" }));
    expect(rpcMock).toHaveBeenCalledWith("kuro", "ping", {});
  });
});
