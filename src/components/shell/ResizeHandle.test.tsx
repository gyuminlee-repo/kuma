// Tests for ResizeHandle component
// Run: npx vitest run src/components/shell/ResizeHandle.test.tsx
import { describe, it, expect, vi } from "vitest";
import { render, fireEvent } from "@testing-library/react";
import { ResizeHandle } from "./ResizeHandle";

// Mock react-i18next
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (k: string) => k }),
}));

describe("ResizeHandle", () => {
  it("renders a separator with correct ARIA attributes", () => {
    const { getByRole } = render(
      <ResizeHandle width={240} min={180} max={480} onResize={vi.fn()} />,
    );
    const h = getByRole("separator");
    expect(h).toBeInTheDocument();
    expect(h).toHaveAttribute("aria-orientation", "vertical");
    expect(h).toHaveAttribute("aria-valuenow", "240");
    expect(h).toHaveAttribute("aria-valuemin", "180");
    expect(h).toHaveAttribute("aria-valuemax", "480");
  });

  it("calls onResize on mousemove during drag", () => {
    const onResize = vi.fn();
    const { getByRole } = render(
      <ResizeHandle width={240} min={180} max={480} onResize={onResize} />,
    );
    const h = getByRole("separator");
    fireEvent.mouseDown(h, { clientX: 240 });
    fireEvent.mouseMove(document, { clientX: 300 });
    fireEvent.mouseUp(document);
    expect(onResize).toHaveBeenCalledWith(300);
  });

  it("clamps to min on mousemove below min", () => {
    const onResize = vi.fn();
    const { getByRole } = render(
      <ResizeHandle width={240} min={180} max={480} onResize={onResize} />,
    );
    const h = getByRole("separator");
    fireEvent.mouseDown(h, { clientX: 240 });
    fireEvent.mouseMove(document, { clientX: 50 });
    fireEvent.mouseUp(document);
    expect(onResize).toHaveBeenLastCalledWith(180);
  });

  it("clamps to max on mousemove above max", () => {
    const onResize = vi.fn();
    const { getByRole } = render(
      <ResizeHandle width={240} min={180} max={480} onResize={onResize} />,
    );
    const h = getByRole("separator");
    fireEvent.mouseDown(h, { clientX: 240 });
    fireEvent.mouseMove(document, { clientX: 9999 });
    fireEvent.mouseUp(document);
    expect(onResize).toHaveBeenLastCalledWith(480);
  });

  it("ArrowRight increments width by 1", () => {
    const onResize = vi.fn();
    const { getByRole } = render(
      <ResizeHandle width={240} min={180} max={480} onResize={onResize} />,
    );
    fireEvent.keyDown(getByRole("separator"), { key: "ArrowRight" });
    expect(onResize).toHaveBeenCalledWith(241);
  });

  it("ArrowLeft decrements width by 1", () => {
    const onResize = vi.fn();
    const { getByRole } = render(
      <ResizeHandle width={240} min={180} max={480} onResize={onResize} />,
    );
    fireEvent.keyDown(getByRole("separator"), { key: "ArrowLeft" });
    expect(onResize).toHaveBeenCalledWith(239);
  });

  it("Shift+ArrowRight increments by 10", () => {
    const onResize = vi.fn();
    const { getByRole } = render(
      <ResizeHandle width={240} min={180} max={480} onResize={onResize} />,
    );
    fireEvent.keyDown(getByRole("separator"), { key: "ArrowRight", shiftKey: true });
    expect(onResize).toHaveBeenCalledWith(250);
  });

  it("Home moves to min", () => {
    const onResize = vi.fn();
    const { getByRole } = render(
      <ResizeHandle width={240} min={180} max={480} onResize={onResize} />,
    );
    fireEvent.keyDown(getByRole("separator"), { key: "Home" });
    expect(onResize).toHaveBeenCalledWith(180);
  });

  it("End moves to max", () => {
    const onResize = vi.fn();
    const { getByRole } = render(
      <ResizeHandle width={240} min={180} max={480} onResize={onResize} />,
    );
    fireEvent.keyDown(getByRole("separator"), { key: "End" });
    expect(onResize).toHaveBeenCalledWith(480);
  });
});
