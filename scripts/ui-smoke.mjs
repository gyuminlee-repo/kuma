import { spawn } from "node:child_process";
import { setTimeout as delay } from "node:timers/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

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

async function waitForServer(url, timeoutMs = 30000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.ok) return;
    } catch {
      // Server not ready yet.
    }
    await delay(500);
  }
  throw new Error(`Timed out waiting for preview server at ${url}`);
}

const server = spawn(
  VITE_BIN,
  ["preview", "--host", HOST, "--port", String(PORT), "--strictPort"],
  {
    stdio: "inherit",
    shell: process.platform === "win32",
  },
);

try {
  await waitForServer(URL);

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
  } finally {
    await browser.close();
  }
} finally {
  server.kill("SIGTERM");
  await delay(500);
  if (!server.killed) {
    server.kill("SIGKILL");
  }
}
