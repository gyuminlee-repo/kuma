# 설계 기록과 인용이 해석되지 않는 이유

이 저장소의 소스 주석과 docstring 은 설계 문서를 경로로 인용한다. 그중 일부는 따라가도 파일이 없다. 이 문서는 어떤 인용이 왜 해석되지 않는지 밝히고 그럴 때 무엇을 정본으로 삼아야 하는지 정한다.

`scripts/check-doc-citations.mjs` 가 이 분류를 기계로 강제한다. tracked 파일에서 문서 인용을 뽑아 해석을 시도하고, 실패한 것이 `scripts/doc-citations-allow.json` 에 없으면 실패한다. 새 미해석 인용은 이유를 적어 등록해야 통과한다.

측정 시점 기준으로 1,130개 파일에 인용 563건이 있고 그중 64건이 236곳에서 해석되지 않는다.

## 다섯 부류

| 부류 | 건수 | 뜻 | 어떻게 대해야 하나 |
|---|---|---|---|
| generated | 7 | 빌드가 만든다 | 정상이다. 빌드를 돌리면 생긴다 |
| internal | 26 | 공개 대상이 아닌 내부 기록 | 이 저장소에 없다. 아래 표 참조 |
| lost | 11 | 어디에도 남지 않았다 | 인용을 근거로 쓰지 마라 |
| external | 8 | 다른 저장소나 볼트의 문서 | kuma 경로가 아니다 |
| prose | 12 | 애초에 인용이 아니다 | 무시해도 된다 |

### generated

`NOTICE.md` 계열은 `scripts/build-notice.mjs` 가 릴리스 시점에 만든다. 소스 트리에 없는 것이 정상이다. `sync-check` 의 `tauri-resources` 항목이 로컬에서 실패하는 것도 같은 이유다.

### internal

`.gitignore:38` 이 `notes/` 를 "Dev tooling & internal notes" 로 제외한다. 이 저장소는 공개이고 그 문서들에는 공개 대상이 아닌 내용이 섞여 있다. 인터뷰 기록과 사람 이름이 그렇다. `notes/specs/2026-05-04-mame-activity-integration.md` §12-A.9 는 제목부터 특정 연구원 인터뷰 기록이다. 앞으로도 들어오지 않는다.

`notes/` 전체가 빠진 것은 아니다. 14개 파일이 force-add 되어 tracked 이므로(`notes/perf/` 10건, `2026-05-19-evolvepro-others-mode` 는 plans 와 specs 양쪽, `2026-05-28-mame-aporva-port`, `2026-07-31-menubar-app-menu-unify`) 그쪽 인용은 정상 해석된다. `plans/` 는 아예 제외 대상이 아니다.

내부 기록은 남아 있다. 저장소 밖에 있을 뿐이다. 소스가 인용하는 것은 아래와 같다.

| 인용 경로 | 다루는 범위 | 주로 인용하는 코드 |
|---|---|---|
| `notes/specs/2026-05-04-mame-activity-integration.md` | MAME activity 통합 전반. §12-A 가 전환 분류기(신호 정의, 결정 트리, 사전등록 임계값) | `kuma_core/strategy/` 전체, `kuma_core/mame/activity/` 대부분, `src/types/round*.ts` (22개 파일) |
| `notes/plans/2026-05-04-mame-activity-implementation-plan.md` | 위 스펙의 단계별 구현 계획 | `tests/strategy/` |
| `notes/architecture/2026-05-06-v0.3-phase-ab-interfaces.md` | v0.3 phase A·B 모듈 경계 | `kuma_core/mame/activity/` xlsx 계열 |
| `notes/specs/2026-05-06-mame-activity-v0.3-xlsx-pipeline.md` | xlsx 파이프라인 계약 | `export_evolvepro.py`, `sanity_check.py`, activity 핸들러 |
| `notes/specs/2026-05-11-kuro-mame-integration.md` | KURO 와 MAME 연결 | `UPDATE-NOTES` |
| `notes/specs/2026-05-13-menubar-prefs-shortcuts.md` | 메뉴바·환경설정·단축키 | `UPDATE-NOTES` |
| `notes/specs/2026-06-02-phase3-windows-minimap2.md` | Windows minimap2 번들 | `.github/workflows/build.yml` |
| `notes/specs/phase4-5-namespacing.md` | phase 4·5 네임스페이스 분리 | `KuroChrome.tsx`, `UPDATE-NOTES` |
| `notes/agent-reports/audit-*.md` | 프런트엔드 표준 감사 회차별 기록 | `docs/standards/common-frontend-standards.md` |

`.omo/` 아래 한 건은 `.gitignore` 가 아니라 `.git/info/exclude` 로 빠져 있다. 로컬 체크아웃 한정이라 다른 클론에서는 상태가 다를 수 있다.

### lost

아래는 저장소에도 내부 디렉터리에도 없다. 인용만 남았다.

| 인용 경로 | 인용하는 곳 |
|---|---|
| `v5-strategy.md` | KURO inspector 계열 6개, `KuroChrome.tsx`, MAME layout 3개. 모두 10곳이다. `[source: v5-strategy.md §N]` 형태로 화면 계약의 근거로 든다 |
| `v5-audit.md` | `KuroChrome.tsx`, MAME layout 2개, `PlateClusterAlert.tsx` |
| `notes/specs/2026-05-13-kuma-deps.md` | `AGENTS.md`. cross-layer 그룹 스키마를 다뤘다. 스키마 자체는 `AGENTS.md` 본문과 `.cross-layer-sync.json` 에 남아 있다 |
| `evidence/task-{1,4,5,6,7,8,9}-*.md` 7건 | `plans/evolvepro-checklist-closure.md`. 그 체크리스트는 tracked 인데 근거로 든 증거 문서는 없다 |
| `.gjc/plans/ralplan/2026-06-12-0645-bcdf/stage-08-final.md` | `benchmark/REPORT.md`, `benchmark/al/__init__.py` |

이 인용들이 든 근거는 확인할 수 없다. 같은 주장을 다시 쓸 일이 있으면 근거를 새로 대라.

### external

다른 저장소나 옵시디언 볼트의 문서다. kuma 경로가 아니므로 해석되지 않는 것이 맞다. `docs/2026-06-08-mame-transition-backtest.md` 가 형제 저장소 산출물을 나열하며 언급하는 `report_final.md` 계열이 여기 든다.

### prose

산문에 우연히 등장한 `.md` 문자열이다. CLI usage 플레이스홀더, 테스트의 zip 멤버 리터럴, 마크다운 링크 문법 예시, 그리고 디렉터리를 문장에서 따로 밝히고 파일명만 적은 경우가 섞여 있다.

## 스펙과 코드가 어긋나면

**코드와 테스트가 정본이다.** 위 내부 문서는 설계 시점의 기록이고 그 뒤로 코드가 움직였다. 확인된 어긋남이 둘 있다.

전환 분류기의 결정 트리는 스펙이 아니라 2026-06-08 backtest 를 따른다. T4 와 T_active, T_unused 는 계산하되 결정에서 강등됐다. 근거는 `docs/2026-06-08-mame-transition-backtest.md` 다. 스펙 §12-A 의 결정 트리 서술을 그대로 읽으면 지금 코드와 맞지 않는다.

EVOLVEpro 라운드 모델도 그렇다. 스펙 §12-A.0 은 라운드마다 best variant 를 새 baseline 으로 삼아 변이가 누적되는 walking 모델로 서술한다("Round 2: M1 baseline ... 실질 double"). 2026-06-09 에 상류 EvolvePro 원본 코드를 대조한 결과 그쪽은 고정 WT 배경의 single-refinement active learning 이었다. 그 대조는 이 저장소 밖 사본을 상대로 한 것이라 여기서 재확인할 수 없다. 라운드가 실제로 어떻게 도는지는 스펙 산문이 아니라 코드에서 읽어라.

전환 신호의 현재 가용성은 `python-core/sidecar_mame/handlers/classify_round.py` 의 모듈 docstring 이 가장 정확하다. 어떤 신호가 왜 NA 인지, 부트스트랩 신뢰도를 어디까지 믿어야 하는지 거기 적혀 있다.

## 새 인용을 쓸 때

저장소 안에서 해석되는 경로만 인용한다. 근거가 내부 문서에만 있으면 두 가지 중 하나를 택한다. 공개 가능한 결론만 `docs/` 로 옮겨 적고 그것을 인용하거나(`docs/2026-06-08-mame-transition-backtest.md` 가 그 방식이다), `scripts/doc-citations-allow.json` 에 항목을 추가하고 왜 해석되지 않아도 되는지 `reason` 에 적는다.

allowlist 에 접두 규칙이나 glob 은 두지 않는다. `notes/` 같은 접두를 한 번 허용하면 이후 모든 미해석 인용이 자동 통과해 검사기가 무력해진다.
