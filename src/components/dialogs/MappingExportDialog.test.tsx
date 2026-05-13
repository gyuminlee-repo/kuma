import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MappingExportDialog } from "./MappingExportDialog";

function renderDialog(props: Partial<React.ComponentProps<typeof MappingExportDialog>> = {}) {
  return render(
    <MappingExportDialog
      open={true}
      initialFormat="echo"
      onOpenChange={vi.fn()}
      onExport={vi.fn()}
      {...props}
    />,
  );
}

describe("MappingExportDialog — echo max 500 nL", () => {
  it("echo transfer volume input has max=500", () => {
    renderDialog({ initialFormat: "echo" });
    const input = screen.getByRole<HTMLInputElement>("spinbutton");
    expect(Number(input.max)).toBe(500);
  });

  it("echo transfer volume input has min=25", () => {
    renderDialog({ initialFormat: "echo" });
    const input = screen.getByRole<HTMLInputElement>("spinbutton");
    expect(Number(input.min)).toBe(25);
  });

  it("shows Max 500 nL note when echo format is selected", () => {
    renderDialog({ initialFormat: "echo" });
    expect(screen.getByText("(Max 500 nL)")).toBeTruthy();
  });

  it("does not show Max 500 nL note for janus format", () => {
    renderDialog({ initialFormat: "janus" });
    expect(screen.queryByText("(Max 500 nL)")).toBeNull();
  });

  it("janus format has max=10 (µL, unchanged)", () => {
    renderDialog({ initialFormat: "janus" });
    const input = screen.getByRole<HTMLInputElement>("spinbutton");
    expect(Number(input.max)).toBe(10);
  });

  it("calls onExport with clamped value when user types within range", () => {
    const onExport = vi.fn();
    renderDialog({ initialFormat: "echo", onExport });
    const input = screen.getByRole("spinbutton");
    fireEvent.change(input, { target: { value: "250" } });
    fireEvent.click(screen.getByRole("button", { name: /export/i }));
    expect(onExport).toHaveBeenCalledWith(
      expect.objectContaining({ format: "echo", transferVol: 250 }),
    );
  });
});
