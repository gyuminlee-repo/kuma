import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { WorkflowRail, type WorkflowStep } from "./WorkflowRail";

const BASE_STEPS: WorkflowStep[] = [
  { num: 1, title: "Load", state: "done" },
  { num: 2, title: "Mutate", hint: "Enter mutations", state: "active", mini: "now" },
  { num: 3, title: "Params", state: "lock" },
];

describe("WorkflowRail", () => {
  it("renders without crashing", () => {
    render(
      <WorkflowRail title="Design workflow" progressPercent={34} steps={BASE_STEPS} />,
    );
    expect(screen.getByText("Design workflow")).toBeInTheDocument();
  });

  it("progress bar has correct aria attributes", () => {
    render(
      <WorkflowRail title="Design workflow" progressPercent={50} steps={BASE_STEPS} />,
    );
    const bar = screen.getByRole("progressbar");
    expect(bar).toHaveAttribute("aria-valuenow", "50");
    expect(bar).toHaveAttribute("aria-valuemin", "0");
    expect(bar).toHaveAttribute("aria-valuemax", "100");
  });

  it("renders all step titles", () => {
    render(
      <WorkflowRail title="Design workflow" progressPercent={34} steps={BASE_STEPS} />,
    );
    expect(screen.getByText("Load")).toBeInTheDocument();
    expect(screen.getByText("Mutate")).toBeInTheDocument();
    expect(screen.getByText("Params")).toBeInTheDocument();
  });

  it("active step has aria-current=step", () => {
    render(
      <WorkflowRail title="Design workflow" progressPercent={34} steps={BASE_STEPS} />,
    );
    const activeBtn = screen.getByRole("button", { name: /mutate/i });
    expect(activeBtn).toHaveAttribute("aria-current", "step");
  });

  it("done step is clickable and calls onStepClick", async () => {
    const onStepClick = vi.fn();
    render(
      <WorkflowRail
        title="Design workflow"
        progressPercent={34}
        steps={BASE_STEPS}
        onStepClick={onStepClick}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: /load/i }));
    expect(onStepClick).toHaveBeenCalledWith(0);
  });

  it("lock step button is clickable (spec #17: free rail navigation)", async () => {
    const onStepClick = vi.fn();
    render(
      <WorkflowRail
        title="Design workflow"
        progressPercent={34}
        steps={BASE_STEPS}
        onStepClick={onStepClick}
      />,
    );
    const lockBtn = screen.getByRole("button", { name: /params/i });
    expect(lockBtn).not.toBeDisabled();
    await userEvent.click(lockBtn);
    expect(onStepClick).toHaveBeenCalledWith(2);
  });

  it("renders side-card when provided", () => {
    render(
      <WorkflowRail
        title="Design workflow"
        progressPercent={34}
        steps={BASE_STEPS}
        sideCard={{ title: "Tip", body: "Load a FASTA file first." }}
      />,
    );
    expect(screen.getByText("Tip")).toBeInTheDocument();
    expect(screen.getByText("Load a FASTA file first.")).toBeInTheDocument();
  });

  it("renders mini label for active step", () => {
    render(
      <WorkflowRail title="Design workflow" progressPercent={34} steps={BASE_STEPS} />,
    );
    expect(screen.getByText("now")).toBeInTheDocument();
  });
});
