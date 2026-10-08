import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Onboarding } from "./Onboarding";
import * as projectApi from "../lib/project";
import * as pathApi from "@tauri-apps/api/path";

vi.mock("../lib/project", async () => {
  const actual = await vi.importActual<typeof import("../lib/project")>("../lib/project");
  return {
    ...actual,
    setProjectsRoot: vi.fn(),
  };
});

vi.mock("@tauri-apps/api/path", () => ({
  documentDir: vi.fn(),
  join: vi.fn(),
}));

const setProjectsRootMock = vi.mocked(projectApi.setProjectsRoot);
const documentDirMock = vi.mocked(pathApi.documentDir);
const joinMock = vi.mocked(pathApi.join);

describe("Onboarding", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    documentDirMock.mockResolvedValue("/Users/gml/Documents");
    joinMock.mockImplementation((...parts: string[]) => Promise.resolve(parts.join("/")));
  });

  it("calls setProjectsRoot and then onDone", async () => {
    const onDone = vi.fn();
    const cfg = {
      projects_root: "/tmp/kuma",
      recent_projects: [],
    };

    setProjectsRootMock.mockResolvedValueOnce(cfg);

    render(<Onboarding initialPath="/tmp/kuma" onDone={onDone} />);

    fireEvent.click(screen.getByRole("button", { name: "Done" }));

    await waitFor(() => {
      expect(setProjectsRootMock).toHaveBeenCalledWith("/tmp/kuma");
      expect(onDone).toHaveBeenCalledWith(cfg);
    });
  });

  it("uses the default projects folder as an actionable first-run value", async () => {
    const onDone = vi.fn();
    const cfg = {
      projects_root: "/Users/gml/Documents/kuma",
      recent_projects: [],
    };

    setProjectsRootMock.mockResolvedValueOnce(cfg);

    render(<Onboarding onDone={onDone} />);

    await waitFor(() => {
      expect(screen.getByLabelText("Projects folder")).toHaveValue(
        "/Users/gml/Documents/kuma",
      );
    });
    fireEvent.click(screen.getByRole("button", { name: "Done" }));

    await waitFor(() => {
      expect(setProjectsRootMock).toHaveBeenCalledWith("/Users/gml/Documents/kuma");
      expect(onDone).toHaveBeenCalledWith(cfg);
    });
  });

  it("disables submit when the path is cleared", () => {
    render(<Onboarding initialPath="/tmp/kuma" onDone={vi.fn()} />);

    fireEvent.change(screen.getByLabelText("Projects folder"), { target: { value: "" } });

    expect(screen.getByRole("button", { name: "Done" }).hasAttribute("disabled")).toBe(true);
  });
});
