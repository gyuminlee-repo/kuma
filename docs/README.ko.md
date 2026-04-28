# kuma — Kuro 서브툴 문서

**Language**: [🇺🇸 English](./README.md) · 🇰🇷 한국어

![Kuro 메인 창](./screenshots/04-design-complete.png)

이 페이지는 [kuma](../README.ko.md) 안의 **Kuro** 서브툴 문서다. Kuro(Kernel for Upstream Recombination Oligodesign)는 Gibson Assembly 기반 Site-Directed Mutagenesis(SDM) 프라이머를 일괄 설계하는 탭이다. 같은 워크스페이스 안의 또 다른 서브툴 Mame(Mutagenesis Assessment & Microplate Export)는 NGS 판정을 담당한다.

## 🚀 시작하기

- [설치](./ko/installation.md) — Windows / macOS / Linux 설치
- [빠른 시작](./ko/quick-start.md) — 5단계로 첫 프라이머 설계
- [인터페이스 개요](./ko/interface-overview.md) — 패널 구성 및 메뉴 설명

## 🧪 Kuro가 하는 일

변이 목록(텍스트 또는 EVOLVEpro CSV)과 템플릿 서열(GenBank / SnapGene)을 입력하면 overlap-extension 방식으로 SDM 프라이머 쌍을 자동 생성. 출력: IDT/Twist 오더 CSV, Echo/JANUS 액체핸들러 매핑 파일, 변이별 통계를 담은 Excel 워크북. 모든 export에는 숨김 시트 `__kuma_meta__`가 들어가서 Mame 탭이 나중에 시퀀싱 결과를 원래 프로젝트로 자동 매칭한다.

## 📑 전체 페이지

### 📘 시작하기
- [설치](./ko/installation.md)
- [빠른 시작](./ko/quick-start.md)
- [인터페이스 개요](./ko/interface-overview.md)
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

## 🔗 링크

- 소스: https://github.com/gyuminlee-repo/kuma
- 릴리스: https://github.com/gyuminlee-repo/kuma/releases
- 이슈: https://github.com/gyuminlee-repo/kuma/issues
