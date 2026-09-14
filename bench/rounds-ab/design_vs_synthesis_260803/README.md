# 설계 대 실제 합성 패널 (Figure 2c), 2026-08-03 실행본

원고 Figure 2c 로 들어가는 96웰 플레이트 맵을 그리는 스크립트와 그 입력이다.
버전 관리 밖에 있던 것을 2026-09-14 에 옮겨 왔다.

## release_r2 와 같은 산출물이 아니다

옆 폴더 `release_r2/` 는 라운드 2 재분석 릴리스다. 이 패널은 **다른 실행본**이라
같은 폴더에 두지 않았다. 세 가지가 다르다.

- 입력이 릴리스 워크북(`R2_FBF10847_v0.16.58_amplicon_MAME.xlsx`)이 아니라
  `run_analyze` 출력을 그대로 저장한 `well_verdicts.csv` 다
- depth 게이트를 끄고 돌렸다. 보관된 consensus 번들에 read 수 메타데이터가 없어
  `LOWDEPTH` 가 나올 수 없는 실행이다. `release_r2` 쪽은 게이트가 실제로 작동한다
- 더 이른 실행이다. 참조도 amplicon 이 아니라 `ispS.fasta` CDS 0-1683 이다

그래서 두 폴더의 replicate 층 분포는 서로 다른 수치이고 대조표로 나란히 놓으면
안 된다. 이 실행본 288 레코드는 PASS 210, WRONG_AA 60, AMBIGUOUS 9, MANY 9 다.
`release_r2` 의 288 레코드는 PASS 191 로 시작하는 8분류 분포다.

## 입력

`well_verdicts.csv`, 96행. 열은 `well,mutant,expected,verdicts,n_pass,aa1,aa2,aa3`
이고 `verdicts` 는 `|` 로 이은 replicate 3종 판정이다. 판정은 읽기만 하고 다시
계산하지 않는다. 288 = 96 well x 3 replicate 는 같은 construct 를 세 플레이트에서
잰 기술 반복이고 생물학적 반복이 아니다.

레포 사본과 `020.admin` 실행 사본은 바이트 동일하다. 이 폴더의 `.gitattributes`
가 CSV 의 줄끝 변환을 끈다. 레포 기본값(`.gitattributes:39`)이 `*.csv eol=crlf` 라
그대로 두면 checkout 바이트가 실행에 쓴 바이트와 달라진다.

## 판정 어휘

스크립트는 판정 목록을 손으로 적지 않는다. `kuma_core/mame/models.py` 의
`VerdictClass` 에서 읽어 온다(`make_fidelity_panel.py:39-72`). checkout 탐색 순서는
`KUMA_REPO_ROOT`, 스크립트 조상 중 `kuma_core` 를 가진 것, `$WORKSPACE_ROOT` 에
bench worktree 경로를 붙인 것이다. 못 찾으면 예외이고 대체 리터럴은 없다.

손으로 적은 네 키 목록이 여기 있던 결함이다. 목록 밖 판정을 가진 레코드가 조용히
합계에서 빠져도 그림만 봐서는 드러나지 않는다. 지금은 두 가지로 막는다.

- 어휘 밖 판정을 만나면 건너뛰지 않고 웰 이름과 판정 문자열을 찍고 즉시 종료한다
- 집계 합이 읽은 판정 수와 같은지 검산한다. 짧은 목록을 혼자 드러내는 쪽이 이것이다

`rep` 는 집계와 검산 전용이고 시각 요소가 아니다. 관측 0인 클래스가 생겨도 마크,
범례 행, 축 칸 어디에도 나타나지 않는다. 그래서 이 수정으로 SVG 두 개가 바이트
동일하게 유지된다.

`GATE = {"AMBIGUOUS", "MANY", "LOWDEPTH", "NO_CALL"}` 는 지웠다. 정의만 있고 읽는
곳이 없는 죽은 코드였다. 웰 단위 보류 판정은 `AUDIT_CLASS` 와 `clean_from_data` 가
맡고 그쪽은 데이터 유도 집합과 assert 로 묶여 있어 건드리지 않았다.

## 실행

산출물이 속한 곳은 볼트라 실행도 볼트 사본에서 한다.

```
cd <admin>/010.fig/260803_mame_design_vs_synthesis
python3 make_fidelity_panel.py                  # mame_design_vs_synthesis.svg
LANG_FIDELITY=en python3 make_fidelity_panel.py # mame_design_vs_synthesis_en.svg
```

`python3` 이 이 머신에서 도는 인터프리터다. `COMPACT=1` 은 슬라이드용 판이고
원고 경로가 아니다.

## 산출물 (원고 캡션이 인용하는 경로, 옮기지 말 것)

- `010.fig/260803_mame_design_vs_synthesis/mame_design_vs_synthesis.svg`
  sha256 `af31e5c459a06ef7424d475837a3ed0d1df2dd35014be4307a026c69a0a2e437`
- `010.fig/260803_mame_design_vs_synthesis/mame_design_vs_synthesis_en.svg`
  sha256 `c820e732118ff4e1829507e00b35d89546241239df9d8ab8fc5d3ff5c004091a`

SVG 가 정본이다. 두 파일은 레포에 넣지 않는다. 볼트가 원고 경로다.

## 판별력

`fixtures/run_fixtures.py` 가 수정 전 코드와 수정 후 코드를 같은 픽스처에 물려
차이를 보인다. 자세한 것은 `fixtures/README.md` 를 봐라.
