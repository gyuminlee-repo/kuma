/**
 * settingsThemeSync — ThemeToggle 의 localStorage 키와 DOM 적용 로직을 공유하는 헬퍼.
 *
 * ThemeToggle.tsx 내부 함수 applyTheme 은 export 되지 않으므로
 * 동일 로직을 여기 복제하여 settingsSlice 에서 참조한다.
 * THEME_STORAGE_KEY 는 ThemeToggle 에서 re-export 한다.
 */
export { THEME_STORAGE_KEY } from "../components/ui/ThemeToggle";

/**
 * <html> 에 .dark 클래스를 적용한다.
 * ThemeToggle 내부 applyTheme 과 동일 로직.
 */
export function applyThemeValue(theme: "light" | "dark" | "system"): void {
  const resolved =
    theme === "system"
      ? window.matchMedia("(prefers-color-scheme: dark)").matches
        ? "dark"
        : "light"
      : theme;
  const root = document.documentElement;
  if (resolved === "dark") {
    root.classList.add("dark");
  } else {
    root.classList.remove("dark");
  }
}
