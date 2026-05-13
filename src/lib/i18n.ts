/**
 * i18n — Locale 설정 슬롯 + i18next 초기화
 *
 * localStorage key: "kuma:locale"
 * 지원 값: SUPPORTED_LOCALES 전체 + "system"
 */
import i18next from "i18next";
import { initReactI18next } from "react-i18next";
import en from "../locales/en.json";
import ko from "../locales/ko.json";
import zhCN from "../locales/zh-CN.json";
import zhTW from "../locales/zh-TW.json";
import ja from "../locales/ja.json";
import es from "../locales/es.json";
import de from "../locales/de.json";
import fr from "../locales/fr.json";
import ptBR from "../locales/pt-BR.json";
import ru from "../locales/ru.json";

export const SUPPORTED_LOCALES = [
  "en", "ko", "zh-CN", "zh-TW", "ja", "es", "de", "fr", "pt-BR", "ru",
] as const;
export type ActiveLocale = (typeof SUPPORTED_LOCALES)[number];
export type Locale = ActiveLocale | "system";

const LOCALE_KEY = "kuma:locale";

function matchSupportedLocale(tag: string | undefined | null): ActiveLocale {
  if (!tag) return "en";
  const lower = tag.toLowerCase();
  const exact = SUPPORTED_LOCALES.find((l) => l.toLowerCase() === lower);
  if (exact) return exact;
  if (lower.startsWith("zh")) {
    if (lower.includes("tw") || lower.includes("hk") || lower.includes("hant")) return "zh-TW";
    return "zh-CN";
  }
  if (lower.startsWith("pt")) return "pt-BR";
  const base = lower.split("-")[0];
  const baseMatch = SUPPORTED_LOCALES.find((l) => l.toLowerCase().split("-")[0] === base);
  return baseMatch ?? "en";
}

export function getLocale(): Locale {
  try {
    const stored = localStorage.getItem(LOCALE_KEY);
    if (stored === "system") return "system";
    if (stored && (SUPPORTED_LOCALES as readonly string[]).includes(stored)) {
      return stored as ActiveLocale;
    }
  } catch {
    // localStorage 접근 실패 시 시스템 기본값 사용
  }
  return "system";
}

export function setLocale(locale: Locale): void {
  try {
    localStorage.setItem(LOCALE_KEY, locale);
  } catch {
    // 저장 실패 시 세션 내 동작은 호출 측 상태로 유지
  }
  void i18next.changeLanguage(resolveActiveLocale());
}

export function resolveActiveLocale(): ActiveLocale {
  const locale = getLocale();
  if (locale !== "system") return locale;
  try {
    return matchSupportedLocale(navigator.language);
  } catch {
    return "en";
  }
}

export function initI18n(resolvedLng: string): void {
  void i18next.use(initReactI18next).init({
    resources: {
      en: { translation: en },
      ko: { translation: ko },
      "zh-CN": { translation: zhCN },
      "zh-TW": { translation: zhTW },
      ja: { translation: ja },
      es: { translation: es },
      de: { translation: de },
      fr: { translation: fr },
      "pt-BR": { translation: ptBR },
      ru: { translation: ru },
    },
    lng: resolvedLng,
    fallbackLng: "en",
    interpolation: { escapeValue: false },
  });
}
