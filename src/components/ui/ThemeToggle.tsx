/**
 * ThemeToggle
 *
 * 라이트 / 다크 / 시스템 3-way 테마 전환 컴포넌트.
 * - localStorage key: "theme"
 * - "system" 선택 시 prefers-color-scheme 미디어 쿼리를 구독하여 자동 추종
 * - <html> 엘리먼트에 .dark 클래스를 토글 (Tailwind darkMode: ["class"] 방식)
 */
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "./dropdown-menu";
import { Button } from "./button";
import { useAppStore } from "../../store/appStore";
import {
  THEME_STORAGE_KEY,
  applyThemeValue,
  readStoredTheme,
  useThemeStore,
  type Theme,
} from "../../store/settingsThemeSync";

export type { Theme };
export { THEME_STORAGE_KEY };

/**
 * useTheme
 *
 * 테마 읽기/쓰기 훅. 값은 호출부마다 따로 들지 않고 `useThemeStore` 하나에서
 * 읽으므로 메뉴 두 곳의 체크 표시가 어긋나지 않는다. 쓰기는 모든 진입점이
 * `setThemePreference` 하나를 거쳐 localStorage 와 preferences.json 에 함께
 * 남긴다. 예전에는 메뉴 서브메뉴가 localStorage 에만 써서 재시작 때 설정 파일
 * 값으로 되돌아갔다.
 */
export function useTheme(): { theme: Theme; setTheme: (next: Theme) => void } {
  const theme = useThemeStore((s) => s.theme);
  const setTheme = useAppStore((s) => s.setThemePreference);

  useEffect(() => {
    if (theme !== "system") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = () => applyThemeValue("system");
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, [theme]);

  return { theme, setTheme };
}

/**
 * useResolvedTheme
 *
 * 현재 실제로 적용된(resolved) 테마("light" | "dark")를 관찰하는 훅.
 *
 * 선택값("system" 포함)은 useThemeStore 가 들지만 "system" 이 실제로 무엇으로
 * 풀렸는지는 OS 설정에 달려 있다. 풀린 결과가 합류하는 곳은 <html> 엘리먼트의
 * .dark 클래스이므로 이를 MutationObserver로 직접 관찰한다.
 */
export function useResolvedTheme(): "light" | "dark" {
  const [resolved, setResolved] = useState<"light" | "dark">(() =>
    document.documentElement.classList.contains("dark") ? "dark" : "light",
  );

  useEffect(() => {
    const root = document.documentElement;
    const observer = new MutationObserver(() => {
      const next = root.classList.contains("dark") ? "dark" : "light";
      setResolved((prev) => (prev === next ? prev : next));
    });
    observer.observe(root, { attributes: true, attributeFilter: ["class"] });
    return () => observer.disconnect();
  }, []);

  return resolved;
}

const THEME_LABEL_KEYS: Record<Theme, string> = {
  light: "themeToggle.labelLight",
  dark: "themeToggle.labelDark",
  system: "themeToggle.labelSystem",
};

/** 테마 아이콘 (SVG inline) */
function ThemeIcon({ theme }: { theme: Theme }) {
  if (theme === "dark") {
    return (
      <svg
        xmlns="http://www.w3.org/2000/svg"
        width="14"
        height="14"
        viewBox="0 0 24 24"
        fill="currentColor"
        aria-hidden="true"
      >
        <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
      </svg>
    );
  }
  if (theme === "light") {
    return (
      <svg
        xmlns="http://www.w3.org/2000/svg"
        width="14"
        height="14"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <circle cx="12" cy="12" r="5" />
        <line x1="12" y1="1" x2="12" y2="3" />
        <line x1="12" y1="21" x2="12" y2="23" />
        <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
        <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
        <line x1="1" y1="12" x2="3" y2="12" />
        <line x1="21" y1="12" x2="23" y2="12" />
        <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
        <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
      </svg>
    );
  }
  // system
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <rect x="2" y="3" width="20" height="14" rx="2" ry="2" />
      <line x1="8" y1="21" x2="16" y2="21" />
      <line x1="12" y1="17" x2="12" y2="21" />
    </svg>
  );
}

export interface ThemeToggleProps {
  /** 버튼 표시 방식. "icon": 아이콘만, "icon-label": 아이콘+텍스트. 기본 "icon" */
  variant?: "icon" | "icon-label";
}

export function ThemeToggle({ variant = "icon" }: ThemeToggleProps) {
  const { t } = useTranslation();
  const { theme, setTheme } = useTheme();

  function getThemeLabel(th: Theme): string {
    return t(THEME_LABEL_KEYS[th]);
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          className="h-control px-2 gap-1.5 text-foreground/70 hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
          aria-label={t("themeToggle.currentThemeAria", { label: getThemeLabel(theme) })}
        >
          <ThemeIcon theme={theme} />
          {variant === "icon-label" && (
            <span className="text-caption">{getThemeLabel(theme)}</span>
          )}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {(["light", "dark", "system"] as Theme[]).map((th) => (
          <DropdownMenuItem
            key={th}
            onClick={() => setTheme(th)}
            aria-current={theme === th ? "true" : undefined}
          >
            <span className="flex items-center gap-2">
              <ThemeIcon theme={th} />
              <span>{getThemeLabel(th)}</span>
              {theme === th && (
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  width="12"
                  height="12"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  className="ml-auto text-primary"
                  aria-hidden="true"
                >
                  <polyline points="20 6 9 17 4 12" />
                </svg>
              )}
            </span>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/**
 * initTheme
 *
 * App.tsx 부트스트랩에서 호출. React 마운트 전에 플래시 없이 테마 적용.
 */
export function initTheme(): void {
  applyThemeValue(readStoredTheme());
}
