/**
 * networkSettings.ts — 네트워크 동의 및 오프라인 모드 설정 영속화.
 *
 * localStorage 키 "kuma:network_settings" 에 저장.
 * Tauri plugin-fs 의존 없이 동작하므로 dev/prod 모두 사용 가능.
 */

export interface NetworkSettings {
  /** 외부 서비스 호출 동의 여부 */
  networkConsentGranted: boolean;
  /** 동의 시각 (ISO8601). null = 미동의 */
  networkConsentTimestamp: string | null;
  /** 오프라인 모드 (true = 외부 호출 차단) */
  offlineMode: boolean;
}

const STORAGE_KEY = "kuma:network_settings";

const DEFAULT_SETTINGS: NetworkSettings = {
  networkConsentGranted: false,
  networkConsentTimestamp: null,
  offlineMode: false,
};

export function loadNetworkSettings(): NetworkSettings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { ...DEFAULT_SETTINGS };
    const parsed = JSON.parse(raw) as Partial<NetworkSettings>;
    return {
      networkConsentGranted: parsed.networkConsentGranted ?? false,
      networkConsentTimestamp: parsed.networkConsentTimestamp ?? null,
      offlineMode: parsed.offlineMode ?? false,
    };
  } catch {
    return { ...DEFAULT_SETTINGS };
  }
}

export function saveNetworkSettings(settings: NetworkSettings): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
  } catch {
    // localStorage 사용 불가 환경 — 무시
  }
}
