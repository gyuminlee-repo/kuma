---
date: 2026-05-07
type: decision
project: kuma
decided_by: 강혜민
version: 0.1
status: draft
tags: [kuma, frontend, standards, charter, kuro, mame, primerbench]
---

# KUMA Common Frontend Standards (kuro · mame · primerbench)

세 앱(kuro, mame, primerbench) 독립 배포 빌드에서 공통적으로 지켜야 할 프론트엔드 요건을 22개 카테고리로 정의한다. 각 항목은 [필수]/[권장] 태그와 검증 가능한 acceptance criteria를 포함한다.

## 0. Scope & Conventions

- **대상**: kuro, mame, primerbench 독립 데스크탑 배포 (Tauri v2 + React 19 + Python sidecar)
- **태그**:
  - **[필수]**: 미준수 시 릴리스 차단
  - **[권장]**: 차기 마이너 버전까지 충족
- **상태 표기 (Per-app status table)**: ✅ 충족 / 🟡 부분 / ❌ 미구현 / ❓ 미확인 — 본 헌장 v0.1 에서는 전부 ❓ placeholder, 별도 audit 작업으로 채움
- **검증**: acceptance criteria 는 자동/수동 테스트 항목으로 직접 매핑

---

## 1. Recovery — 복구·초기화 [필수]

**Rationale**: 과학용 SW 는 장시간·다단계 작업이 많아 hang/dead-state 빈도가 높다. 복구 경로가 없으면 사용자가 강제 종료로만 빠져나오게 되어 데이터 손실 위험.

**Requirements**
- [필수] 전역 **Reset 버튼**: store + sidecar 상태 동시 초기화 (단축키 Ctrl/Cmd+Shift+R)
- [필수] **Sidecar 재시작 버튼**: Python 프로세스만 kill & respawn, UI 상태는 보존
- [필수] 장시간 작업 **Cancel/Abort** 버튼 (BLAST, alignment, design 등)
- [권장] **Dead-lock 감지**: progress notification 이 30초 이상 끊기면 모달로 안내
- [필수] **Workspace 자동 저장**: 30초 간격 또는 주요 액션 후, crash 재기동 시 직전 상태 복원

**Acceptance**
- Reset 후 sidecar PID 가 변경됨 (재기동 확인)
- Cancel 누르면 5초 이내 progress 종료
- 강제 종료 후 재실행 시 마지막 입력 폼 자동 복원

---

## 2. Observability — 진행 상태 가시성 [필수]

**Rationale**: 진행 단계 미공개는 "멈춘 건지 도는 건지" 불확실성을 유발하고 강제 종료를 자극한다.

**Requirements**
- [필수] **Progress bar + 단계 라벨** ("Aligning reads (3/12)" 형식). 단순 spinner 단독 금지
- [권장] **ETA 표시**: 동일 입력 크기 평균 기반 추정
- [필수] **로그 패널** (펼침 가능): sidecar stdout/stderr 실시간 스트림
- [필수] **Sidecar 헬스 인디케이터**: 좌하단 dot (green/yellow/red) + tooltip 으로 PID·메모리
- [필수] **에러 발생 위치 trace**: 어느 단계에서 실패했는지 명시

**Acceptance**
- 모든 RPC 호출에 progress notification 1개 이상 발생
- 헬스 인디케이터가 sidecar 재시작 직후 1초 이내 갱신

---

## 3. Input Guards — 입력 검증 [필수]

**Rationale**: schema mismatch 가 sidecar 까지 흘러가면 raw traceback 으로만 노출되어 사용자가 원인 파악 불가.

**Requirements**
- [필수] 파일 업로드 **schema 검증** (컬럼명·타입) 프론트엔드 단에서 1차 차단
- [필수] **빈 입력 차단**: Run 버튼 disabled + tooltip 으로 사유 표시
- [필수] **Sample Data 로드 버튼**: 신규 사용자가 동작 검증 가능
- [권장] **이전 입력 기억** (localStorage 마지막 사용 경로)
- [권장] 파일 input 옆 동등한 **Drag & Drop 영역**

**Acceptance**
- 잘못된 컬럼명 CSV 업로드 시 sidecar 호출 없이 즉시 빨간 메시지
- Sample Data → Run → Export 가 한 클릭씩 3회로 완주 가능

---

## 4. Error UX — 에러 표시 [필수]

**Rationale**: Python traceback raw 노출은 개발자에게만 의미 있고 일반 사용자에게는 진입장벽.

**Requirements**
- [필수] **사람이 읽을 수 있는 1차 메시지** + traceback 은 토글 펼침
- [필수] **재현 정보 복사 버튼**: 앱 버전 + sidecar 버전 + OS + 에러 라인 한 번에 클립보드
- [필수] **다음 액션 명시**: Retry / Reset / Open log folder 중 1개 이상 버튼 노출
- [권장] **네트워크 에러 분리**: UniProt/BLAST 외부 API 타임아웃은 일반 sidecar 에러와 다른 아이콘·문구

**Acceptance**
- 모든 에러 모달에 "복사" + "다음 액션" 두 버튼 동시 존재
- 네트워크 에러는 retry-after 안내 포함

---

## 5. Output Persistence — 결과 영속성 [필수]

**Rationale**: 결과 export 일관성이 부족하면 사용자가 어떤 패널에서 무엇이 저장되는지 학습 비용이 든다.

**Requirements**
- [필수] **Export 버튼 위치 일관성**: 모든 결과 패널 우상단 동일 위치
- [필수] **포맷 명시**: CSV / Excel / FASTA / PDF 중 해당 패널이 지원하는 포맷 드롭다운
- [필수] **결과 폴더 열기** 버튼: OS 파일 탐색기 호출
- [필수] **Default export 경로 project-aware** (kuro v0.3.1.0 패턴 준용)
- [필수] **덮어쓰기 confirm**

**Acceptance**
- Export 버튼 위치를 세 앱 스크린샷에서 동일 좌표(±20px)로 측정 가능
- 동일 파일명 export 시 confirm 모달 100% 발생

---

## 6. Settings — 설정·상태 [권장]

**Rationale**: 설정 UI 가 분산되면 사용자가 옵션을 찾기 어렵고 앱별 일관성도 떨어진다.

**Requirements**
- [필수] About 다이얼로그에 **앱 버전 + sidecar 버전 + Python 버전** 표시
- [권장] **데이터 폴더 위치** 설정 가능 + 현재 위치 표시
- [권장] **언어 토글** (ko/en) — i18n 미도입 시 향후 슬롯만 확보
- [권장] sidecar 바이너리 경로 표시

**Acceptance**
- About 모달이 메뉴바·헬프에서 동일 도달
- 버전 문자열은 `package.json` / `Cargo.toml` / sidecar 메타 일치

---

## 7. UI Safety — UI 안전장치 [필수]

**Rationale**: 이미 kuma CLAUDE.md 에 일부 명시. 세 앱 공통 강제.

**Requirements**
- [필수] **`flex-1` + `min-w-0`** 조합 강제 (셀렉트·텍스트 자식)
- [필수] 고정폭 사이드바 **`overflow-x-hidden`**
- [필수] 모달 **ESC 닫기 + backdrop click 닫기** (단, 진행 중 작업 모달 제외)
- [필수] 장시간 작업 중 **창 닫기 confirm**
- [필수] **다중 인스턴스 락**: 동일 워크스페이스에 두 앱 진입 차단 (lock file)

**Acceptance**
- ESLint/grep 으로 `flex-1` 인접에 `min-w-0` 누락 0건
- 작업 중 ⌘W / Alt+F4 누르면 confirm 모달

---

## 8. Accessibility & Ergonomics — 접근성·인체공학 [권장]

**Rationale**: 접근성·단축키 통일 부재는 마우스 미사용 사용자, 색약 사용자, 다른 OS 환경의 진입장벽을 키운다.

**Requirements**
- [필수] **Run / Save / Reset 단축키** (Ctrl/Cmd+R, Ctrl/Cmd+S, Ctrl/Cmd+Shift+R) 통일
- [필수] **Focus ring 보존** (shadcn/ui 기본 유지)
- [권장] **다크모드** 셋 다 동일 디자인 토큰 사용
- [필수] **Toast 위치 통일**: top-right
- [권장] **컬러블라인드 안전 팔레트** (특히 mame 의 plate map heatmap)

**Acceptance**
- 단축키 매핑 표가 About → Shortcuts 에 동일 구조로 노출
- Toast 가 동일 컴포넌트(`Sonner` 등) 재사용

---

## 9. Versioning & Updates — 버전·업데이트 [권장]

**Rationale**: 버전 mismatch 미처리 시 구 워크스페이스와 신 sidecar 간 호환성이 깨져 데이터 손실 위험.

**Requirements**
- [권장] **자동 업데이트 알림** 또는 About 의 "Check for updates"
- [필수] **Workspace schema_version mismatch 경고** + 마이그레이션 안내
- [필수] About 다이얼로그에 **Release notes 링크**
- [필수] 세 파일 버전 동기화 (`package.json` / `tauri.conf.json` / `Cargo.toml`)

**Acceptance**
- 구버전 워크스페이스 로드 시 호환성 모달 100% 발생
- 릴리스 시 세 버전 문자열 일치를 CI 단에서 검증

---

## 10. Telemetry & Privacy — 텔레메트리·프라이버시 [필수]

**Rationale**: 학술 SW 에서 무단 외부 호출은 IRB·기관 규정 위반 가능.

**Requirements**
- [필수] **외부 통신 1회 고지**: UniProt/BLAST/AlphaFold 호출 전 최초 1회 모달 동의
- [필수] **오프라인 모드 토글**: 외부 의존 기능 명시적 disable
- [필수] **암묵 텔레메트리 금지**: 사용자 데이터·메트릭 외부 송신 0건
- [권장] About 에 "Network calls made by this app" 목록 노출

**Acceptance**
- 첫 실행 시 외부 호출 모달 1회 노출 후 동의 상태 영속
- Wireshark/proxy 로 검증 시 동의 외 호출 0건

---

## 11. Build & Distribution — 빌드·배포 (Frontend 관점) [필수]

**Rationale**: 빌드 무결성 검증 없이는 변조된 바이너리 배포 가능성이 있고, 버전 불일치는 디버깅 비용을 키운다.

**Requirements**
- [필수] **버전 3-파일 동기화** (위 §9)
- [필수] **macOS ad-hoc codesign 상태 표시** (kuro v0.3.1.0 도입분 준용)
- [필수] **First-run onboarding**: 최초 실행 시 1-page 가이드
- [권장] **CI 산출물 무결성 표시**: About 에 빌드 SHA / 빌드 시각

**Acceptance**
- About 의 빌드 SHA 가 git tag 와 일치
- First-run 가이드는 두 번째 실행부터 미노출 (사용자 토글 가능)

---

## 12. Reproducibility — 재현성 [필수]

**Rationale**: 학술 SW 핵심 가치. 세 앱 모두 현재 약하므로 강하게 도입.

**Requirements**
- [필수] **Run manifest 자동 생성**: 결과 폴더에 `run.json` 동봉
  - 입력 파일 SHA-256
  - 파라미터 dict
  - 앱 버전 + sidecar 버전 + Python 버전
  - 시작/종료 timestamp (ISO 8601, UTC)
  - random seed (있다면)
- [필수] **Re-run from manifest**: `run.json` 드롭하면 입력·파라미터 자동 로드
- [권장] **Random seed 노출·고정**: 비결정 단계에서 사용자가 seed 입력 가능
- [권장] **Diff view**: 두 manifest 의 파라미터 차이 비교

**Acceptance**
- 모든 export 폴더에 `run.json` 존재
- 동일 manifest 로 두 번 실행 시 출력 SHA 일치 (seed 고정 시)

---

## 13. Long-running Jobs — 장시간 작업 신뢰성 [권장]

**Rationale**: 큐·OS 알림이 없으면 사용자가 작업 완료 시점을 놓치거나 sleep 으로 작업이 중단된다.

**Requirements**
- [권장] **Background job queue**: 여러 작업을 큐에 쌓고 순차 실행
- [필수] **OS native notification**: 작업 완료 시 백그라운드여도 알림
- [필수] **Sleep 방지**: 실행 중 OS sleep inhibit (Tauri plugin)
- [권장] **Resume from checkpoint**: 다단계 파이프라인(특히 mame raw_run) 중단 후 재개

**Acceptance**
- 5분 이상 작업 완료 시 OS 알림 발생률 100%
- 실행 중 macOS Caffeinate / Windows ES_SYSTEM_REQUIRED 활성화

---

## 14. Data Integrity — 데이터 무결성 검증 [필수]

**Rationale**: 입력 파일 무결성 검증 부재 시 손상된 데이터로 계산한 산출을 신뢰할 수 없고, sidecar 변조도 탐지 불가.

**Requirements**
- [필수] **입력 파일 SHA-256** UI 노출 + `run.json` 기록
- [필수] **Sidecar binary 무결성**: 시작 시 hash 검증, 변조 감지 시 실행 차단
- [필수] **Schema version gate**: 워크스페이스 로드 시 호환성 명시 + dry-run 마이그레이션
- [권장] **Output checksum**: export 결과에도 `*.sha256` 동봉

**Acceptance**
- 입력 파일 헤더에 SHA-256 prefix 8자 노출
- 손상된 sidecar 바이너리로 실행 시 안내 모달 + 종료

---

## 15. Onboarding — 사용자 학습 곡선 [권장]

**Rationale**: 신규 사용자 학습 곡선이 가파르면 docs 의존도가 커지고 초기 이탈률이 상승한다.

**Requirements**
- [권장] **Inline help (?) 아이콘**: 모든 입력 필드 옆, 호버 시 1-2줄 설명 + 외부 docs 링크
- [필수] **Empty state 가이드**: 빈 화면일 때 "Sample → Run → Export" 3-step 안내
- [권장] **What's New 모달**: 업데이트 직후 변경점 요약
- [권장] **튜토리얼 모드**: 첫 실행 시 가상 데이터로 walkthrough

**Acceptance**
- 신규 사용자가 docs 없이 sample → export 까지 5분 이내 완주
- What's New 는 마이너 버전 업데이트마다 1회만 노출

---

## 16. Local Diagnostics — 디버깅 자산 [권장]

**Rationale**: 사용자 ↔ 개발자 채널을 외부 전송 없이 로컬 zip 으로만 제공. 사용자가 메일/디스코드 등으로 직접 첨부.

**Requirements**
- [필수] **"Generate diagnostics zip" 버튼**: 로그 + manifest + 익명화 입력 헤더 + 환경 정보를 단일 zip 으로 패키징, 저장 후 Finder/Explorer 자동 열기
- [필수] **외부 자동 전송 금지**: 사용자가 명시적으로 첨부할 때만 외부 도달
- [권장] **Crash reporter (로컬)**: 패닉 후 다음 실행 시 "지난 세션이 비정상 종료됨, 진단 zip 생성하시겠어요?" 모달
- [권장] **Verbose 모드 토글**: 평소 깔끔, 디버그 시 stdout 전체

**Acceptance**
- 진단 zip 생성 시 어떤 외부 호출도 발생하지 않음 (Wireshark 검증)
- zip 내부에 로그, run.json, version 정보 3종 포함

---

## 17. Cross-platform Consistency — 멀티 플랫폼 일관성 [필수]

**Rationale**: OS별 단축키/경로/인코딩 차이를 무시하면 Windows/macOS/Linux 사용자 간 UX 격차와 데이터 깨짐(특히 한글 CSV)이 발생.

**Requirements**
- [필수] **OS별 단축키 자동 매핑** (Cmd vs Ctrl)
- [필수] **경로 표시 native 형식** (Windows `\` vs POSIX `/`)
- [필수] **CSV export 인코딩**: 기본 UTF-8 + BOM 옵션 (Excel 호환)
- [필수] **High-DPI 검증**: macOS Retina, Windows 150% 스케일 둘 다 통과
- [권장] **줄바꿈**: export 시 OS 기본 따름 토글

**Acceptance**
- macOS / Windows / Linux 빌드 스크린샷에서 단축키 표기 자동 변환 확인
- 한글 포함 CSV 가 Excel(Win/Mac) 양쪽에서 깨지지 않음

---

## 18. Partial Success — 부분 실패 [필수]

**Rationale**: 100개 primer 중 3개 실패해도 97개는 사용 가능해야 함. all-or-nothing 패턴 금지.

**Requirements**
- [필수] **Best-effort 결과 보존**: 일부 실패해도 성공분 export 가능
- [필수] **실패 항목 별도 패널**: 사유 + 개별/일괄 재시도 버튼
- [필수] **Warning vs Error 구분**: tolerance 완화 같은 "성공했지만 주의" 케이스 별도 색·아이콘
- [필수] **요약 통계**: "97/100 성공, 2 warning, 1 error"

**Acceptance**
- 실패 항목 존재 시에도 Export 버튼 enabled
- 실패 항목 패널에 재시도 버튼 동작 확인

---

## 19. Performance Guardrails — 성능 가드레일 [필수]

**Rationale**: 입력 크기 경고와 메모리 모니터가 없으면 대규모 데이터 처리 시 OOM 또는 freeze 가 사용자 측에서 그대로 발생.

**Requirements**
- [필수] **입력 크기 사전 경고**: 임계 초과 시 "약 N분 소요 예상" 모달
- [필수] **메모리 임계값 모니터**: sidecar RSS 가 시스템 메모리 70% 초과 시 차단·경고
- [필수] **Pagination/Virtual scroll**: 결과 테이블 1만 행 이상 시 가상 스크롤
- [권장] **Run pre-flight check**: 디스크 여유 공간, sidecar alive, 외부 API 도달 가능성

**Acceptance**
- 1만 행 테이블 렌더링 시 60fps 유지
- 메모리 70% 초과 시 모달 발생 후 정상 종료

---

## 20. Citation & Licensing — 라이선스·인용 [필수]

**Rationale**: 학술 SW 의무. 인용은 더미 placeholder 로 시작, 본 SW 가 인용 가능 형태(논문/Zenodo DOI)로 공개되면 채움.

**Requirements**
- [필수] About → **How to cite** 섹션: BibTeX/RIS 복사 버튼 (현재는 더미)
- [필수] About → **Third-party licenses** 전체 표시 (Tauri 의무사항)
- [필수] **Used data sources**: UniProt/PDB/AlphaFold 등 외부 DB 사용 시 출처·버전·접근일 노출
- [권장] 라이선스 (앱 자체) 명시: 미정 시 "Internal use, KRIBB C1 Lab" 표기

**Acceptance**
- About → How to cite 클릭 시 BibTeX 복사 동작 (placeholder 라도 형식 유효)
- Third-party licenses 가 빌드 시 자동 수집

**Citation placeholder (Appendix C 도 참조)**
```bibtex
@software{kuro_TBD,
  title = {KURO: Kernel for Upstream Recombination Oligodesign},
  author = {Kang, Hyemin and KRIBB C1 Lab},
  year = {2026},
  note = {DOI/citation forthcoming},
  url = {https://github.com/<org>/kuro}
}
```
mame, primerbench 도 동일 형식 placeholder.

---

## 21. Multi-workspace Management — 워크스페이스 다중 관리 [권장]

**Rationale**: 워크스페이스 격리가 미흡하면 프로젝트 A 의 설정·캐시가 B 로 누출되어 재현성과 데이터 분리가 깨진다.

**Requirements**
- [필수] **최근 프로젝트 목록**: 첫 화면에 5–10개
- [필수] **프로젝트 단위 격리**: 워크스페이스별 설정·캐시 분리
- [권장] **Compare workspaces**: 두 프로젝트의 결과 나란히 보기
- [권장] **Export/Import workspace**: 단일 zip 으로 워크스페이스 이전

**Acceptance**
- 워크스페이스 A 의 설정이 B 에 누출되지 않음
- 최근 프로젝트 목록이 5개 초과 시 자동 truncate

---

## 22. Graceful Shutdown — 안전한 종료 [필수]

**Rationale**: 비정상 종료 시 sidecar 좀비 프로세스, partial export, file lock 잔존이 다음 실행을 차단하거나 데이터 손상을 유발.

**Requirements**
- [필수] **Graceful shutdown**: 창 닫기 → sidecar SIGTERM → 정리 → 5초 후 SIGKILL fallback
- [필수] **Pending writes flush**: export 중 종료 시도 시 차단 + confirm
- [필수] **Lock file**: 동일 워크스페이스 다중 인스턴스 진입 방지
- [권장] **Shutdown hook**: 사용자 정의 cleanup 액션 (캐시 비우기 등)

**Acceptance**
- 종료 후 sidecar 좀비 프로세스 0건
- export 중 ⌘Q 누르면 confirm 모달

---

## Appendix A. Component Library 매핑

| 카테고리 | shadcn/ui 또는 컴포넌트 |
|---|---|
| Reset / Cancel 버튼 | `Button` (variant=destructive/outline) |
| Progress | `Progress` + 커스텀 stage label |
| Toast | `Sonner` (top-right) |
| Modal/Confirm | `Dialog`, `AlertDialog` |
| Inline help | `Tooltip` + `HoverCard` |
| Sidebar lock | 커스텀 `Resizable` + `overflow-x-hidden` |
| Diagnostics zip | 커스텀 (Tauri fs API) |

## Appendix B. Lint-able Rules — CLAUDE.md 흡수 후보

다음 항목은 자동 검증 가능하므로 kuma CLAUDE.md 또는 CI lint 단계로 통합:
- §7 `flex-1` + `min-w-0` 조합 grep 검증
- §9 세 파일 버전 일치 (`package.json` / `tauri.conf.json` / `Cargo.toml`)
- §11 Tauri resources 글로브 패턴(`**`) 미사용
- §10 외부 호출 화이트리스트 외 fetch 호출 0건
- §17 CSV export 시 UTF-8 BOM 옵션 존재 확인

## Appendix C. Citation Template (Dummy Placeholders)

```bibtex
@software{kuro_TBD,
  title  = {KURO: Kernel for Upstream Recombination Oligodesign},
  author = {Kang, Hyemin and KRIBB C1 Lab},
  year   = {2026},
  note   = {DOI/citation forthcoming},
  url    = {TBD}
}

@software{mame_TBD,
  title  = {MAME: Multi-round Activity & Mutation Engine},
  author = {Kang, Hyemin and KRIBB C1 Lab},
  year   = {2026},
  note   = {DOI/citation forthcoming},
  url    = {TBD}
}

@software{primerbench_TBD,
  title  = {PrimerBench: Benchmarking Suite for Primer Design Tools},
  author = {Kang, Hyemin and KRIBB C1 Lab},
  year   = {2026},
  note   = {DOI/citation forthcoming},
  url    = {TBD}
}
```

## Appendix D. Per-app Status Matrix (audit 2026-05-07, Phase 1–7 후 갱신)

판정 규칙: 카테고리 내 모든 [필수]·[권장] Requirements 충족 → ✅ / 일부 충족 → 🟡 / 전부 미구현 → ❌. 셀 단위 상세 근거(파일:라인)는 `notes/agent-reports/audit-kuma-v5.md` (Phase 7 후 재감사), `notes/agent-reports/audit-primerbench.md`, Phase 보고서 (`phase1a` ~ `phase7-*`) 참조.

### Req 단위 카운트 (audit-kuma-v5.md 기준)

| 앱 | ✅ | 🟡 | ❌ | 비교 (audit 시점) |
|---|---|---|---|---|
| kuro | 29 | 13 | 13 (응답 없는 Req 추정 포함) | ✅ 16 → 29 (+13), ❌ 25 → 13 (-12) |
| mame | 27 | 15 | 13 | ✅ 16 → 27 (+11), ❌ 26 → 13 (-13) |

(카테고리 단위 rollup 은 아래 표 참조)

| § | Category | kuro | mame | primerbench | 변동 |
|---|---|---|---|---|---|
| 1 | Recovery | 🟡 | 🟡 | 🟡 | — |
| 2 | Observability | 🟡 | 🟡 | 🟡 | — |
| 3 | Input Guards | 🟡 | 🟡 | 🟡 | — |
| 4 | Error UX | 🟡 | 🟡 | 🟡 | — |
| 5 | Output Persistence | 🟡 | 🟡 | 🟡 | — |
| 6 | Settings | 🟡 | 🟡 | 🟡 | — |
| 7 | UI Safety | ✅ | ✅ | 🟡 | kuro/mame 🟡→✅ (Phase 1a) |
| 8 | A11y & Ergonomics | 🟡 | 🟡 | 🟡 | — |
| 9 | Versioning | ✅ | ✅ | 🟡 | kuro/mame 🟡→✅ (Phase 7-4 auto update) |
| 10 | Telemetry & Privacy | ✅ | ✅ | 🟡 | kuro/mame 🟡→✅ (Phase 2b) |
| 11 | Build & Distribution | 🟡 | 🟡 | 🟡 | — |
| 12 | Reproducibility | 🟡 | 🟡 | ❌ | diff view 추가 (Phase 5-5). mame seed N/A 잔여 |
| 13 | Long-running Jobs | ✅ | ✅ | ❌ | kuro/mame 🟡→✅ (Phase 7-2 job queue + checkpoint via cancel/resume) |
| 14 | Data Integrity | ✅ | ✅ | 🟡 | sidecar binary hash 추가 (Phase 6-1). 4 Req 모두 ✅ |
| 15 | Onboarding | 🟡 | 🟡 | 🟡 | — |
| 16 | Local Diagnostics | 🟡 | 🟡 | 🟡 | — |
| 17 | Cross-platform | 🟡 | 🟡 | ❌ | — |
| 18 | Partial Success | 🟡 | 🟡 | 🟡 | — |
| 19 | Performance Guardrails | ✅ | ✅ | 🟡 | kuro/mame 🟡→✅ (Phase 7-1 pre-flight). 4 Req 모두 ✅ |
| 20 | Citation & Licensing | ✅ | ✅ | ❌ | kuro/mame 🟡→✅ (Phase 5-4 + fixup, NOTICE.md 자동 수집 + viewer) |
| 21 | Multi-workspace | 🟡 | 🟡 | 🟡 | — |
| 22 | Graceful Shutdown | 🟡 | 🟡 | ❌ | CloseConfirmDialog 도입 (Phase 6-2). pending export flush·shutdown hook 보강. 셀 카운트 변화 미미 |

### Phase 1–7 누적 결과
- **🟡 → ✅ 카테고리 14건**: §7, §9, §10, §13, §14, §19, §20 (kuro/mame 양쪽)
- **❌ → 🟡 카테고리 8건**: §12, §22 보강 (kuro/mame)
- **kuro 카운트** (rollup): ❌ 0 / 🟡 15 / ✅ 7 (audit 시점 ❌ 4 / 🟡 18 / ✅ 0)
- **mame 카운트** (rollup): ❌ 0 / 🟡 15 / ✅ 7 (audit 시점 ❌ 4 / 🟡 18 / ✅ 0)
- **Req 단위**: kuro ✅ 29/40, mame ✅ 27/40
- **primerbench**: PB Phase A-D 진행 중 (별도 레포)

### 잔여 약점 (Phase 6 후 — 모두 [권장] 또는 부분 항목)

§12 Reproducibility:
- **mame seed UI 미구현** (mame 비결정 단계 없으므로 N/A 처리 가능)

§13 Long-running Jobs:
- **Background job queue** 미구현
- **Resume from checkpoint** 미구현

§19 Performance Guardrails:
- **Run pre-flight check** 미구현 (디스크·sidecar alive·외부 API 도달 확인)

§22 Graceful Shutdown:
- **Shutdown hook** (사용자 정의 cleanup) 미구현

§8 / §9 / §17 등 [권장] 카테고리는 ETA·다크모드·자동 업데이트 알림 같은 부분 항목 잔여.

### 다음 우선 보강 (Phase 7 후보, 가치/비용 기준)

1. **§19 Run pre-flight check**: 디스크 여유·sidecar 헬스·네트워크 도달 검사 후 Run. ~40 LoC
2. **§13 Background job queue**: 다중 export/design 큐. ~80 LoC
3. **§17 PrimerBench**: 별도 레포에 헌장 적용 (kuma 패턴 이식)
4. **§9 자동 업데이트**: Tauri updater 활성화 + About "Check for updates"
5. **§8 다크모드**: 디자인 토큰 통일 + 토글

---

## Changelog

- **v0.1 (2026-05-07)**: 22 카테고리 초안. status matrix placeholder. 외부 진단 전송 제거(§16). Citation 더미(§20).
- **v0.1.1 (2026-05-07)**: 11개 카테고리(§6, 8, 9, 11, 13, 14, 15, 17, 19, 21, 22) Rationale 보강 (verifier FAIL 수정).
- **v0.2 (2026-05-07)**: Per-app audit 완료. Appendix D 매트릭스 ❓ → 실제 status 채움. 공통 약점·강점·우선 보강 5순위 추가. 근거: `notes/agent-reports/audit-kuma.md`, `audit-primerbench.md`.
- **v0.3 (2026-05-07)**: Phase 1–3 (v0.3.2.1 ~ v0.3.3.0) 결과 반영. §7/§10 → ✅, §12/§20 → 🟡, §22 부분 보강. kuro/mame ✅ 카테고리 0→2, ❌ 카운트 4→3. 다음 우선 5순위 갱신.
- **v0.4 (2026-05-07)**: Phase 4 (v0.3.3.2~v0.3.3.3) 결과 반영. §13/§19 → 🟡, §22 SIGKILL fallback 도입, §12 seed UI, §14 dry-run 마이그레이션. kuro/mame ❌ 카운트 2→0 (모든 [필수] 미구현 카테고리 해소). 다음 우선 5순위 입력 경고·sleep inhibit·output checksum 중심으로 갱신.
- **v0.4.1 (2026-05-07)**: 셀 단위 재감사 완료 — `audit-kuma-v2.md`. Req 단위 ✅ 카운트 kuro +6, mame +5. ❌ 카운트 kuro -7, mame -7. Appendix D 근거 링크를 v2 로 갱신.
- **v0.5 (2026-05-07)**: Phase 5 (v0.3.4.0) + fixup 결과 반영. §20 Citation kuro/mame 🟡→✅. §12/§13/§14/§19 셀 단위 보강. Req ✅ 카운트 kuro 22→26, mame 21→24. 모든 [필수] 카테고리에서 ❌ 셀 0건. 잔여는 [권장] 또는 부분 항목. 다음 보강 5순위 갱신 (sidecar hash, pending export flush, 메모리 모니터, in-app toast, PrimerBench).
- **v0.6 (2026-05-07)**: Phase 6 (v0.3.5.0) 결과 반영. §14 Data Integrity kuro/mame 🟡→✅ (sidecar binary hash 도입). §13/§19 셀 보강 (in-app toast, 메모리 모니터). §22 CloseConfirmDialog. Req ✅ 카운트 kuro 26→27, mame 24→25. ✅ 카테고리 3→4. 다음 우선 5순위 갱신 (§19 pre-flight, §13 job queue, PrimerBench, §9 자동 업데이트, §8 다크모드).
- **v0.7 (2026-05-07)**: Phase 7 (v0.3.6.0) 결과 반영. §9/§13/§19 kuro/mame 🟡→✅. ✅ 카테고리 4→7. Req ✅ 카운트 kuro 27→29, mame 25→27. PrimerBench 별도 레포 PB Phase A-D 동시 진행 중. 잔여 부진 카테고리: §1, §2, §4, §5, §6, §8, §11, §12, §15, §16, §17, §18, §21, §22 (모두 [권장] 또는 부분 미구현).

## 후속 액션

1. 사용자 리뷰 후 v0.1 → v1.0 승격
2. Per-app audit 별도 태스크로 진행 (kuro/mame/primerbench src grep)
3. Appendix B 항목을 kuma CLAUDE.md / CI lint 로 흡수
4. Citation placeholder 는 논문/Zenodo 공개 시 갱신
