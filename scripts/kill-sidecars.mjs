import { spawnSync } from "node:child_process";

const sidecars = ["kuro-sidecar", "mame-sidecar"];

for (const name of sidecars) {
  if (process.platform === "win32") {
    spawnSync("taskkill", ["/F", "/IM", `${name}-x86_64-pc-windows-msvc.exe`], {
      stdio: "ignore",
    });
    continue;
  }

  const selfSafePattern = name.replace(/^./, "[$&]");
  spawnSync("pkill", ["-f", selfSafePattern], { stdio: "ignore" });
}
