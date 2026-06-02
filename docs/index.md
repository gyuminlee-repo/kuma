# KUMA User Guide

KUMA는 두 도구를 하나의 Tauri 데스크톱 앱으로 묶은 프라이머 설계·NGS 검증 워크벤치다.

- **KURO** (Kernel for Upstream Recombination Oligodesign) — Gibson Assembly 템플릿에서 SDM 프라이머를 일괄 설계한다.
- **MAME** (Mutagenesis Assessment & Microplate Export) — Oxford Nanopore 데이터에서 의도 변이 보유 클론을 판정한다.

KURO 탭에서 프라이머를 설계하고, 시퀀싱 결과가 돌아오면 같은 프로젝트 폴더의 MAME 탭에서 판정을 받는다.

<!-- TODO: insert screenshot of KUMA main window -->

## Quick start

```bash
# 1) 최신 릴리스 다운로드
open https://github.com/gyuminlee-repo/kuma/releases

# 2) 첫 실행 — projects root 지정 (기본 ~/Documents/kuma)
# 3) New Project → Sequence 로드 → 변이 입력 → Run Design
```

## 아키텍처 (텍스트 다이어그램)

```
┌─────────────────────────┐
│  Tauri shell (Rust)     │
│  ┌───────────────────┐  │
│  │  React UI (Vite)  │  │
│  │  KURO / MAME 탭   │  │
│  └────────┬──────────┘  │
│           │ JSON-RPC     │
│  ┌────────┴──────────┐  │
│  │ kuro-sidecar.exe  │  │  PyInstaller 번들
│  │ mame-sidecar.exe  │  │  primer3 / minimap2 / pandas
│  └───────────────────┘  │
└─────────────────────────┘
```

## 진입

- [KURO 워크플로우 →](kuro/index.md)
- [MAME 워크플로우 →](mame/index.md)
- [입력 파일 사양 →](inputs/sequence.md)
- [트러블슈팅 →](troubleshooting/index.md)
