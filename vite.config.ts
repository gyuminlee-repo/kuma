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
    },
  };
});
