# kuma 통합 앱 구현 계획

**목표:** kuro(primer 설계) + mame(NGS 판정)를 `Kuro`/`Mame` 탭을 가진 단일 Tauri 앱 `kuma`로 통합. 프로젝트 폴더 기반 세션 연속성 제공.

**아키텍처:** kuro repo 복제 기반(히스토리 보존)으로 mame를 이식. 두 Python sidecar는 lazy-spawn 유지. Rust 쪽이 프로젝트 CRUD와 sidecar 생명주기 소유. React는 단일 통합 IPC 레이어에서 `kind`로 라우팅.

**기술 스택:** Tauri v2, React 19, Vite, pnpm, Python 3.11+, PyInstaller, Rust, TypeScript

**Mode:** hold
**Spec:** `$OBSIDIAN_VAULT/010.KRIBB/010.Projects/010.프라이머_설계_툴/kuma/2026-04-24-kuma-integration.md`
**Verifier:** 미검증 (작성 직후 1차 검증 예정)

경로 관례: `$WS = $WORKSPACE_ROOT/cc`. 아래 모든 `$WS/...` 표기는 이 prefix를 가리킴.

---

## 사전 준비

- [ ] **P1: GitHub에 private repo `kuma` 생성 (사용자 작업)**
  - github.com에서 `kuma` private repo 생성 (README/gitignore 체크 해제)
  - URL을 기록 (예: `git@github.com:<user>/kuma.git`)

- [ ] **P2: 로컬에 kuro 복제 → kuma로 rename (히스토리 보존)**
  ```bash
  cd "$WS"
  cp -r kuro kuma
  cd kuma
  git remote set-url origin git@github.com:<user>/kuma.git
  git remote -v
  git push -u origin master
  ```
  예상: 원격 push 성공, kuro 커밋 히스토리 보존

- [ ] **P3: 기준 태그 기록**
  ```bash
  cd "$WS/kuma"
  git tag pre-integration
  git push origin pre-integration
  ```

---

## Task 1: 제품명/패키지명 rename (Step 1 — Repo 세팅)

**배경**: kuro에는 두 종류의 Python 코드가 있다. 둘 다 동시에 이동/충돌회피해야 함.
- **도메인 패키지**: `kuro/` (root에 위치) — 알고리즘·데이터 모델
- **Sidecar 런타임**: `python-core/sidecar/` (JSON-RPC handlers)

mame도 동일 구조(`src/mame/` + `python-core/sidecar/`)이므로, kuro와 mame의 `python-core/sidecar/`는 **이름 충돌**. Task 1에서 kuro 쪽을 `sidecar_kuro/`로 rename, Task 5에서 mame 쪽을 `sidecar_mame/`로.

**파일:**
- 수정: `package.json` (`"name": "kuro"` → `"kuma"`)
- 수정: `src-tauri/Cargo.toml` (package name)
- 수정: `src-tauri/tauri.conf.json` (productName, identifier, windows.title)
- 수정: `pyproject.toml` (project.name, packages)
- 수정: `index.html` (`<title>`)
- 이동: `kuro/` 도메인 패키지 → `kuma_core/kuro/`
- 이동: `python-core/sidecar/` → `python-core/sidecar_kuro/`
- 이동: `python-core/sidecar_main.py` → `python-core/sidecar_main_kuro.py`
- 수정: `python-core/kuro-sidecar.spec` (entry 경로, hiddenimports, datas)
- 수정: `python-core/sidecar_main_kuro.py` (`from sidecar` → `from sidecar_kuro`)
- 수정: `python-core/sidecar_kuro/**/*.py` 내부 import (`from kuro` → `from kuma_core.kuro`)

- [ ] **Step 1.1: 의존성 현황 스냅샷**
  ```bash
  cd "$WS/kuma"
  grep -rn "^from kuro\|^import kuro" --include="*.py" . > /tmp/kuro_imports.txt
  wc -l /tmp/kuro_imports.txt
  ```
  예상: kuro import 파일 리스트 출력

- [ ] **Step 1.2: 도메인 패키지 이동 + import 치환**
  ```bash
  mkdir -p kuma_core
  git mv kuro kuma_core/kuro
  touch kuma_core/__init__.py
  # 모든 Python 파일에서 from kuro.X → from kuma_core.kuro.X
  grep -rln "from kuro\b\|^import kuro\b" --include="*.py" . \
    | xargs sed -i 's/from kuro\b/from kuma_core.kuro/g; s/^import kuro\b/import kuma_core.kuro as kuro/g'
  ```
  검증: `pytest tests/ -x` → 기존 kuro 도메인 테스트 PASS

- [ ] **Step 1.3: Sidecar 런타임 rename + import 치환**
  ```bash
  git mv python-core/sidecar python-core/sidecar_kuro
  git mv python-core/sidecar_main.py python-core/sidecar_main_kuro.py
  # sidecar_main_kuro.py와 sidecar_kuro/ 내부 파일에서
  # from sidecar → from sidecar_kuro
  grep -rln "from sidecar\b\|^import sidecar\b" python-core --include="*.py" \
    | xargs sed -i 's/from sidecar\b/from sidecar_kuro/g; s/^import sidecar\b/import sidecar_kuro as sidecar/g'
  ```
  `python-core/kuro-sidecar.spec` 수정:
  - `Analysis([...])` entry를 `sidecar_main_kuro.py`로
  - `hiddenimports`에 `sidecar_kuro.handlers.*` 포함 여부 확인
  - `datas` 경로가 `kuma_core/kuro/...` 참조하도록 수정
  
  빌드 검증:
  ```bash
  cd python-core && python build_sidecar.py
  ls dist/kuro-sidecar
  ./dist/kuro-sidecar --help 2>&1 | head -5  # entry 정상 기동 확인
  ```
  예상: `dist/kuro-sidecar` 생성, 실행 시 startup 로그 출력

- [ ] **Step 1.4: 제품명 일괄 치환**
  - `package.json`, `Cargo.toml`, `tauri.conf.json`, `pyproject.toml`, `index.html`
  - 제품명 `kuma`, 식별자 `com.<org>.kuma`, 윈도우 타이틀 `kuma`

- [ ] **Step 1.5: 앱 빌드 & 실행 검증**
  ```bash
  pnpm install
  pnpm tauri dev
  ```
  예상: 타이틀바에 `kuma`, 기존 KURO UI 정상

- [ ] **Step 1.6: 커밋**
  ```bash
  git commit -am "v0.01.00.00: rename kuro → kuma, move package to kuma_core/kuro"
  ```

---

## Task 2: 프로젝트 파일 스키마 & Rust CRUD (Step 2 기반)

**파일:**
- 생성: `src-tauri/src/project.rs`
- 생성: `src-tauri/tests/project_test.rs`
- 수정: `src-tauri/src/main.rs`
- 수정: `src-tauri/Cargo.toml` (의존성 추가)

- [ ] **Step 2.1: 실패 테스트 — 프로젝트 생성**
  ```rust
  use kuma::project::{create_project, load_project};
  use tempfile::tempdir;

  #[test]
  fn creates_project_folder_with_schema_v1() {
      let root = tempdir().unwrap();
      let path = create_project(root.path(), "Sample_42").unwrap();
      assert!(path.join("kuma.project.json").exists());
      let proj = load_project(&path).unwrap();
      assert_eq!(proj.schema, 1);
      assert_eq!(proj.name, "Sample_42");
      assert_eq!(proj.stage, "draft");
  }
  ```

- [ ] **Step 2.2: 실행 → FAIL 확인**
  ```bash
  cd src-tauri && cargo test project_test -- --nocapture
  ```
  예상: FAIL — 모듈 없음

- [ ] **Step 2.3: 최소 구현**
  `src-tauri/src/project.rs`:
  ```rust
  use serde::{Deserialize, Serialize};
  use std::path::{Path, PathBuf};

  #[derive(Serialize, Deserialize, Debug)]
  pub struct Project {
      pub schema: u32,
      pub project_id: String,
      pub name: String,
      pub created_at: String,
      pub updated_at: String,
      pub stage: String,
      pub kuro_workspace: Option<String>,
      pub expected_mutations: Option<String>,
      pub analysis_input: Option<String>,
      pub analysis_output: Option<String>,
      pub last_opened_tab: String,
  }

  pub fn create_project(root: &Path, name: &str) -> Result<PathBuf, String> {
      let path = unique_folder(root, name);
      std::fs::create_dir_all(path.join("design")).map_err(|e| e.to_string())?;
      std::fs::create_dir_all(path.join("analysis/consensus")).map_err(|e| e.to_string())?;
      let now = chrono::Local::now().to_rfc3339();
      let proj = Project {
          schema: 1,
          project_id: uuid::Uuid::new_v4().to_string(),
          name: name.to_string(),
          created_at: now.clone(),
          updated_at: now,
          stage: "draft".into(),
          kuro_workspace: None,
          expected_mutations: None,
          analysis_input: None,
          analysis_output: None,
          last_opened_tab: "kuro".into(),
      };
      let json = serde_json::to_string_pretty(&proj).map_err(|e| e.to_string())?;
      std::fs::write(path.join("kuma.project.json"), json).map_err(|e| e.to_string())?;
      Ok(path)
  }

  pub fn load_project(path: &Path) -> Result<Project, String> {
      let s = std::fs::read_to_string(path.join("kuma.project.json")).map_err(|e| e.to_string())?;
      serde_json::from_str(&s).map_err(|e| e.to_string())
  }

  fn unique_folder(root: &Path, name: &str) -> PathBuf {
      let mut candidate = root.join(name);
      let mut n = 2;
      while candidate.exists() {
          candidate = root.join(format!("{}_{}", name, n));
          n += 1;
      }
      candidate
  }
  ```
  Cargo.toml 의존성:
  ```toml
  serde = { version = "1", features = ["derive"] }
  serde_json = "1"
  uuid = { version = "1", features = ["v4"] }
  chrono = "0.4"
  # [dev-dependencies]
  tempfile = "3"
  ```

- [ ] **Step 2.4: 실행 → PASS 확인**
  ```bash
  cargo test project_test
  ```
  예상: `test creates_project_folder_with_schema_v1 ... ok`

- [ ] **Step 2.5: Stage 자동 계산 (FAIL → 구현 → PASS)**
  ```rust
  #[test]
  fn stage_is_draft_when_no_xlsx() { /* 빈 프로젝트 → "draft" */ }
  #[test]
  fn stage_is_design_complete_when_xlsx_present() {
      let root = tempdir().unwrap();
      let p = create_project(root.path(), "S").unwrap();
      std::fs::write(p.join("design/expected_mutations.xlsx"), b"").unwrap();
      assert_eq!(compute_stage(&p), "design_complete");
  }
  #[test]
  fn stage_is_analyzing_when_consensus_present_without_verdict() { /* ... */ }
  #[test]
  fn stage_is_done_when_verdict_present() { /* ... */ }
  ```
  구현:
  ```rust
  pub fn compute_stage(path: &Path) -> String {
      let has_xlsx = path.join("design/expected_mutations.xlsx").exists();
      let consensus_has_files = path.join("analysis/consensus").read_dir()
          .map(|mut d| d.next().is_some()).unwrap_or(false);
      let has_verdict = path.join("analysis/verdict.xlsx").exists();
      match (has_xlsx, consensus_has_files, has_verdict) {
          (_, _, true) => "done",
          (_, true, false) => "analyzing",
          (true, false, false) => "design_complete",
          _ => "draft",
      }.into()
  }
  ```

- [ ] **Step 2.6: 동명 프로젝트 suffix (FAIL → PASS)**
  ```rust
  #[test]
  fn duplicate_name_gets_numeric_suffix() {
      let root = tempdir().unwrap();
      let p1 = create_project(root.path(), "Sample_42").unwrap();
      let p2 = create_project(root.path(), "Sample_42").unwrap();
      assert_eq!(p1.file_name().unwrap(), "Sample_42");
      assert_eq!(p2.file_name().unwrap(), "Sample_42_2");
  }
  ```

- [ ] **Step 2.7: 손상된 json + schema 버전**
  ```rust
  #[test]
  fn load_project_returns_err_on_corrupt_json() {
      let root = tempdir().unwrap();
      let p = root.path().join("broken");
      std::fs::create_dir_all(&p).unwrap();
      std::fs::write(p.join("kuma.project.json"), "{not json").unwrap();
      assert!(load_project(&p).is_err());
  }
  #[test]
  fn load_project_rejects_future_schema() {
      let root = tempdir().unwrap();
      let p = create_project(root.path(), "S").unwrap();
      // schema를 99로 변조
      let mut proj = load_project(&p).unwrap();
      proj.schema = 99;
      std::fs::write(p.join("kuma.project.json"),
          serde_json::to_string(&proj).unwrap()).unwrap();
      let err = load_project(&p).unwrap_err();
      assert!(err.contains("SchemaTooNew"));
  }
  ```
  구현: `load_project` 내부에서 `if proj.schema > 1 { return Err("SchemaTooNew".into()); }` 추가.

- [ ] **Step 2.8: 커밋**
  ```bash
  git commit -am "v0.01.01.00: add project CRUD with schema v1"
  ```

---

## Task 3: 앱 설정 (projects_root) & Recent Projects

**파일:**
- 생성: `src-tauri/src/config.rs`
- 생성: `src-tauri/tests/config_test.rs`
- 수정: `src-tauri/src/main.rs`

- [ ] **Step 3.1: 실패 테스트**
  ```rust
  #[test]
  fn creates_default_config_on_first_run() {
      let tmp = tempdir().unwrap();
      let cfg = load_or_init_config(tmp.path()).unwrap();
      assert!(cfg.projects_root.ends_with("kuma"));
      assert!(cfg.recent_projects.is_empty());
  }
  ```

- [ ] **Step 3.2: FAIL 확인 → 구현**
  `~/.kuma/config.json`:
  ```rust
  pub struct Config {
      pub projects_root: PathBuf,
      pub recent_projects: Vec<RecentProject>,
  }
  pub struct RecentProject { pub path: String, pub name: String, pub last_opened: String }
  ```
  config 루트 인자를 받아 테스트 시 tempdir 사용 가능.

- [ ] **Step 3.3: PASS 확인**

- [ ] **Step 3.4: projects_root 사라짐 감지**
  - 경로 없을 때 `load_or_init_config`가 `NeedsReconfigure` 반환
  - 온보딩 재호출 플로우 구현

- [ ] **Step 3.5: Tauri commands 노출**
  ```rust
  .invoke_handler(tauri::generate_handler![
      create_project_cmd, load_project_cmd, list_recent_projects_cmd,
      get_config_cmd, set_projects_root_cmd,
  ])
  ```

- [ ] **Step 3.6: 커밋**
  ```bash
  git commit -am "v0.01.02.00: add config and recent projects management"
  ```

---

## Task 4: 시작 화면 & 온보딩 UI (React)

**파일:**
- 생성: `src/screens/Home.tsx`
- 생성: `src/screens/Onboarding.tsx`
- 생성: `src/lib/project.ts` (Rust command 래퍼)
- 수정: `src/App.tsx`
- 테스트: `tests/home.test.tsx`

- [ ] **Step 4.1: 실패 테스트 — 시작 화면 렌더**
  ```tsx
  test('Home shows new project button and recent list', async () => {
    render(<Home />);
    expect(await screen.findByRole('button', { name: /새 프로젝트/ })).toBeInTheDocument();
    expect(screen.getByText(/최근 프로젝트/)).toBeInTheDocument();
  });
  ```

- [ ] **Step 4.2: FAIL → `Home.tsx` 구현**
  - 버튼 3개: `+ 새 프로젝트`, `파일 열기`, `설정`
  - 최근 프로젝트 리스트 (빈 상태 "아직 없어요")

- [ ] **Step 4.3: 새 프로젝트 다이얼로그 테스트**
  이름 입력 → `create_project_cmd` 호출 → 메인 화면 전환.

- [ ] **Step 4.4: 온보딩 테스트 + 구현**
  - `config.projects_root` 비어있으면 `Onboarding` 우선 표시
  - 기본값 `~/Documents/kuma/`, 폴더 선택 다이얼로그 (`@tauri-apps/plugin-dialog`)

- [ ] **Step 4.5: Scratch 모드 엔트리**
  `.kuro.json` 선택 시 기존 KURO workspace 로드 경로로 진입.

- [ ] **Step 4.6: 커밋**
  ```bash
  git commit -am "v0.01.03.00: add home screen, onboarding, scratch entry"
  ```

---

## Task 5: mame 이식 (Step 3)

**파일:**
- 복사: `$WS/mame/src/mame/` → `kuma_core/mame/` (도메인 패키지)
- 복사: `$WS/mame/python-core/sidecar/` → `python-core/sidecar_mame/` (런타임)
- 복사: `$WS/mame/python-core/sidecar_main.py` → `python-core/sidecar_main_mame.py`
- 복사: `$WS/mame/python-core/mame-sidecar.spec` → `python-core/mame-sidecar.spec`
- 복사: `$WS/mame/src/` → `apps/mame/` (React 자산 임시, Task 7 흡수)
- 수정: `python-core/build_sidecar.py` — CLI `--target` 플래그
- 수정: `src-tauri/tauri.conf.json` — `externalBin` 확장
- 수정: `pyproject.toml` — `kuma_core.mame` 등록

- [ ] **Step 5.1: 도메인 패키지 + 런타임 이식**
  ```bash
  cp -r "$WS/mame/src/mame" kuma_core/mame
  cp -r "$WS/mame/python-core/sidecar" python-core/sidecar_mame
  cp "$WS/mame/python-core/sidecar_main.py" python-core/sidecar_main_mame.py
  cp "$WS/mame/python-core/mame-sidecar.spec" python-core/mame-sidecar.spec
  ```

- [ ] **Step 5.2: import 경로 치환**
  ```bash
  # 도메인 패키지: from mame → from kuma_core.mame
  grep -rln "from mame\b\|^import mame\b" kuma_core/mame --include="*.py" \
    | xargs sed -i 's/from mame\b/from kuma_core.mame/g; s/^import mame\b/import kuma_core.mame as mame/g'
  # 런타임: from sidecar → from sidecar_mame (mame sidecar 내부)
  grep -rln "from sidecar\b\|^import sidecar\b" python-core/sidecar_mame python-core/sidecar_main_mame.py --include="*.py" \
    | xargs sed -i 's/from sidecar\b/from sidecar_mame/g; s/^import sidecar\b/import sidecar_mame as sidecar/g'
  # mame sidecar 내부에서 from mame → from kuma_core.mame
  grep -rln "from mame\b" python-core/sidecar_mame --include="*.py" \
    | xargs sed -i 's/from mame\b/from kuma_core.mame/g'
  ```
  `mame-sidecar.spec` entry를 `sidecar_main_mame.py`로 갱신, hiddenimports/datas 경로도 동일하게.

- [ ] **Step 5.3: 테스트 이식 + 통과**
  ```bash
  cp -r "$WS/mame/tests" tests/mame
  # import 경로 수정 후
  pytest tests/mame -x
  ```
  예상: 기존 mame 테스트 PASS

- [ ] **Step 5.4: build_sidecar.py CLI 화**
  ```python
  import argparse, subprocess
  parser = argparse.ArgumentParser()
  parser.add_argument('--target', choices=['kuro', 'mame', 'all'], default='all')
  args = parser.parse_args()
  targets = ['kuro', 'mame'] if args.target == 'all' else [args.target]
  for t in targets:
      subprocess.run(['pyinstaller', '--noconfirm', f'{t}-sidecar.spec'], check=True)
  ```
  ```bash
  python build_sidecar.py --target mame
  ```
  예상: `dist/mame-sidecar` 바이너리 생성

- [ ] **Step 5.5: tauri.conf.json externalBin**
  ```json
  "bundle": {
      "externalBin": ["binaries/kuro-sidecar", "binaries/mame-sidecar"]
  }
  ```
  `src-tauri/binaries/`에 두 바이너리 복사.

- [ ] **Step 5.6: React 자산 임시 보관**
  ```bash
  mkdir -p apps/mame
  cp -r "$WS/mame/src" apps/mame/src
  cp "$WS/mame/package.json" apps/mame/package.json
  ```
  Task 7에서 `src/screens/MameTab.tsx`로 흡수.

- [ ] **Step 5.7: 빌드 검증**
  ```bash
  pnpm tauri dev
  ```
  예상: Kuro UI만 표시, 두 바이너리 번들 포함.

- [ ] **Step 5.8: 커밋**
  ```bash
  git commit -am "v0.02.00.00: port mame python package and build integration"
  ```

---

## Task 6: 통합 IPC 레이어 + Sidecar 생명주기 (Step 4)

**파일:**
- 생성: `src/lib/ipc.ts`
- 생성: `src/lib/ipc-kuro/index.ts`
- 생성: `src/lib/ipc-mame/index.ts`
- 생성: `src-tauri/src/sidecar.rs`
- 수정: `src-tauri/src/main.rs`
- 테스트: `src-tauri/tests/sidecar_test.rs`

- [ ] **Step 6.1: Rust sidecar 매니저 실패 테스트**
  `binaries_dir()`는 테스트 헬퍼 — `CARGO_MANIFEST_DIR/../binaries/` 해석.
  ```rust
  fn binaries_dir() -> PathBuf {
      PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../binaries")
  }
  #[tokio::test]
  async fn spawns_and_routes_to_kuro_sidecar() {
      let mgr = SidecarManager::new(binaries_dir()).await;
      let resp: serde_json::Value = mgr.rpc("kuro", "ping", json!({})).await.unwrap();
      assert_eq!(resp["result"], "pong");
  }
  ```
  사전 조건: Task 1.3의 `dist/kuro-sidecar` 바이너리가 `src-tauri/binaries/`에 존재.

- [ ] **Step 6.2: FAIL → 구현**
  ```rust
  pub struct SidecarManager {
      kuro: Mutex<Option<Child>>,
      mame: Mutex<Option<Child>>,
      binaries_dir: PathBuf,
  }
  impl SidecarManager {
      pub async fn rpc(&self, kind: &str, method: &str, params: Value) -> Result<Value, String> {
          let child = self.ensure_spawned(kind).await?;
          send_jsonrpc(child, method, params).await
      }
      async fn ensure_spawned(&self, kind: &str) -> Result<&Child, String> { /* lazy spawn */ }
  }
  ```
  - race condition 방지 (Mutex)
  - 비정상 종료 감지 → 재spawn

- [ ] **Step 6.3: Tauri command 등록**
  ```rust
  #[tauri::command]
  async fn sidecar_rpc(
      kind: String, method: String, params: Value,
      state: State<'_, SidecarManager>,
  ) -> Result<Value, String> {
      state.rpc(&kind, &method, params).await
  }
  ```

- [ ] **Step 6.4: React 통합 ipc.ts**
  ```ts
  import { invoke } from '@tauri-apps/api/core';
  export type SidecarKind = 'kuro' | 'mame';
  export async function rpc<T = unknown>(
    kind: SidecarKind, method: string, params: unknown = {}
  ): Promise<T> {
    return invoke('sidecar_rpc', { kind, method, params }) as Promise<T>;
  }
  ```

- [ ] **Step 6.5: 기존 kuro ipc 래퍼 분리**
  기존 `src/lib/ipc.ts`의 함수들을 `src/lib/ipc-kuro/index.ts`로 이동.
  내부 호출을 `rpc('kuro', method, params)`로 치환.

- [ ] **Step 6.6: mame ipc 래퍼 이식**
  `$WS/mame/src/lib/ipc.ts` 내용 → `src/lib/ipc-mame/index.ts`, `rpc('mame', ...)` 사용.

- [ ] **Step 6.7: 통합 빌드 검증**
  ```bash
  pnpm tauri dev
  ```
  예상: Kuro UI 정상, mame sidecar는 탭 활성 전까지 미기동.

- [ ] **Step 6.8: 커밋**
  ```bash
  git commit -am "v0.02.01.00: unified ipc layer and sidecar lifecycle"
  ```

---

## Task 7: 탭 UI & 프로젝트 컨텍스트

**파일:**
- 생성: `src/screens/KuroTab.tsx`
- 생성: `src/screens/MameTab.tsx`
- 생성: `src/screens/MainShell.tsx`
- 생성: `src/state/projectContext.tsx`
- 수정: `src/App.tsx`

- [ ] **Step 7.1: 탭 전환 테스트**
  ```tsx
  test('switching tabs activates respective sidecar', async () => {
    const spy = vi.spyOn(api, 'rpc');
    render(<MainShell project={mockProject} />);
    await user.click(screen.getByRole('tab', { name: 'Mame' }));
    expect(spy).toHaveBeenCalledWith('mame', 'ping', {});
  });
  ```

- [ ] **Step 7.2: FAIL → MainShell 구현**
  ```tsx
  <Tabs defaultValue="kuro">
    <TabsList>
      <TabsTrigger value="kuro">Kuro</TabsTrigger>
      <TabsTrigger value="mame">Mame</TabsTrigger>
    </TabsList>
    <TabsContent value="kuro"><KuroTab /></TabsContent>
    <TabsContent value="mame"><MameTab /></TabsContent>
  </Tabs>
  ```
  탭 전환 시 `rpc(kind, 'ping', {})`로 lazy spawn 트리거.

- [ ] **Step 7.3: KuroTab/MameTab로 기존 UI 래핑**
  - `KuroTab.tsx`: 기존 kuro 컴포넌트 트리 import
  - `MameTab.tsx`: `apps/mame/src/App.tsx` 내용 이동, `src/components/mame/`로 재배치

- [ ] **Step 7.4: Project context**
  ```tsx
  export const ProjectContext = createContext<Project | null>(null);
  ```
  두 탭 공용 현재 프로젝트 메타.

- [ ] **Step 7.5: 헤더에 프로젝트 이름 + stage 뱃지**
  프로젝트 열려있을 때만, scratch면 "(Scratch)".

- [ ] **Step 7.6: 커밋**
  ```bash
  git commit -am "v0.02.02.00: add Kuro/Mame tabs and project context"
  ```

---

## Task 8: xlsx 메타 시그니처

**파일** (Task 1·5 이후 경로 기준):
- 수정: `python-core/sidecar_kuro/handlers/export.py` (handle_export_excel 시그니처 확장)
- 생성: `python-core/sidecar_mame/handlers/kuma_meta.py` (메타 read handler)
- 또는 `kuma_core/mame/io/kuma_meta.py`에 메타 파서, sidecar_mame/handlers가 그걸 호출
- 테스트: `tests/sidecar_kuro/test_export_meta.py`, `tests/sidecar_mame/test_meta_read.py`

- [ ] **Step 8.1: Kuro export meta write — 실패 테스트**
  ```python
  def test_xlsx_contains_kuma_meta_sheet(tmp_path):
      out = tmp_path / "out.xlsx"
      export_expected_mutations(mutations=[...], output=out,
                                project_id="abc-123", kuma_version="0.1.0")
      book = openpyxl.load_workbook(out, keep_vba=False)
      assert "__kuma_meta__" in book.sheetnames
      meta = {r[0].value: r[1].value
              for r in book["__kuma_meta__"].iter_rows(min_row=1, max_row=4)}
      assert meta["project_id"] == "abc-123"
      assert meta["kuma_version"] == "0.1.0"
  ```

- [ ] **Step 8.2: FAIL → handler 확장**
  `handle_export_excel`에 `project_id: Optional[str]`, `kuma_version: str` 추가:
  ```python
  if project_id:
      meta_sheet = wb.create_sheet("__kuma_meta__")
      meta_sheet.sheet_state = "hidden"
      meta_sheet.append(["project_id", project_id])
      meta_sheet.append(["kuma_version", kuma_version])
      meta_sheet.append(["kuro_module_version", KURO_VERSION])
      meta_sheet.append(["exported_at", datetime.now(tz).isoformat()])
  ```
  scratch 모드 (project_id=None) → 시트 생략.

- [ ] **Step 8.3: PASS 확인**

- [ ] **Step 8.4: React → sidecar 전달**
  `src/lib/ipc-kuro/index.ts`의 export 함수가 `ProjectContext`에서 `project_id`를 읽어 params에 포함.

- [ ] **Step 8.5: Mame meta read — 실패 테스트 + 구현**
  ```python
  def test_reads_meta_sheet_if_present(tmp_path):
      xlsx = make_xlsx_with_meta(tmp_path, project_id="abc-123")
      meta = read_kuma_meta(xlsx)
      assert meta.project_id == "abc-123"
  def test_returns_none_if_meta_absent(tmp_path):
      xlsx = make_plain_xlsx(tmp_path)
      assert read_kuma_meta(xlsx) is None
  ```
  구현: `kuma_core/mame/io/kuma_meta.py`

- [ ] **Step 8.6: MameTab 매칭 다이얼로그**
  - `rpc('mame', 'read_kuma_meta', { path })` → project_id
  - recent_projects에서 매칭
  - "Sample_42 프로젝트로 로드하시겠어요?" 다이얼로그

- [ ] **Step 8.7: 커밋**
  ```bash
  git commit -am "v0.02.03.00: xlsx __kuma_meta__ write/read with project matching"
  ```

---

## Task 9: Shared 유틸 추출 (Step 5)

**파일:**
- 생성: `kuma_core/shared/__init__.py`
- 생성: `kuma_core/shared/config_paths.py`
- 생성: `kuma_core/shared/logging.py`
- 생성: `kuma_core/shared/errors.py`

- [ ] **Step 9.1: 중복 식별**
  ```bash
  grep -rn "expanduser.*kuro\|Path.home.*kuro" kuma_core/kuro
  grep -rn "expanduser.*mame\|Path.home.*mame" kuma_core/mame
  ```

- [ ] **Step 9.2: `config_paths.py` 실패 테스트 + 구현**
  ```python
  def test_kuma_home_defaults_to_dot_kuma(monkeypatch):
      monkeypatch.setenv("HOME", "/tmp/testhome")
      assert kuma_home() == Path("/tmp/testhome/.kuma")
  ```

- [ ] **Step 9.3: logging / errors 유틸도 실패 테스트 + 구현**
  ```python
  def test_logger_writes_to_kuma_home_log(tmp_path, monkeypatch):
      monkeypatch.setenv("HOME", str(tmp_path))
      from kuma_core.shared.logging import get_logger
      log = get_logger("test")
      log.info("hello")
      assert (tmp_path / ".kuma" / "logs" / "test.log").exists()

  def test_jsonrpc_error_format():
      from kuma_core.shared.errors import jsonrpc_error
      err = jsonrpc_error(code=-32603, message="boom")
      assert err == {"code": -32603, "message": "boom"}
  ```

- [ ] **Step 9.4: kuro/mame에서 shared import로 교체**
  모듈별 최소 커밋. 각 단계 전체 테스트 슈트 통과 유지:
  ```bash
  pytest tests/ -x
  ```

- [ ] **Step 9.5: 커밋**
  ```bash
  git commit -am "v0.02.04.00: extract shared config/logging/errors"
  ```

---

## Task 10: 통합 시나리오 테스트

**파일:**
- 생성: `tests/integration/end_to_end.test.ts` (Playwright 또는 Tauri e2e)

- [ ] **Step 10.1: 시나리오**
  1. 첫 실행 → 온보딩 → projects_root 설정
  2. `+ 새 프로젝트` → `Sample_42` 생성
  3. Kuro 탭 → mutation 설계 → xlsx export
  4. `kuma.project.json`의 stage가 `design_complete`로 전환 확인
  5. 앱 재시작 → 최근 프로젝트에 `Sample_42`
  6. Mame 탭 → 별도 xlsx 드롭 → project_id 매칭 다이얼로그

- [ ] **Step 10.2: assertion 작성 & 통과**

- [ ] **Step 10.3: 커밋**
  ```bash
  git commit -am "v0.03.00.00: end-to-end integration scenario test"
  ```

---

## Task 11: 릴리스 준비

- [ ] **Step 11.1: CHANGELOG 작성**
  ```
  # v0.1.0 (2026-04-XX)
  첫 kuma 릴리스. kuro v<last>, mame v<last>를 통합.
  - Kuro / Mame 탭 UI
  - 프로젝트 폴더 기반 세션 연속성
  - __kuma_meta__ 시트로 파일 출처 자동 인식
  ```

- [ ] **Step 11.2: 버전 동기화**
  `tauri.conf.json` 0.1.0, `package.json`, `Cargo.toml`, `pyproject.toml`.

- [ ] **Step 11.3: GitHub Actions 빌드 (Windows/macOS/Linux)**
  기존 kuro 워크플로 재사용, 바이너리명 `kuma`로. `actions/checkout@v5` 등 최신.

- [ ] **Step 11.4: 기존 kuro/mame repo archive**
  README 상단:
  ```markdown
  > ⚠️ This repo is archived. Development continues in [kuma](https://github.com/<user>/kuma).
  ```
  GitHub settings에서 archive.

- [ ] **Step 11.5: v0.1.0 태그 + 릴리스 (private)**
  ```bash
  git tag v0.1.0
  git push origin v0.1.0
  ```

---

## 시간 배분 (스펙 기준 3.5-4일)

| Task | 단계 | 추정 |
|---|---|---|
| 사전 + Task 1 | Step 1 | 0.5일 |
| Task 2, 3, 4 | Step 2 | 1.0일 |
| Task 5 | Step 3 | 1.0일 |
| Task 6, 7, 8 | Step 4 | 0.5-0.75일 |
| Task 9 | Step 5 | 0.5-0.75일 |
| Task 10, 11 | 릴리스 | 0.25일 |

---

## Confidence Check

| 축 | 점수 | 근거 |
|---|---|---|
| Completeness | 4/5 | 스펙 섹션 7·12 모두 Task에 매핑. 엣지 케이스 단계 할당 반영 (Task 2.6, 2.7, 3.4, 8.6). |
| Clarity | 4/5 | 각 스텝 파일/명령/예상 출력 명시. 기존 함수명 일부는 코드 열람 후 정확 이름 확정 필요. |
| Feasibility | 4/5 | Tauri v2 + PyInstaller + pnpm 양쪽 앱에서 사용 중. 의존성 충돌 리스크 낮음. |

**총점 12/15 → 계획 유효.**

---

## 실패 시나리오 대응

- **Task 1.2 import 치환 후 테스트 실패**: 내부 상대 import는 유지, external만 치환
- **Task 5.4 PyInstaller onefile 용량 폭증**: onedir 모드 검토
- **Task 6.2 sidecar race condition**: Mutex 보호 유지, 탭 전환 스트레스 테스트
- **Task 8 hidden sheet 뷰어 호환성**: `sheet_state="veryHidden"` 대안 검토
