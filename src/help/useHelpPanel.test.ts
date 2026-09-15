import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { OPEN_HELP_EVENT } from "./events";
import { useHelpPanel } from "./useHelpPanel";

function emit(detail?: unknown) {
  act(() => {
    window.dispatchEvent(new CustomEvent(OPEN_HELP_EVENT, { detail }));
  });
}

describe("useHelpPanel", () => {
  it("starts closed", () => {
    const { result } = renderHook(() => useHelpPanel());
    expect(result.current.open).toBe(false);
  });

  it("opens at the topic named in the event", () => {
    const { result } = renderHook(() => useHelpPanel());
    emit({ topic: "mame-02-review" });
    expect(result.current.open).toBe(true);
    expect(result.current.topic).toBe("mame-02-review");
  });

  it("replaces the topic and stays open on a second request", () => {
    const { result } = renderHook(() => useHelpPanel());
    emit({ topic: "mame-02-review" });
    emit({ topic: "kuro-03-params" });
    expect(result.current.open).toBe(true);
    expect(result.current.topic).toBe("kuro-03-params");
  });

  it("closes, and lets the panel change topic itself", () => {
    const { result } = renderHook(() => useHelpPanel());
    emit({ topic: "mame-02-review" });
    act(() => result.current.setTopic("mame-pipeline"));
    expect(result.current.topic).toBe("mame-pipeline");
    act(() => result.current.close());
    expect(result.current.open).toBe(false);
  });

  it.each([[undefined], [null], [{}], [{ topic: 42 }], ["mame-02-review"]])(
    "ignores a malformed detail %j",
    (detail) => {
      const { result } = renderHook(() => useHelpPanel());
      emit(detail);
      expect(result.current.open).toBe(false);
    },
  );

  it("removes its listener on unmount", () => {
    const remove = vi.spyOn(window, "removeEventListener");
    const { unmount } = renderHook(() => useHelpPanel());
    unmount();
    expect(remove).toHaveBeenCalledWith(OPEN_HELP_EVENT, expect.any(Function));
    remove.mockRestore();
  });
});
