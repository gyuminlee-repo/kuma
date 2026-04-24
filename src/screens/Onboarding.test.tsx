import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Onboarding } from "./Onboarding";
import * as projectApi from "../lib/project";

vi.mock("../lib/project", async () => {
  const actual = await vi.importActual<typeof import("../lib/project")>("../lib/project");
  return {
    ...actual,
    setProjectsRoot: vi.fn(),
  };
});

const setProjectsRootMock = vi.mocked(projectApi.setProjectsRoot);

describe("Onboarding", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("calls setProjectsRoot and then onDone", async () => {
    const onDone = vi.fn();
    const cfg = {
      projects_root: "/tmp/kuma",
      recent_projects: [],
    };

    setProjectsRootMock.mockResolvedValueOnce(cfg);

    render(<Onboarding initialPath="/tmp/kuma" onDone={onDone} />);

    fireEvent.click(screen.getByRole("button", { name: "완료" }));

    await waitFor(() => {
      expect(setProjectsRootMock).toHaveBeenCalledWith("/tmp/kuma");
      expect(onDone).toHaveBeenCalledWith(cfg);
    });
  });

  it("disables submit when the path is empty", () => {
    render(<Onboarding onDone={vi.fn()} />);

    expect(screen.getByRole("button", { name: "완료" }).hasAttribute("disabled")).toBe(true);
  });
});
