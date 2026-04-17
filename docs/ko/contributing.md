# 기여

## 이슈 제보

[이슈 트래커](https://github.com/gyuminlee-repo/KURO/issues) 사용. 포함할 정보:
- OS + KURO 버전 (Help → About 또는 installer 파일명)
- 재현 단계
- sidecar 크래시 관련 시 `~/.kuro/crash.log` 내용
- 가능하면 샘플 서열 / CSV (최소 재현 셋)

## 개발 환경

```bash
git clone https://github.com/gyuminlee-repo/KURO.git
cd KURO
pip install -e '.[build]'
pnpm install
pnpm run sidecar:build
pnpm tauri dev
```

테스트:
```bash
python -m pytest tests/ -v
npx tsc --noEmit
cd src-tauri && cargo check
```

## 코드 스타일

- TypeScript: `as any` 금지, `@ts-ignore` 금지
- Python: RPC 경계 검증은 Pydantic, `kuro/` 라이브러리는 순수 유지 (Tauri import 금지)
- 커밋: `vX.Y.Z: summary in English`

## PR 체크리스트

1. 테스트 통과 (`pytest`, `tsc`, `cargo check`)
2. `UPDATE-NOTES.md` / `UPDATE-NOTES.ko.md` 업데이트
3. UI 변경 시 스크린샷 재생성 (`pnpm run capture-guide`)
4. 신규 기능은 Wiki 업데이트 (이 repo의 `.wiki.git`)

## 라이선스

MIT — [LICENSE](https://github.com/gyuminlee-repo/KURO/blob/main/LICENSE) 참고.
