// Provides browser APIs that jsdom does not implement so libraries depending
// on them (react-resizable-panels uses ResizeObserver) don't crash in tests.

// jest-dom custom matchers (toBeInTheDocument, toHaveAttribute, etc.)
import "@testing-library/jest-dom";

// requestAnimationFrame: jsdom doesn't implement timing properly.
// Replace with synchronous stub so drag-event tests work without fakeTimers.
globalThis.requestAnimationFrame = (cb: FrameRequestCallback): number => {
  cb(performance.now());
  return 0;
};
globalThis.cancelAnimationFrame = (_: number): void => {};

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
