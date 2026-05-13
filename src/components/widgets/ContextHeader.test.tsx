import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ContextHeader } from "./ContextHeader";

describe("ContextHeader", () => {
  it("renders without crashing", () => {
    render(<ContextHeader title="Load Construct" />);
    expect(screen.getByText("Load Construct")).toBeInTheDocument();
  });

  it("renders subtitle when provided", () => {
    render(<ContextHeader title="Load Construct" subtitle="Step 1 of 4" />);
    expect(screen.getByText("Step 1 of 4")).toBeInTheDocument();
  });

  it("does not render subtitle when omitted", () => {
    render(<ContextHeader title="Load Construct" />);
    expect(screen.queryByText("Step 1 of 4")).toBeNull();
  });

  it("renders action buttons when provided", async () => {
    const onAction = vi.fn();
    render(
      <ContextHeader
        title="Load Construct"
        actions={<button onClick={onAction}>Import</button>}
      />,
    );
    const btn = screen.getByRole("button", { name: "Import" });
    expect(btn).toBeInTheDocument();
    await userEvent.click(btn);
    expect(onAction).toHaveBeenCalledOnce();
  });

  it("header landmark has aria-label screen-header", () => {
    render(<ContextHeader title="Load Construct" />);
    expect(
      screen.getByRole("banner", { name: "screen-header" }),
    ).toBeInTheDocument();
  });
});
