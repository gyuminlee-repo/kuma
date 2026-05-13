/**
 * localeUtils — locale 관련 유틸리티 함수.
 *
 * [source: spec Phase G — #14 BOM OS Locale 자동]
 */

import i18n from "../lib/i18n";

/**
 * 현재 i18n 언어가 한국어인지 반환한다.
 * BOM 기본값 등 locale 의존 기본값 설정에 사용.
 */
export function localeIsKorean(): boolean {
  return i18n.language?.startsWith("ko") ?? false;
}
