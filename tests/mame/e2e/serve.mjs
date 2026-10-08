import { build, preview } from "vite";
import { resolve } from "node:path";
import { access } from "node:fs/promises";

process.env.MOCK_MODE = "1";
const dataDir = resolve(process.argv[2] ?? process.env.MAME_E2E_DATA_DIR ?? "scripts");
await Promise.all(["real-data.json", "mame-real-data.json"].map((file) => access(resolve(dataDir, file))));
await build({
  cacheDir: "tests/mame/e2e/artifacts/vite-cache",
  optimizeDeps: { entries: ["index.html"] },
  resolve: { alias: {
    "../real-data.json": resolve(dataDir, "real-data.json"),
    "../mame-real-data.json": resolve(dataDir, "mame-real-data.json"),
  } },
  build: { outDir: "tests/mame/e2e/artifacts/dist", emptyOutDir: true },
});
const server = await preview({
  build: { outDir: "tests/mame/e2e/artifacts/dist" },
  preview: { host: "0.0.0.0", port: 15473, strictPort: true },
});
console.log(`MAME_E2E_SERVER_PID=${process.pid}`);
server.printUrls();
