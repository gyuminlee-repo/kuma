# 릴리스 노트

> 이 노트는 kuma 통합 이전의 독립형 KURO 릴리스를 다룹니다.

전체 릴리스 이력은 메인 repo에서 확인:

- **English**: [UPDATE-NOTES.md](https://github.com/gyuminlee-repo/KURO/blob/main/UPDATE-NOTES.md)
- **한국어**: [UPDATE-NOTES.ko.md](https://github.com/gyuminlee-repo/KURO/blob/main/UPDATE-NOTES.ko.md)

## 최신: v1.33.6

- Windows 빌드 수정 (plugin-dialog 버전 mismatch)
- Sidecar Python 3.11 호환성 복구 (`typing_extensions.TypedDict`)
- BLAST contact 이메일 기본값 복구 — UniProt 고유사도 매칭 정상화
- PlateMap 버튼 순서 (플레이트 내비가 탭 옆, Export Mapping 우측 끝)
- 내보내기 파일명 자동 생성 (날짜 / 유전자 / 변이 수)
- EVOLVEpro CSV 상한 960 → 10,000, 개수 변경 시 자동 복구

## 바이너리

Windows / macOS / Linux installer가 각 GitHub Release에 첨부됨.
