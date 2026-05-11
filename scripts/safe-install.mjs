#!/usr/bin/env node
/**
 * safe-install.mjs - Windows-friendly pnpm install with auto-retry.
 *
 * Usage: pnpm setup
 *
 * Windows 파일 락(Defender, IDE 워처, antivirus)으로 인한 EACCES/EBUSY 실패를
 * 자동 재시도로 흡수한다. macOS/Linux에서는 일반 pnpm install과 동일하게 동작.
 *
 * 정책:
 * - Windows에서만 package-import-method=copy 임시 적용 (hardlink 락 우회)
 * - EACCES/EBUSY/EPERM 실패 시 3초 대기 후 재시도 (최대 3회)
 * - 마지막 실패 시 원인별 해결 가이드 출력
 */

import { spawn } from "node:child_process";
import process from "node:process";

const MAX_ATTEMPTS = 3;
const RETRY_DELAY_MS = 3000;
const isWindows = process.platform === "win32";

const env = { ...process.env };
if (isWindows) {
  env.npm_config_package_import_method = "copy";
}

function runOnce(attempt) {
  return new Promise((resolve) => {
    const buffers = [];
    const child = spawn("pnpm", ["install", ...process.argv.slice(2)], {
      stdio: ["inherit", "pipe", "pipe"],
      env,
      shell: isWindows,
    });

    child.stdout.on("data", (chunk) => {
      process.stdout.write(chunk);
      buffers.push(chunk);
    });
    child.stderr.on("data", (chunk) => {
      process.stderr.write(chunk);
      buffers.push(chunk);
    });

    child.on("close", (code) => {
      const output = Buffer.concat(buffers).toString();
      const retryable =
        code !== 0 &&
        /EACCES|EBUSY|EPERM|ENOTEMPTY|Cannot find module/i.test(output);
      resolve({ code, retryable, output });
    });

    child.on("error", (err) => {
      console.error(`\n[safe-install] spawn failed: ${err.message}`);
      resolve({ code: 1, retryable: false, output: err.message });
    });
  });
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

function printFailureGuide(lastOutput) {
  console.error("\n========================================");
  console.error("[safe-install] All attempts failed.");
  console.error("========================================");

  if (/EACCES|EBUSY|EPERM/i.test(lastOutput)) {
    console.error(`
Windows 파일 잠금 의심. 해결 순서:

  1. VS Code / Cursor 등 IDE 종료
  2. 실행 중인 vite dev server, tauri dev 프로세스 종료
  3. Windows Defender 예외 추가:
       Settings -> Virus & threat protection -> Manage settings
       -> Add or remove exclusions -> Add folder
       => 현재 프로젝트 경로 추가
  4. 관리자 PowerShell에서 다시 시도: pnpm setup
  5. 그래도 실패하면 수동 정리:
       Remove-Item node_modules -Recurse -Force
       pnpm setup
`);
  } else if (/Cannot find module/i.test(lastOutput)) {
    console.error(`
의존성 트리 불일치. node_modules 초기화 후 재시도:

  Remove-Item node_modules -Recurse -Force
  Remove-Item pnpm-lock.yaml   # (선택) lockfile도 재생성 원하면
  pnpm setup
`);
  }
}

async function main() {
  console.log(
    `[safe-install] platform=${process.platform} package-import-method=${env.npm_config_package_import_method ?? "default"}`,
  );

  let lastOutput = "";
  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
    if (attempt > 1) {
      console.log(
        `\n[safe-install] Retry ${attempt}/${MAX_ATTEMPTS} after ${RETRY_DELAY_MS}ms ...`,
      );
      await sleep(RETRY_DELAY_MS);
    }
    const { code, retryable, output } = await runOnce(attempt);
    lastOutput = output;
    if (code === 0) {
      console.log(`\n[safe-install] OK (attempt ${attempt}/${MAX_ATTEMPTS})`);
      process.exit(0);
    }
    if (!retryable) {
      console.error(
        `\n[safe-install] non-retryable failure (exit ${code}). Stopping.`,
      );
      process.exit(code);
    }
  }

  printFailureGuide(lastOutput);
  process.exit(1);
}

main().catch((err) => {
  console.error(`[safe-install] unexpected error: ${err?.stack ?? err}`);
  process.exit(1);
});
