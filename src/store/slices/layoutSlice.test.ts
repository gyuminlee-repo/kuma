// Tests for layoutSlice / layoutStore
// Run: pnpm vitest run src/store/slices/layoutSlice.test.ts
import { describe, it, expect, beforeEach } from "vitest";
import { create } from "zustand";
import { persist } from "zustand/middleware";
import { createLayoutSlice, type LayoutSlice } from "./layoutSlice";

describe("layoutSlice", () => {
  beforeEach(() => localStorage.clear());

  it("starts with sidebarWidth null", () => {
    const useStore = create<LayoutSlice>()(createLayoutSlice);
    expect(useStore.getState().sidebarWidth).toBeNull();
  });

  it("setSidebarWidth persists to localStorage", () => {
    const useStore = create<LayoutSlice>()(
      persist(createLayoutSlice, { name: "test.layout.v1" }),
    );
    useStore.getState().setSidebarWidth(300);
    expect(useStore.getState().sidebarWidth).toBe(300);
    expect(
      JSON.parse(localStorage.getItem("test.layout.v1")!).state.sidebarWidth,
    ).toBe(300);
  });

  it("setSidebarWidth(null) reverts to null", () => {
    const useStore = create<LayoutSlice>()(createLayoutSlice);
    useStore.getState().setSidebarWidth(300);
    useStore.getState().setSidebarWidth(null);
    expect(useStore.getState().sidebarWidth).toBeNull();
  });

  it("computedDefault starts at SIDEBAR_DEFAULT_WIDTH", () => {
    const useStore = create<LayoutSlice>()(createLayoutSlice);
    // SIDEBAR_DEFAULT_WIDTH is 180 (from build script) or fallback 240
    expect(useStore.getState().computedDefault).toBeGreaterThanOrEqual(180);
  });

  it("setComputedDefault updates computedDefault", () => {
    const useStore = create<LayoutSlice>()(createLayoutSlice);
    useStore.getState().setComputedDefault(250);
    expect(useStore.getState().computedDefault).toBe(250);
  });
});
