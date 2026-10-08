/**
 * settingsSlice — unit tests
 *
 * mapThemeToBundle / mapThemeFromBundle 변환 로직 검증.
 * IPC 호출은 Tauri bridge 없이 실행 불가하므로 변환 함수만 검증한다.
 */
import { describe, it, expect } from "vitest";
import { mapThemeToBundle, mapThemeFromBundle } from "./settingsSlice";

describe("mapThemeToBundle", () => {
  it("converts system to auto", () => {
    expect(mapThemeToBundle("system")).toBe("auto");
  });
  it("passes light through", () => {
    expect(mapThemeToBundle("light")).toBe("light");
  });
  it("passes dark through", () => {
    expect(mapThemeToBundle("dark")).toBe("dark");
  });
  it("unknown value defaults to auto", () => {
    expect(mapThemeToBundle("unknown")).toBe("auto");
  });
});

describe("mapThemeFromBundle", () => {
  it("converts auto to system", () => {
    expect(mapThemeFromBundle("auto")).toBe("system");
  });
  it("passes light through", () => {
    expect(mapThemeFromBundle("light")).toBe("light");
  });
  it("passes dark through", () => {
    expect(mapThemeFromBundle("dark")).toBe("dark");
  });
  it("undefined defaults to system", () => {
    expect(mapThemeFromBundle(undefined)).toBe("system");
  });
});

describe("round-trip conversion", () => {
  it("system → auto → system", () => {
    const bundleTheme = mapThemeToBundle("system");
    const uiTheme = mapThemeFromBundle(bundleTheme);
    expect(uiTheme).toBe("system");
  });
  it("light → light → light", () => {
    const bundleTheme = mapThemeToBundle("light");
    const uiTheme = mapThemeFromBundle(bundleTheme);
    expect(uiTheme).toBe("light");
  });
  it("dark → dark → dark", () => {
    const bundleTheme = mapThemeToBundle("dark");
    const uiTheme = mapThemeFromBundle(bundleTheme);
    expect(uiTheme).toBe("dark");
  });
});
