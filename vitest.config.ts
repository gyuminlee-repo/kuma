import { defineConfig } from "vitest/config";
import { resolve } from "path";
import react from "@vitejs/plugin-react-swc";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": resolve(__dirname, "src"),
      "@tauri-apps/plugin-shell": resolve(__dirname, "scripts/stubs/shell.ts"),
      "@tauri-apps/plugin-dialog": resolve(__dirname, "scripts/stubs/dialog.ts"),
      "@tauri-apps/api/webview": resolve(__dirname, "scripts/stubs/webview.ts"),
      "@tauri-apps/api/window": resolve(__dirname, "scripts/stubs/webview.ts"),
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: [],
    globals: true,
    include: ["src/**/*.test.{ts,tsx}", "tests/**/*.test.ts"],
    exclude: ["tests/mame/e2e/**/*.spec.ts", "node_modules/**"],
  },
  define: {
    __APP_VERSION__: JSON.stringify("0.0.0-test"),
  },
});
