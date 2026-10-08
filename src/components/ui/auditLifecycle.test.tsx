import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ExpandableText } from "@/components/ui/ExpandableText";
import { InfoPopover } from "@/components/ui/InfoPopover";
import { Progress } from "@/components/ui/progress";
import { ResizeHandle } from "@/components/shell/ResizeHandle";

beforeEach(() => {
  document.body.classList.remove("resizing-sidebar");
  document.body.style.cursor = "";
  document.body.style.userSelect = "";
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  document.body.classList.remove("resizing-sidebar");
  document.body.style.cursor = "";
  document.body.style.userSelect = "";
});

function openOverflowText() {
  vi.spyOn(HTMLElement.prototype, "scrollWidth", "get").mockReturnValue(200);
  vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockReturnValue(100);
  render(<ExpandableText text="Full audit message" label="Notes" />);
  const trigger = screen.getByRole("button");
  fireEvent.click(trigger);
  expect(screen.getByTestId("expandable-text-panel")).toBeInTheDocument();
  return trigger;
}

describe("audit component event and accessibility contracts", () => {
  it("keeps dragging across callback updates and commits the final queued position", () => {
    let frame: FrameRequestCallback = () => {};
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((callback) => { frame = callback; return 91; });
    vi.spyOn(window, "cancelAnimationFrame").mockImplementation(() => {});
    const first = vi.fn();
    const next = vi.fn();
    const commit = vi.fn();
    const view = render(<ResizeHandle width={240} min={180} max={480} onResize={first} onCommit={commit} />);
    fireEvent.mouseDown(screen.getByRole("separator"));
    fireEvent.mouseMove(document, { clientX: 300 });
    frame(0);
    view.rerender(<ResizeHandle width={300} min={180} max={480} onResize={next} onCommit={commit} />);
    fireEvent.mouseMove(document, { clientX: 350 });
    fireEvent.mouseUp(document);
    expect(next).toHaveBeenLastCalledWith(350);
    expect(commit).toHaveBeenCalledTimes(1);
    expect(document.body).not.toHaveClass("resizing-sidebar");
  });
  it("closes overflow text when Escape reaches document", () => {
    openOverflowText();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByTestId("expandable-text-panel")).not.toBeInTheDocument();
  });

  it("closes overflow text when Escape starts on its trigger", () => {
    const trigger = openOverflowText();
    trigger.focus();
    fireEvent.keyDown(trigger, { key: "Escape" });
    expect(screen.queryByTestId("expandable-text-panel")).not.toBeInTheDocument();
  });

  it("keeps overflow text open when selecting text inside its panel", () => {
    openOverflowText();
    fireEvent.mouseDown(screen.getByTestId("expandable-text-panel"));
    expect(screen.queryByTestId("expandable-text-panel")).toBeInTheDocument();
  });

  it("closes InfoPopover with Escape from its trigger as a control", () => {
    render(<InfoPopover label="Notes" ariaLabel="Explain notes">Detail</InfoPopover>);
    const trigger = screen.getByRole("button");
    fireEvent.click(trigger);
    expect(screen.getByTestId("info-popover")).toBeInTheDocument();
    trigger.focus();
    fireEvent.keyDown(trigger, { key: "Escape" });
    expect(screen.queryByTestId("info-popover")).not.toBeInTheDocument();
  });

  it("clears global resize state after mouseup", () => {
    render(<ResizeHandle width={240} min={180} max={480} onResize={vi.fn()} />);
    fireEvent.mouseDown(screen.getByRole("separator"));
    expect(document.body).toHaveClass("resizing-sidebar");
    fireEvent.mouseUp(document);
    expect(document.body).not.toHaveClass("resizing-sidebar");
    expect(document.body.style.cursor).toBe("");
  });

  it("clears global resize state on unmount during a drag", () => {
    const view = render(<ResizeHandle width={240} min={180} max={480} onResize={vi.fn()} />);
    fireEvent.mouseDown(screen.getByRole("separator"));
    expect(document.body).toHaveClass("resizing-sidebar");
    view.unmount();
    fireEvent.mouseUp(document);
    expect(document.body).not.toHaveClass("resizing-sidebar");
    expect(document.body.style.cursor).toBe("");
  });

  it("exposes the visual progress value to assistive technology", () => {
    render(<Progress value={50} />);
    const bar = screen.getByRole("progressbar");
    expect(bar.firstElementChild).toHaveStyle({ transform: "translateX(-50%)" });
    expect(bar).toHaveAttribute("aria-valuenow", "50");
  });

  it("uses max for both progress accessibility and visual percentage", () => {
    render(<Progress value={50} max={200} />);
    const bar = screen.getByRole("progressbar");
    expect(bar).toHaveAttribute("aria-valuenow", "50");
    expect(bar).toHaveAttribute("aria-valuemax", "200");
    expect(bar.firstElementChild).toHaveStyle({ transform: "translateX(-75%)" });
  });

  it("cancels a queued resize and restores prior body styles on unmount", () => {
    vi.spyOn(window, "requestAnimationFrame").mockReturnValue(91);
    const cancel = vi.spyOn(window, "cancelAnimationFrame");
    const resize = vi.fn();
    document.body.style.cursor = "crosshair";
    document.body.style.userSelect = "text";
    const view = render(<ResizeHandle width={240} min={180} max={480} onResize={resize} />);
    fireEvent.mouseDown(screen.getByRole("separator"));
    fireEvent.mouseMove(document, { clientX: 300 });
    view.unmount();
    expect(cancel).toHaveBeenCalledWith(91);
    expect(resize).not.toHaveBeenCalled();
    expect(document.body.style.cursor).toBe("crosshair");
    expect(document.body.style.userSelect).toBe("text");
  });
});
