import { defineConfig } from "@playwright/test";

if (!process.env.MAME_E2E_BASE_URL) {
  throw new Error("Set MAME_E2E_BASE_URL to your dedicated MOCK_MODE=1 Vite server");
}

export default defineConfig({
  testDir: ".",
  testMatch: "*.spec.ts",
  outputDir: "./artifacts/results",
  reporter: [["list"]],
  workers: 1,
  retries: 0,
  timeout: 60_000,
  expect: { timeout: 15_000 },
  use: {
    baseURL: process.env.MAME_E2E_BASE_URL,
    browserName: "chromium",
    locale: "en-US",
    viewport: { width: 1440, height: 1000 },
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
    launchOptions: process.env.MAME_E2E_CHROMIUM
      ? { executablePath: process.env.MAME_E2E_CHROMIUM }
      : {},
  },
});
