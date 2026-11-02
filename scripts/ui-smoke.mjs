import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { assertStillRunning, startOwnedServer, stopServer } from "./ui-smoke-server.mjs";

const HOST = "127.0.0.1";
const PORT = 4173;
const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(__dirname, "..");
const VITE_BIN = resolve(
  REPO_ROOT,
  "node_modules",
  ".bin",
  process.platform === "win32" ? "vite.cmd" : "vite",
);
const URL = `http://${HOST}:${PORT}`;

// Refuses a port someone else already serves, and rejects as soon as the
// child exits, so the page tested below is the one this checkout built.
const server = await startOwnedServer({
  command: VITE_BIN,
  args: ["preview", "--host", HOST, "--port", String(PORT), "--strictPort"],
  url: URL,
  spawnOptions: {
    stdio: "inherit",
    shell: process.platform === "win32",
  },
});

try {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage();
    const pageErrors = [];
    page.on("pageerror", (error) => {
      pageErrors.push(error);
    });
    await page.goto(URL, { waitUntil: "networkidle" });
    await page.waitForLoadState("domcontentloaded");
    const title = await page.title();
    if (title !== "kuma") {
      throw new Error(`Unexpected page title: ${title}`);
    }
    const rootHtml = await page.locator("#root").evaluate((el) => el.innerHTML.trim());
    if (!rootHtml) {
      throw new Error("App root did not render any content");
    }
    if (pageErrors.length > 0) {
      throw pageErrors[0];
    }
    assertStillRunning(server);
  } finally {
    await browser.close();
  }
} finally {
  if (!(await stopServer(server))) {
    console.error(`preview server (pid ${server.pid}) did not exit after SIGKILL`);
    process.exitCode = 1;
  }
}
