# Windows 테스트 가이드

브랜치: `worktree-spec-export-all-macrogen` (24 commits ahead of base)
경로: `D:\_workspace\cc\kuma\.claude\worktrees\spec-export-all-macrogen`

## 사전 확인

```powershell
# Windows PowerShell 에서 (WSL 아님)
cd D:\_workspace\cc\kuma\.claude\worktrees\spec-export-all-macrogen
git status              # → working tree clean
git log --oneline -5    # → ac2fb28 ... v0.4.2.03 ... 가 최신
```

## 1. 의존성 설치

```powershell
# 프론트엔드 (Windows native — WSL 절대 사용 금지)
pnpm install

# Python (kuro + sidecar 공용 pyproject.toml — xlwt 1.3.0 / xlrd 1.2.0 포함)
pip install -e .
```

## 2. 빠른 UI 검증 (sidecar 불필요)

```powershell
pnpm dev    # vite — http://localhost:1420
```

UI 만 보고 싶으면 이것만으로 충분. Phase C → Export 서브스텝에서 Export All 폼 확인.

## 3. 전체 통합 테스트 (sidecar 포함)

```powershell
pnpm sidecar:build      # PyInstaller --onefile → src-tauri/binaries/kuro-sidecar-x86_64-pc-windows-msvc.exe
pnpm tauri dev          # Tauri 개발 모드 실행
```

## 4. 검증 시나리오

### 4.1 Macrogen Export All
1. Project 열기 → Phase C → Export 서브스텝
2. **Plate Name (fwd)** / **(rev)** 입력. 한글/공백 입력 시 빨간 에러 메시지 확인.
3. **Amount** 드롭다운: 0.05 μmole / 0.2 μmole.
4. **Echo transfer vol**: 25–500 nL 범위 검증. 600 입력 시 차단.
5. **JANUS transfer vol**: 0.5–10 μL 범위.
6. **Export All** 클릭 → 폴더 dialog. 선택 후 6 종 파일 생성 확인:
   - `<plate>_<YYYYMMDD>.kuro.macrogen.xls`
   - `.kuro.primers.fasta`
   - `.kuro.echo.csv`
   - `.kuro.janus.csv`
   - `.kuro.platemap.xlsx`
   - `.kuro.run.json`
7. Macrogen .xls 를 Excel 에서 열어 column-major 96-well 배치 확인.
8. 96 well 초과 시나리오: primer > 96 → "분할 필요" 메시지.

### 4.2 Sidebar Drag Resize
1. 윈도우 좌측 사이드바 우측 모서리에 마우스 hover → 핸들 강조 (`bg-primary`).
2. 드래그하여 너비 변경. 180–480 px 범위 clamp 확인.
3. ArrowLeft/Right 키 1 px, Shift+Arrow 10 px, Home/End min/max.
4. 앱 재시작 → 변경된 너비 유지 (localStorage `kuma.layout.v1`).
5. kuro/mame 탭 전환 → 동일 너비 공유.

## 5. 알려진 잔여 이슈 (후속 PR 추적)

- `pnpm sync:check` 의 `[generated-models]` FAIL 은 worktree node_modules 부재 환경 한정. main repo merge 후 `pnpm install` 한 환경에서는 정상.
- Code review Warning 3건 / Suggestion 5건 — `notes/agent-reports/execute-plan-report.md` 참조.
- Macrogen `.xls` 의 Amount 셀 정확 문자열 (`0.05` vs `0.05 μmole`) 미확정. 현재 숫자 문자열 `"0.05"`/`"0.2"`. 실제 Macrogen 웹 LIMS 업로드 결과 확인 필요.
- Oligo Name 길이 상한 20 자 가정. Macrogen 실측 미확정.

## 6. 롤백 방법

```powershell
git checkout main   # 또는 feat/kuma-integration
git worktree remove .claude/worktrees/spec-export-all-macrogen    # main repo 에서
```

worktree 브랜치는 `worktree-spec-export-all-macrogen` 으로 유지. push 미수행.
