/**
 * §5 Output Persistence — 결과 폴더 열기 헬퍼.
 *
 * `tauri-plugin-opener`의 `revealItemInDir`을 사용해
 * 파일을 OS 파일 탐색기에서 선택 상태로 연다.
 *
 * 의존성 설치:
 *   Windows 네이티브 터미널에서:
 *     pnpm add @tauri-apps/plugin-opener
 *   src-tauri/Cargo.toml: tauri-plugin-opener = "2"
 *   src-tauri/src/lib.rs: .plugin(tauri_plugin_opener::init())
 *   src-tauri/capabilities/default.json: "opener:allow-reveal-item-in-dir"
 */

/**
 * OS 파일 탐색기에서 filepath를 선택 상태로 표시한다.
 *
 * - macOS: Finder에서 파일 하이라이트
 * - Windows: 탐색기에서 파일 선택
 * - Linux: 파일 관리자에서 폴더 열기
 *
 * @param filepath - 절대 경로 (Windows 경로도 지원)
 * @throws plugin-opener 미설치 또는 OS 거부 시 에러를 throw한다. 호출자가 처리할 것.
 */
interface OpenerModule {
  revealItemInDir: (path: string) => Promise<void>;
}

export async function revealInOSFolder(filepath: string): Promise<void> {
  // Dynamic import: @tauri-apps/plugin-opener 패키지 설치 전에도 빌드가 통과하도록 한다.
  // 런타임에서 모듈을 찾지 못하면 에러를 throw해 호출자(toast action)에서 처리한다.
  const opener = await import("@tauri-apps/plugin-opener" as string) as OpenerModule;
  await opener.revealItemInDir(filepath);
}
