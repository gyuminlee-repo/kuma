import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  ProjectTourCoordinator,
  START_GUIDED_TOUR_EVENT,
} from "./ProjectTourCoordinator";

const project = {
  path: "/tmp/tutorial-project",
  name: "Tutorial",
  scratch: false,
  project_id: "tutorial-project-id",
  newlyCreated: true,
};

function storageKey(kind: "overview" | "kuro" | "mame"): string {
  return `kuma:guided-tour:${encodeURIComponent(project.project_id)}:${kind}`;
}

describe("ProjectTourCoordinator", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    cleanup();
  });

  it("starts the overview once and chains into the Kuro tour", async () => {
    const onTabChange = vi.fn();
    render(
      <ProjectTourCoordinator
        project={project}
        activeTab="kuro"
        onTabChange={onTabChange}
      />,
    );

    expect(await screen.findByText("Move between Kuro and Mame")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByText("Track the active project")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Finish" }));

    expect(await screen.findByText("Follow the Kuro workflow")).toBeInTheDocument();
    expect(localStorage.getItem(storageKey("overview"))).toBe("1");
    expect(onTabChange).not.toHaveBeenCalled();
  });

  it("Skip all tours suppresses every automatic project tour", async () => {
    render(
      <ProjectTourCoordinator
        project={project}
        activeTab="kuro"
        onTabChange={vi.fn()}
      />,
    );

    fireEvent.click(await screen.findByRole("button", { name: "Skip all tours" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(localStorage.getItem(storageKey("overview"))).toBe("1");
    expect(localStorage.getItem(storageKey("kuro"))).toBe("1");
    expect(localStorage.getItem(storageKey("mame"))).toBe("1");
  });

  it("Escape dismisses without opting out of future tours", async () => {
    render(
      <ProjectTourCoordinator
        project={project}
        activeTab="kuro"
        onTabChange={vi.fn()}
      />,
    );

    await screen.findByRole("dialog");
    fireEvent.keyDown(window, { key: "Escape" });

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(localStorage.getItem(storageKey("overview"))).toBeNull();
    expect(localStorage.getItem(storageKey("kuro"))).toBeNull();
    expect(localStorage.getItem(storageKey("mame"))).toBeNull();
  });

  it("does not automatically tour an existing project", () => {
    render(
      <ProjectTourCoordinator
        project={{ ...project, project_id: "existing-project", newlyCreated: false }}
        activeTab="kuro"
        onTabChange={vi.fn()}
      />,
    );

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("can replay the current tab tour from the Help event", async () => {
    localStorage.setItem(storageKey("overview"), "1");
    localStorage.setItem(storageKey("kuro"), "1");
    localStorage.setItem(storageKey("mame"), "1");
    render(
      <ProjectTourCoordinator
        project={project}
        activeTab="mame"
        onTabChange={vi.fn()}
      />,
    );

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    window.dispatchEvent(new CustomEvent(START_GUIDED_TOUR_EVENT));

    expect(await screen.findByText("Follow the Mame workflow")).toBeInTheDocument();
  });
});
