# KURO Project Rules

## CI/CD Guidelines — GitHub Actions 빌드 실패 방지

> v0.9.37 릴리스에서 겪은 실패 사례를 기반으로 작성. 모든 항목은 실제 빌드 실패에서 유래함.

### 릴리스 전 필수 체크리스트

태그 푸시 전 반드시 **모든 항목** 통과 확인:

```bash
# 1. TypeScript 타입체크
npx tsc --noEmit

# 2. Frontend 빌드 (Rust check에 필요)
npm run build

# 3. Rust 컴파일 체크 (sidecar stub 필요)
touch src-tauri/binaries/kuro-sidecar-x86_64-unknown-linux-gnu
cd src-tauri && cargo check

# 4. Python 테스트
pip install primer3-py==2.3.0 biopython==1.84 openpyxl==3.1.5 pytest
python -m pytest tests/ -v
```

**하나라도 실패하면 태그를 만들지 않는다.**

---

### 실패 사례 & 교훈 (v0.9.37)

#### 1. Tauri 리소스 glob 실패
- **증상**: `glob pattern samples/** path not found or didn't match any files`
- **원인**: Tauri build.rs의 glob 해석이 OS별/빌드모드별로 다름
- **시도했으나 실패한 것**:
  - `../samples/**` → `samples/**`로 변경 (실패 — Windows에서도 동일)
  - `--target` 플래그 제거 (실패 — glob 자체가 문제)
- **최종 해결**: glob 완전 제거, 명시적 파일 매핑 사용
  ```json
  "resources": {
    "samples/file.csv": "samples/file.csv"
  }
  ```
- **규칙**: **Tauri resources에 glob(`*`, `**`) 절대 사용 금지**

#### 2. `--target` 플래그 불필요
- **증상**: 리소스 경로가 target-specific 빌드 디렉토리 기준으로 해석됨
- **원인**: CI에서 `npx tauri build --target x86_64-pc-windows-msvc` 사용
- **해결**: 네이티브 빌드이므로 `npx tauri build`로 충분
- **규칙**: 크로스 컴파일 아니면 `--target` 사용 금지

#### 3. TypeScript `never` 타입 에러
- **증상**: `Property 'kill' does not exist on type 'never'` (3 OS 전부)
- **원인**: 모듈 레벨 `let child: Child | null = null` → early return 후 TS가 `null`로 확정 → async IIFE 내 재할당을 추적 못함
- **해결**: `const proc = child as Child | null;` 로컬 변수 + 명시적 타입
- **규칙**: 모듈 레벨 `let` + async 재할당 패턴에서는 반드시 `as T | null` 사용

#### 4. pip install editable 실패
- **증상**: `pip install -e .` → setuptools._legacy backend가 editable 미지원
- **원인**: `pyproject.toml`의 `build-backend = "setuptools.backends._legacy:_Backend"`
- **해결 2가지**:
  - build-backend를 `setuptools.build_meta`로 변경
  - CI에서 `-e .` 대신 의존성 직접 설치
- **규칙**: CI에서는 `pip install <deps> pytest`로 직접 설치. editable install 불필요.

#### 5. `pip install -e ".[dev]"` — extras 미정의
- **증상**: `[dev]` extras가 pyproject.toml에 없어서 pip 에러
- **해결**: extras 참조 제거
- **규칙**: CI의 pip install 명령은 pyproject.toml과 반드시 일치 확인

#### 6. Rust cargo check — frontendDist 경로 없음
- **증상**: `The frontendDist configuration is set to "../dist" but this path doesn't exist`
- **원인**: `tauri::generate_context!()` 매크로가 컴파일 시점에 dist 존재 확인
- **해결**: rust-check job에 `npm ci && npm run build` 스텝 추가
- **규칙**: `cargo check` 전에 반드시 frontend 빌드 필요

#### 7. Sidecar 바이너리 경로 없음
- **증상**: `resource path binaries/kuro-sidecar-... doesn't exist`
- **원인**: CI의 rust-check job에서 sidecar를 안 빌드함
- **해결**: `touch src-tauri/binaries/kuro-sidecar-x86_64-unknown-linux-gnu` (stub)
- **규칙**: cargo check용으로 빈 stub 파일 생성 필수

#### 8. 테스트 assertion 오류
- **증상**: `assert 100.0 == 40.0` — `test_different_lengths`
- **원인**: `_sequence_identity("MV", "MVKLT")` → substring match → 100% 반환 (의도된 동작)
- **해결**: 테스트 기대값 수정
- **규칙**: 함수 로직(substring → 100%)을 이해한 뒤 테스트 작성

---

### TypeScript 타입 안전성
1. **`as any`, `@ts-ignore` 사용 금지** — 현재 0건 유지
2. **`!` (non-null assertion) 최소화** — null guard 후 호출 선호
3. **모듈 레벨 `let` + async 재할당** → 로컬 변수 + 명시적 타입 assertion

### Tauri 리소스 번들링
1. **glob 사용 금지** → 명시적 `{ "src": "target" }` 매핑만 허용
2. **번들 파일은 `src-tauri/` 하위에 배치**
3. **새 파일 추가 시** `tauri.conf.json` resources 맵에도 추가 필수
4. **`resolveResource()` 경로와 resources 매핑 일치** 확인

### 버전 동기화
릴리스 시 아래 3개 파일 + pyproject.toml 버전 일치:
- `package.json` → `"version": "X.X.X"`
- `src-tauri/tauri.conf.json` → `"version": "X.X.X"`
- `src-tauri/Cargo.toml` → `version = "X.X.X"`

### GitHub Actions Workflow 규칙

**build.yml (Build & Release)**:
1. `fail-fast: false` 유지
2. `npx tauri build` — `--target` 없이
3. artifact 경로: `src-tauri/target/release/bundle/`
4. sidecar 바이너리 `test -f` 검증 스텝 유지
5. ubuntu-22.04 고정 (WebKit 의존성)
6. actions 버전 `@v5` 이상 (Node.js 24 호환)

**ci.yml (CI)**:
1. `fail-fast: false` 유지
2. Python test: `pip install <deps> pytest` 직접 설치 (editable install 금지)
3. rust-check: `npm ci && npm run build` 후 cargo check
4. rust-check: sidecar stub `touch` 필수
5. typecheck: `npm ci && npx tsc --noEmit`

### .gitignore 필수 항목
```
.claude/
notes/
node_modules/
dist/
src-tauri/target/
src-tauri/gen/
```

## Git Convention
- Commit: `vX.X.XX: summary in English`
- 태그: `vX.X.XX` (semver)
- 버전 bump 커밋: `chore: bump version to X.X.XX`
