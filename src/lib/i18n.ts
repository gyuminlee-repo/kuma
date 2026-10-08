/**
 * i18n — Locale 설정 슬롯 + i18next 초기화
 *
 * localStorage key: "kuma:locale"
 * 지원 값: SUPPORTED_LOCALES 전체 + "system"
 *
 * 번들 최적화: `en`(fallback)만 정적으로 번들하고, 나머지 로케일은
 * 선택 시점에 동적 import 로 별도 청크에서 가져온다. 초기 진입 번들에서
 * ~9개 로케일 JSON(각 ~95KB) 을 제외해 메인 청크 크기를 크게 줄인다.
 */
import i18next from "i18next";
import { initReactI18next } from "react-i18next";
import en from "../locales/en.json";

export const SUPPORTED_LOCALES = [
  "en", "ko", "zh-CN", "zh-TW", "ja", "es", "de", "fr", "pt-BR", "ru",
] as const;
export type ActiveLocale = (typeof SUPPORTED_LOCALES)[number];
export type Locale = ActiveLocale | "system";

const LOCALE_KEY = "kuma:locale";

// `en` is the statically bundled fallback. Every other locale is split into
// its own chunk and fetched only when actually selected.
type LazyLocale = Exclude<ActiveLocale, "en">;

const LOCALE_LOADERS: Record<LazyLocale, () => Promise<{ default: Record<string, unknown> }>> = {
  ko: () => import("../locales/ko.json"),
  "zh-CN": () => import("../locales/zh-CN.json"),
  "zh-TW": () => import("../locales/zh-TW.json"),
  ja: () => import("../locales/ja.json"),
  es: () => import("../locales/es.json"),
  de: () => import("../locales/de.json"),
  fr: () => import("../locales/fr.json"),
  "pt-BR": () => import("../locales/pt-BR.json"),
  ru: () => import("../locales/ru.json"),
};

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

/**
 * 대상 로케일 리소스 번들을 보장한다. `en` 은 이미 번들되어 있고,
 * 나머지는 동적 import 후 addResourceBundle 로 주입한다(중복 로드 방지).
 * 청크 로드 실패 시 조용히 en fallback 으로 동작한다.
 */
async function ensureLocaleLoaded(locale: ActiveLocale): Promise<void> {
  if (locale === "en") return;
  if (i18next.hasResourceBundle(locale, "translation")) return;
  try {
    const mod = await LOCALE_LOADERS[locale]();
    i18next.addResourceBundle(locale, "translation", mod.default, true, true);
  } catch {
    // best-effort: en fallback 으로 동작
  }
}

function applyActiveLocale(): void {
  const active = resolveActiveLocale();
  void ensureLocaleLoaded(active).then(() => i18next.changeLanguage(active));
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
  applyActiveLocale();
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

/**
 * i18next 초기화. fallback(en) 리소스만 즉시 로드한 뒤 활성 로케일 청크를
 * 비동기로 가져와 적용한다. 활성 로케일이 준비된 후에 resolve 되므로
 * 호출 측은 렌더 직전에 await 하여 영어 깜빡임을 피할 수 있다.
 */
export async function initI18n(resolvedLng: string): Promise<void> {
  await i18next.use(initReactI18next).init({
    resources: { en: { translation: en } },
    lng: "en",
    fallbackLng: "en",
    interpolation: { escapeValue: false },
  });
  const target = matchSupportedLocale(resolvedLng);
  if (target !== "en") {
    await ensureLocaleLoaded(target);
    await i18next.changeLanguage(target);
  }
}

export default i18next;
