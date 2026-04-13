import { defineConfig } from "vite";
import { resolve } from "path";
import { readFileSync } from "fs";
import react from "@vitejs/plugin-react-swc";

const pkg = JSON.parse(readFileSync(resolve(__dirname, "package.json"), "utf-8"));

export default defineConfig(({ }) => {
  const isMockMode = process.env.MOCK_MODE === "1";

  return {
    plugins: [react()],
    resolve: {
      alias: {
        "@": resolve(__dirname, "src"),
        ...(isMockMode
          ? {
              "@tauri-apps/plugin-shell": resolve(
                __dirname,
                "scripts/stubs/shell.ts",
              ),
              "@tauri-apps/plugin-dialog": resolve(
                __dirname,
                "scripts/stubs/dialog.ts",
              ),
              "@tauri-apps/api/webview": resolve(
                __dirname,
                "scripts/stubs/webview.ts",
              ),
              "@tauri-apps/api/window": resolve(
                __dirname,
                "scripts/stubs/webview.ts",
              ),
            }
          : {}),
      },
    },
    clearScreen: false,
    server: {
      port: 1421,
      strictPort: true,
    },
    envPrefix: ["VITE_", "TAURI_"],
    define: {
      __APP_VERSION__: JSON.stringify(pkg.version),
    },
    build: {
      target: "esnext",
      minify: !process.env.TAURI_DEBUG ? "esbuild" : false,
      sourcemap: !!process.env.TAURI_DEBUG,
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (!id.includes("node_modules")) return undefined;
            if (id.includes("@tanstack/react-table")) return "table-vendor";
            if (id.includes("zustand")) return "store-vendor";
            if (id.includes("@tauri-apps")) return "tauri-vendor";
            if (id.includes("@radix-ui")) return "ui-vendor";
            if (id.includes("react") || id.includes("react-dom")) return "react-vendor";
            return "vendor";
          },
        },
      },
    },
  };
});
