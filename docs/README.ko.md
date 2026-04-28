# kuma 문서

**Language**: [🇺🇸 English](./README.md) · 🇰🇷 한국어

![kuma 메인 창](./screenshots/04-design-complete.png)

**kuma**는 두 서브툴을 하나의 Tauri 데스크톱 앱으로 통합한다:

- **Kuro** (Kernel for Upstream Recombination Oligodesign) — Gibson Assembly 기반 SDM 프라이머 일괄 설계.
- **Mame** (Mutagenesis Assessment & Microplate Export) — Oxford Nanopore NGS 판정. 어떤 클론이 의도한 돌연변이를 가졌는지 검증.

두 탭은 같은 프로젝트 워크스페이스를 공유한다. Kuro xlsx export에 들어가는 숨김 시트 `__kuma_meta__` 덕분에 몇 주 뒤 시퀀싱 결과가 들어와도 Mame가 원래 프로젝트에 자동 매칭한다. 설치·아키텍처는 [프로젝트 README](../README.ko.md) 참고.

---

## 🦋 Kuro — SDM 프라이머 설계

### 🚀 시작하기
- [설치](./ko/installation.md) — Windows / macOS / Linux 설치
- [빠른 시작](./ko/quick-start.md) — 5단계로 첫 프라이머 설계
- [인터페이스 개요](./ko/interface-overview.md) — 패널 구성 및 메뉴 설명
- [FAQ](./ko/faq.md)

### 🧬 입력 및 준비
- [서열 로드](./ko/loading-sequences.md)
- [변이 입력](./ko/entering-mutations.md)
- [UniProt과 AlphaFold](./ko/uniprot-and-alphafold.md)
- [유전자 선택](./ko/gene-selection.md)

### ⚙️ 파라미터 및 전략
- [파라미터 패널](./ko/parameter-panel.md)
- [커스텀 폴리머레이즈 에디터](./ko/custom-polymerase-editor.md)
- [다양성 전략](./ko/diversity-strategies.md)
- [파이프라인 모드](./ko/pipeline-mode.md)

### 🔬 설계 및 검토
- [프라이머 설계](./ko/designing-primers.md)
- [결과 테이블](./ko/result-table.md)
- [후보 교체](./ko/candidate-swap.md)
- [실패 재시도](./ko/failed-retry.md)
- [서열 뷰어](./ko/sequence-viewer.md)

### 📦 출력
- [플레이트 맵](./ko/plate-map.md)
- [오더 내보내기](./ko/export-orders.md)
- [액체 핸들러 내보내기](./ko/export-liquid-handler.md)
- [Excel 내보내기](./ko/export-excel.md)
- [워크스페이스 저장·불러오기](./ko/workspace-save-load.md)

### 📊 분석 도구
- [벤치마크 다이얼로그](./ko/benchmark-dialog.md)
- [디자인 리포트](./ko/design-report.md)

### 🛠 고급
- [설정](./ko/configuration.md)
- [키보드 단축키](./ko/keyboard-shortcuts.md)
- [트러블슈팅](./ko/troubleshooting.md)
- [릴리스 노트 인덱스](./ko/release-notes-index.md)
- [기여](./ko/contributing.md)

---

## 🦠 Mame — NGS 판정

> 페이지 단위 상세 문서는 준비 중. 현재 사용법은 [프로젝트 README — Mame 탭 섹션](../README.ko.md#사용법)에서 확인할 수 있다.

Mame가 하는 일:

- Mame 탭에 Nanopore consensus FASTA와 참조 파일(있으면 `expected_mutations.xlsx`)을 드롭한다.
- CDS end, ingest mode, depth/identity cutoff을 설정한다.
- **Run** → 판정 테이블(PASS / WRONG_AA / FRAMESHIFT / AMBIGUOUS / LOWDEPTH / NOT_FOUND)과 96-well 플레이트 맵 생성.
- **Export** → well별 판정이 담긴 최종 xlsx 출력.
- Kuro에서 export한 xlsx를 Mame에 드롭하면 `__kuma_meta__ → project_id`로 원래 프로젝트에 자동 매칭된다.

샘플 입력은 Mame 메뉴바의 **Help → Load Sample Data**로 불러올 수 있다.

---

## 🔗 링크

- 소스: https://github.com/gyuminlee-repo/kuma
- 릴리스: https://github.com/gyuminlee-repo/kuma/releases
- 이슈: https://github.com/gyuminlee-repo/kuma/issues
