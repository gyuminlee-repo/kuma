# KURO Project Rules

## CI/CD Guidelines — GitHub Actions 빌드 실패 방지

### 릴리스 전 필수 체크리스트
코드 수정 후 태그 푸시 전 반드시 로컬에서 확인:
```bash
npx tsc --noEmit          # TypeScript 타입체크
cd src-tauri && cargo check  # Rust 컴파일 체크
```
**이 두 명령이 통과하지 않으면 태그를 만들지 않는다.**

### TypeScript 타입 안전성
1. **모듈 레벨 `let` 변수 + async 재할당 패턴 금지**
   - `let x: T | null = null` 후 async IIFE/callback에서 재할당하면 TS가 narrowing을 잘못 추론함
   - 해결: `const proc = child as Child | null;` 처럼 로컬 변수 + 명시적 타입 사용
2. **`!` (non-null assertion) 최소화**
   - `ipc.ts:157`의 `child!.write(...)` — 런타임 NPE 위험
   - 대안: null guard 후 호출하거나 early return 패턴 사용
3. **`as any`, `@ts-ignore` 사용 금지** — 현재 0건 유지할 것

### Tauri 리소스 번들링
1. **resources glob은 `src-tauri/` 기준 상대경로만 사용**
   - `"resources": ["samples/**"]` (O)
   - `"resources": ["../samples/**"]` (X) — cross-compilation (`--target`) 시 glob 해석 실패
2. **번들에 포함할 파일은 `src-tauri/` 하위에 배치**
   - 프론트엔드의 `resolveResource()` 경로와 일치시킬 것

### 버전 동기화
릴리스 시 아래 3개 파일의 버전을 반드시 일치시킨다:
- `package.json` → `"version": "X.X.X"`
- `src-tauri/tauri.conf.json` → `"version": "X.X.X"`
- `src-tauri/Cargo.toml` → `version = "X.X.X"`

### GitHub Actions Workflow 규칙
1. **actions 버전**: `@v5` 이상 사용 (Node.js 24 호환)
2. **build.yml**: `fail-fast: false` 유지 — 한 OS 실패가 다른 OS 빌드 취소하지 않게
3. **sidecar 바이너리 확인 스텝 유지** — `test -f` 로 존재 여부 검증
4. **Cargo.lock 커밋 유지** — Tauri 앱은 바이너리 빌드이므로 lock 파일 필수
5. **ubuntu-22.04 고정** — `ubuntu-latest`가 아닌 특정 버전 사용 (WebKit 의존성 호환)
6. **`--target` 플래그 사용 금지** — 네이티브 빌드에서 `npx tauri build --target`을 쓰면 glob 해석 경로가 바뀌어 resource 번들링 실패. `npx tauri build`만 사용
7. **artifact 경로**: `src-tauri/target/release/bundle/` (target triple 없음)

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
- 버전 bump 커밋은 `chore: bump version to X.X.XX`
