/**
 * i18n — Locale 설정 슬롯 + i18next 초기화
 *
 * 본 모듈은 locale 설정 슬롯과 i18next 초기화 헬퍼를 제공한다.
 * initI18n(resolvedLng)을 main.tsx에서 앱 마운트 전 호출한다.
 *
 * localStorage key: "kuma:locale"
 * 지원 값: "en" | "ko" | "system"
 */
import i18next from "i18next";
import { initReactI18next } from "react-i18next";
import en from "../locales/en.json";
import ko from "../locales/ko.json";

export type Locale = "en" | "ko" | "system";

const LOCALE_KEY = "kuma:locale";

/** localStorage에서 현재 locale 읽기. 저장값이 없거나 유효하지 않으면 "system" 반환 */
export function getLocale(): Locale {
  try {
    const stored = localStorage.getItem(LOCALE_KEY);
    if (stored === "en" || stored === "ko" || stored === "system") {
      return stored;
    }
  } catch {
    // localStorage 접근 실패 시 시스템 기본값 사용
  }
  return "system";
}

/** locale 설정을 localStorage에 저장 */
export function setLocale(locale: Locale): void {
  try {
    localStorage.setItem(LOCALE_KEY, locale);
  } catch {
    // 저장 실패 시 세션 내 동작은 호출 측 상태로 유지
  }
}

/**
 * 실제 활성 locale 결정.
 * "system" 선택 시 navigator.language 를 기반으로 ko/en 분기.
 * 번역 바인딩 도입 시 이 반환값을 사용한다.
 */
export function resolveActiveLocale(): "en" | "ko" {
  const locale = getLocale();
  if (locale === "ko") return "ko";
  if (locale === "en") return "en";
  // system: navigator.language 가 ko로 시작하면 ko, 그 외 en
  try {
    return navigator.language?.toLowerCase().startsWith("ko") ? "ko" : "en";
  } catch {
    return "en";
  }
}

/**
 * i18next 초기화.
 * main.tsx에서 ReactDOM.createRoot 이전에 await 없이 호출 가능.
 * (react-i18next suspense 없이 동기 초기화)
 */
export function initI18n(resolvedLng: string): void {
  void i18next.use(initReactI18next).init({
    resources: {
      en: { translation: en },
      ko: { translation: ko },
    },
    lng: resolvedLng,
    fallbackLng: "en",
    interpolation: { escapeValue: false },
  });
}
