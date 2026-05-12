/**
 * LocaleToggle
 *
 * English / 한국어 / System 3-way 언어 설정 슬롯 컴포넌트.
 * - localStorage key: "kuma:locale"
 * - 실제 번역은 현재 미구현. 향후 react-i18next 등 도입 시 i18n.resolveActiveLocale() 바인딩.
 */
import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "./dropdown-menu";
import { Button } from "./button";
import { getLocale, setLocale, type Locale } from "../../lib/i18n";

const LOCALE_LABELS: Record<Locale, string> = {
  en: "English",
  ko: "한국어",
  system: "System",
};

/** 언어 선택 아이콘 (globe SVG) */
function GlobeIcon({ size = 14 }: { size?: number }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="10" />
      <line x1="2" y1="12" x2="22" y2="12" />
      <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
    </svg>
  );
}

export interface LocaleToggleProps {
  /** 버튼 표시 방식. "icon": 아이콘만, "icon-label": 아이콘+텍스트. 기본 "icon" */
  variant?: "icon" | "icon-label";
}

export function LocaleToggle({ variant = "icon" }: LocaleToggleProps) {
  const { t } = useTranslation();
  const [locale, setLocaleState] = useState<Locale>(getLocale);

  function handleSelect(next: Locale) {
    setLocale(next);
    setLocaleState(next);
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          className="h-control px-2 gap-1.5 text-foreground/70 hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
          aria-label={t("localeToggle.currentLanguageAria", { label: LOCALE_LABELS[locale] })}
        >
          <GlobeIcon />
          {variant === "icon-label" && (
            <span className="text-caption">{LOCALE_LABELS[locale]}</span>
          )}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {(["en", "ko", "system"] as Locale[]).map((l) => (
          <DropdownMenuItem
            key={l}
            onClick={() => handleSelect(l)}
            aria-current={locale === l ? "true" : undefined}
          >
            <span className="flex items-center gap-2">
              <GlobeIcon size={12} />
              <span>{LOCALE_LABELS[l]}</span>
              {locale === l && (
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
