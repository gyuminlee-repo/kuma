# MAME 파이프라인

MinKNOW run 폴더 하나가 들어가 웰별 판정으로 나오기까지 MAME 가 하는 일을 정리한다. 실행은 `2.1 Inputs` 화면에서 시작하고 결과는 `2.2 Review` 화면에 나온다.

아래는 MinKNOW 실행 폴더를 그대로 넣는 `raw_run` 경로다. 이미 만들어 둔 FASTA 폴더를 넣는 나머지 두 모드는 앞쪽 단계를 건너뛴다.

## 들어가는 것과 나오는 것

들어가는 것은 MinKNOW run 폴더, reference FASTA, barcode 워크북, expected mutations 목록이다. 나오는 것은 이렇다.

- 웰별 consensus 서열. 출력 폴더의 barcode 폴더(`sort_barcodeNN/`) 아래에 `{R}_{F}.fasta` 로 쌓인다.
- 전체 웰을 합친 `final/consensus_all_dna.fasta`.
- 화면의 판정표와 plate 그림.
- 선정 클론 pick 목록 `..._picks.csv`. 실행이 자동으로 쓴다.

Excel 워크북과 로봇 매핑 시트(`..._janus.csv`)는 자동으로 나오지 않는다. Excel 은 실행이 끝난 뒤 "Excel 내보내기" 로 저장하고 매핑 시트는 step 3 에서 내보낸다.

## 거치는 단계

2 번부터는 진행 막대에 아래 이름 그대로 뜬다.

1. **Amplicon 잘라내기.** barcode 워크북의 프라이머가 reference 어디에 붙는지 찾아 그 사이 구간만 잘라 정렬용 reference 로 쓴다. 찾지 못하면 준 reference 를 그대로 쓴다.
2. **정렬 중.** 앱에 포함된 minimap2 가 `fastq_pass` 의 read 를 reference 에 붙인다.
3. **커버리지 필터.** 매핑 품질이 낮은 read 와 reference 를 충분히 덮지 못한 read 를 버린다.
4. **역다중화 중.** 남은 read 의 양끝 barcode 를 읽어 96 well 중 하나에 배정한다. 어느 한쪽 barcode 를 정하지 못하거나 동점이면 그 read 를 버린다.
5. **컨센서스 생성 중.** well 마다 같은 자리의 염기를 모아 다수결로 서열 하나를 만든다. 품질이 낮은 염기는 투표에서 빼고 read 가 너무 얕은 자리는 `N` 으로 둔다.
6. **분석 중.** well 별 서열을 기대 변이와 대조해 판정을 매긴다.

## run 폴더에서 읽는 파일

| 파일 | 쓰임 | 필수 |
|---|---|---|
| `fastq_pass/` 아래 barcode 폴더의 `*.fastq` 또는 `*.fastq.gz` | 분석에 쓰는 read | 필수 |
| `final_summary_*.txt`, `sample_sheet_*.csv` | run 이름과 시료 정보 | 있으면 읽음 |
| `sequencing_summary*.txt` 또는 `*.tsv` | read 품질과 barcode 교차오염 점검 | 있으면 읽음 |
| `pore_activity_*.csv`, `throughput_*.csv`, `barcode_alignment*.tsv` | run 건강 지표 | 있으면 읽음 |
| `report_*.json` | flow cell 종류와 공극 수 | 있으면 읽음 |

압축 여부는 상관없다. `*.fastq` 와 `*.fastq.gz` 를 모두 읽는다.

`report_*.json` 은 run 폴더에 없으면 한 단계 위 폴더에서 찾는다. 끝내 없으면 공극 값이 빈칸으로 남는다. 빈칸은 0 이 아니다.

`pod5/`, `fast5/`, `bam_pass/`, `other_reports/`, `report_*.html` 은 읽지 않는다. 지우지 않아도 되고 넣어도 달라지지 않는다.

## 조절할 수 있는 값

`2.1 Inputs` 화면 파라미터 패널의 **고급 옵션** 에 네 가지가 있다.

| 화면 표기 | 기본값 | 무엇이 달라지는가 |
|---|---|---|
| Coverage Fraction | 0.98 | read 하나가 reference 를 얼마나 덮어야 통과하는지 정한다. 올리면 온전한 정렬만 남고 내리면 부분 정렬도 들어온다 |
| 최소 매핑 품질(0–60) | 25 | 이 값보다 매핑 품질이 낮은 read 를 버린다 |
| Edit Distance Ratio | 0.25 | barcode 를 얼마나 느슨하게 맞출지 정한다. 작을수록 엄격해져 배정되는 read 가 줄어든다 |
| Chimera Split | 켬 | 한 read 가 여러 well 에 걸친 경우를 나눠서 센다. 켜 두기를 권한다 |

나머지 판정 기준값은 화면에서 바꾸지 않는다.

## 자주 실패하는 곳

- **판정이 하나도 안 나온다.** "분석이 끝났지만 well 0개" 창이 뜨고 read 가 어느 단계에서 얼마나 버려졌는지 수치로 보여준다. MAPQ 통과가 0 이면 reference 가 다른 construct 다. Coverage 통과가 0 이면 전장 construct 를 reference 로 쓴 것이므로 amplicon 구간을 reference 로 쓰거나 Coverage Fraction 을 내린다.
- **커버리지에서 많이 버려진다.** "커버리지 게이트가 정렬된 read 의 N%를 버렸습니다" 안내가 뜬다. 일부 손실은 정상이다. 비율이 크면 시료보다 reference 를 먼저 의심한다.
- **amplicon 을 잘라내지 못한다.** 프라이머 자리가 reference 에 없거나 여러 곳에 맞거나 앞뒤 순서가 뒤집힌 경우다. CDS 만 담긴 reference 에서는 프라이머가 CDS 밖에 있어 없는 것이 정상이다. 잘라내기를 건너뛴 채 가장 긴 read 가 커버리지 기준을 넘지 못하면 실행을 시작하지 않고 거절한다.
- **변이가 reference 끝에 있다.** 준 reference 를 그대로 정렬에 쓴 run 에서 기대 변이가 reference 양 끝 30 bp 안에 있으면 판정표 위에 그 변이 이름이 뜬다. 정렬기가 그 자리에서 read 를 잘라내 well 이 보고하는 depth 보다 얕게 읽힐 수 있다. 프라이머 자리까지 포함한 reference 를 쓰면 그 위치가 안쪽으로 들어온다.
- **이전 run 이 만든 폴더가 섞여 있다.** 출력 폴더에 남은 옛 plate 폴더는 판정에서 빼고 이름을 알려준다. run 마다 출력 폴더를 따로 쓰면 겹치지 않는다.

판정 클래스의 뜻과 well 하나를 파고드는 방법은 Review 화면 도움말에 있다.

→ [단계 1. 바코드 설정](mame-01-setup.md)
→ [단계 2. 분석 및 검토](mame-02-review.md)
