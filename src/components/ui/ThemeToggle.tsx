/**
 * ThemeToggle
 *
 * 라이트 / 다크 / 시스템 3-way 테마 전환 컴포넌트.
 * - localStorage key: "theme"
 * - "system" 선택 시 prefers-color-scheme 미디어 쿼리를 구독하여 자동 추종
 * - <html> 엘리먼트에 .dark 클래스를 토글 (Tailwind darkMode: ["class"] 방식)
 */
import { useEffect, useState } from "react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "./dropdown-menu";
import { Button } from "./button";

export type Theme = "light" | "dark" | "system";

const STORAGE_KEY = "theme";

/** 현재 적용되어야 할 실제 테마 결정 (system → OS 설정 참조) */
function resolveTheme(theme: Theme): "light" | "dark" {
  if (theme === "system") {
    return window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";
  }
  return theme;
}

/** <html>에 .dark 클래스 적용 */
function applyTheme(theme: Theme): void {
  const resolved = resolveTheme(theme);
  const root = document.documentElement;
  if (resolved === "dark") {
    root.classList.add("dark");
  } else {
    root.classList.remove("dark");
  }
}

/** localStorage에서 초기 테마 읽기 */
function readStoredTheme(): Theme {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === "light" || stored === "dark" || stored === "system") {
      return stored;
    }
  } catch {
    // localStorage 접근 실패 시 시스템 기본값 사용
  }
  return "system";
}

const THEME_LABELS: Record<Theme, string> = {
  light: "Light",
  dark: "Dark",
  system: "System",
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
  const [theme, setTheme] = useState<Theme>(readStoredTheme);

  // 초기 마운트 + 시스템 테마 변경 구독
  useEffect(() => {
    applyTheme(theme);

    if (theme !== "system") {
      return;
    }

    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = () => applyTheme("system");
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, [theme]);

  function handleSelect(next: Theme) {
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // 저장 실패해도 세션 내 동작은 유지
    }
    setTheme(next);
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          className="h-control px-2 gap-1.5 text-foreground/70 hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
          aria-label={`현재 테마: ${THEME_LABELS[theme]}. 테마 변경`}
        >
          <ThemeIcon theme={theme} />
          {variant === "icon-label" && (
            <span className="text-caption">{THEME_LABELS[theme]}</span>
          )}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {(["light", "dark", "system"] as Theme[]).map((t) => (
          <DropdownMenuItem
            key={t}
            onClick={() => handleSelect(t)}
            aria-current={theme === t ? "true" : undefined}
          >
            <span className="flex items-center gap-2">
              <ThemeIcon theme={t} />
              <span>{THEME_LABELS[t]}</span>
              {theme === t && (
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
  applyTheme(readStoredTheme());
}
