import { spawn } from "node:child_process";
import path from "node:path";
import process from "node:process";

const suffix = process.platform === "win32" ? "win" : process.platform;
const env = {
  ...process.env,
  CARGO_TARGET_DIR:
    process.env.CARGO_TARGET_DIR ??
    path.join(process.cwd(), "src-tauri", `target-${suffix}`),
  CARGO_INCREMENTAL: process.env.CARGO_INCREMENTAL ?? "0",
};

delete env.RUSTC_WRAPPER;
delete env.CARGO_BUILD_RUSTC_WRAPPER;
delete env.SCCACHE_ERROR_LOG;
delete env.SCCACHE_LOG;

const args = process.argv.slice(2);
const tauriCli = path.join(
  process.cwd(),
  "node_modules",
  "@tauri-apps",
  "cli",
  "tauri.js",
);

const child = spawn(process.execPath, [tauriCli, ...args], {
  stdio: "inherit",
  env,
});

child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 1);
});

child.on("error", (error) => {
  console.error(`Failed to launch Tauri CLI: ${error.message}`);
  process.exit(1);
});
