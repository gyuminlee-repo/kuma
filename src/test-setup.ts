// Provides browser APIs that jsdom does not implement so libraries depending
// on them (react-resizable-panels uses ResizeObserver) don't crash in tests.

if (typeof globalThis.ResizeObserver === "undefined") {
  class ResizeObserverStub {
    observe(): void {}
    unobserve(): void {}
    disconnect(): void {}
  }
  globalThis.ResizeObserver = ResizeObserverStub as unknown as typeof ResizeObserver;
}

if (typeof globalThis.matchMedia === "undefined") {
  globalThis.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
}

// Initialize i18n with English locale so tests can match the source-of-truth
// labels (en.json values). Without this, useTranslation()'s t() returns keys.
import { initI18n } from "./lib/i18n";
initI18n("en");
